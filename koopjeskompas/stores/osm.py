"""Store lists from OpenStreetMap, for ``koopjeskompas fetch-stores``.

The Overpass API answers queries over OpenStreetMap's data. One query, built from
the chain registry (``koopjeskompas/chains.py``), asks for every supermarket of every
known chain in the Netherlands; this module sends it and turns the answer into
validated ``Store``s, each with its chain. Stores open and close slowly, so this runs
now and then by hand, never per request: its result is committed and packaged as
``nl_stores.json``.

Overpass is free and often busy, and it fails in two ways, both handled here:
an HTTP error (429, 502, 504), and a 200 OK whose ``remark`` reports a runtime error
next to partial or no data. A server without area data (some mirrors) finds nothing
in "the Netherlands" at all. So a run that finds no stores is an error: it must
never replace the list with an empty one.

Overpass gives each IP address a few query slots (usually 2); further queries wait
in a queue. Three rules keep us from clogging our own slots, learned the hard way
on 2026-11-10, when five abandoned queries kept them busy for an hour:

- one light query: every supermarket in the country, the chain worked out here;
- the client waits longer than the query may run, so it never abandons a query
  that is still taking up a slot on the server;
- the status page first: no free slot means stop, not queue. And one attempt per
  run, no automatic retries.

Like AH's payloads, OSM's shapes stop at this module's border: the rest of the code
only sees ``Store``.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from koopjeskompas.chains import CHAINS, Chain
from koopjeskompas.domain.distance import haversine_km
from koopjeskompas.domain.models import Coordinates, Store

DEFAULT_SERVER = "https://overpass-api.de/api/interpreter"
# How long Overpass may run the query, and how long we wait for it: longer, so we
# never walk away from a query that still holds one of our slots.
QUERY_TIMEOUT_S = 180
CLIENT_TIMEOUT_S = 240
STATUS_TIMEOUT_S = 20
# Identify ourselves, as Overpass asks; a link, not anyone's email address.
HEADERS = {"User-Agent": "koopjeskompas/0.1 (+https://github.com/kvta1/Koopjeskompas)"}
# A store mapped twice (as a point and as its building) shows up twice, close together.
DUPLICATE_WITHIN_KM = 0.1
# Collection points for online orders, sometimes tagged as supermarkets: no shopping.
_PICKUP = re.compile(r"pick\s*-?up", re.IGNORECASE)
# The large stores: brand "Albert Heijn XL", or "XL" in the name.
_XL = re.compile(r"\bXL\b")


class OverpassError(RuntimeError):
    """Overpass could not answer usefully; the message says why and what to try."""


# --- asking ----------------------------------------------------------------


def overpass_query() -> str:
    """Every supermarket in the Netherlands, as Overpass QL.

    One clause: a single lookup in the country's area is far cheaper for Overpass
    than a search per chain, brand and name. Which chain a store belongs to is
    worked out afterwards, here (``_chain_of``), so a new chain costs the server
    nothing. The country is the area with ISO code NL, so stores across the border
    (other deals) stay out; ``shop=supermarket`` leaves out "AH to go".
    """
    return f"""[out:json][timeout:{QUERY_TIMEOUT_S}];
area["ISO3166-1"="NL"]["admin_level"="2"]->.nl;
nwr["shop"="supermarket"](area.nl);
out center tags;
"""


# --- fetching --------------------------------------------------------------


def fetch_overpass(
    query: str, server: str = DEFAULT_SERVER, http: httpx.Client | None = None
) -> Any:
    """Run ``query`` on an Overpass server and return its JSON answer.

    One attempt: when Overpass is busy, the answer is to wait, not to ask again.
    """
    client = http or httpx.Client(timeout=CLIENT_TIMEOUT_S)
    check_slots(server, client)
    try:
        response = client.post(server, data={"data": query}, headers=HEADERS)
    except httpx.HTTPError as error:
        raise OverpassError(f"{server} could not be reached: {error}") from error
    if response.status_code != 200:
        busy = response.status_code in (429, 502, 503, 504)
        raise OverpassError(
            f"{server} answered {response.status_code}"
            + ("; it's busy: try again later, or another --server" if busy else "")
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise OverpassError(f"{server} answered something other than JSON") from error

    # A 200 can still be a failure: the query timed out or ran out of memory
    # halfway, and the elements, if any, are incomplete.
    remark = payload.get("remark", "") if isinstance(payload, dict) else ""
    if "error" in remark.lower():
        raise OverpassError(f"{server} reported: {remark}")
    return payload


def status_url(server: str) -> str:
    """ "https://overpass-api.de/api/interpreter" -> ".../api/status"."""
    return server.rsplit("/", 1)[0] + "/status"


def check_slots(server: str, client: httpx.Client) -> None:
    """Stop unless the server has a query slot free for us right now.

    A server without a status page, or one in an unknown format, is given the
    benefit of the doubt.
    """
    url = status_url(server)
    try:
        response = client.get(url, headers=HEADERS, timeout=STATUS_TIMEOUT_S)
    except httpx.HTTPError as error:
        raise OverpassError(
            f"{url} didn't answer ({error}): the server, or this computer's query "
            "slots, are busy. Wait a while, then try once more."
        ) from error
    if response.status_code != 200:
        return
    text = response.text
    if re.search(r"Rate limit: 0\b", text):
        return  # no limit on this server
    free = re.search(r"(\d+) slots? available now", text)
    if free and int(free[1]) > 0:
        return
    waits = [
        int(s)
        for s in re.findall(r"Slot available after: \S+, in (-?\d+) seconds", text)
    ]
    if free or waits:
        when = f" The next one frees up in {max(min(waits), 0)} s." if waits else ""
        raise OverpassError(
            f"{server} has no free query slot for this computer.{when} "
            "Wait, then try once more."
        )


# --- converting ------------------------------------------------------------


class _Center(BaseModel):
    lat: float
    lon: float


class _Element(BaseModel):
    """One OSM object: a node (a point) or a way or relation (an outline)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    type: str
    id: int
    lat: float | None = None  # nodes
    lon: float | None = None
    center: _Center | None = None  # ways and relations, with `out center`
    tags: dict[str, str] = {}

    @property
    def key(self) -> str:
        return f"{self.type}/{self.id}"  # how openstreetmap.org addresses it


@dataclass
class StoreImport:
    """The stores, and what was left out and why."""

    stores: list[Store]
    skipped: list[str] = field(default_factory=list)
    duplicates: int = 0
    # Supermarkets of chains we don't know, by brand: counted, not listed.
    other_chains: Counter[str] = field(default_factory=Counter)


def stores_from_overpass(payload: Any) -> StoreImport:
    """Turn an Overpass answer into stores, one per supermarket, sorted."""
    result = StoreImport(stores=[])
    elements = payload.get("elements", []) if isinstance(payload, dict) else []
    for raw in elements:
        try:
            element = _Element.model_validate(raw)
        except ValidationError:
            result.skipped.append(f"{raw!r:.80}: not an OSM element")
            continue
        tags = element.tags
        if tags.get("shop") != "supermarket":
            # e.g. an "AH to go", with a smaller assortment
            result.skipped.append(f"{element.key}: not a supermarket")
            continue
        chain = _chain_of(tags)
        if chain is None:
            result.other_chains[tags.get("brand") or tags.get("name") or "?"] += 1
            continue
        store = _store_from(element, chain)
        if isinstance(store, str):
            result.skipped.append(f"{element.key}: {store}")
        else:
            result.stores.append(store)

    unique = list(_without_duplicates(result.stores))
    result.duplicates = len(result.stores) - len(unique)
    # Sorted, so a new fetch shows up in git as a readable diff.
    result.stores = sorted(
        unique, key=lambda s: (s.name, s.address or "", s.location.latitude)
    )
    return result


def _store_from(element: _Element, chain: Chain) -> Store | str:
    """The element as a store of ``chain``, or the reason it isn't one."""
    tags = element.tags
    if _PICKUP.search(tags.get("name", "")):
        return "a pickup point, not a store"
    location = _location(element)
    if location is None:
        return "no location"
    street, city = tags.get("addr:street"), tags.get("addr:city")
    place = street or tags.get("branch") or city
    if place is None:
        return "no street, branch or town to name it by"
    xl = any(_XL.search(tags.get(key, "")) for key in ("brand", "name"))
    return Store(
        chain=chain.name,
        name=f"{chain.name} XL {place}" if xl else f"{chain.name} {place}",
        address=_address(street, tags.get("addr:housenumber"), city),
        location=location,
    )


def _chain_of(tags: dict[str, str]) -> Chain | None:
    """Which chain a store belongs to: by Wikidata ID, else brand, else name.

    In that order, because the ID is the most reliable: a store tagged with AH's ID
    but named "Jumbo" (a mapping mistake) still counts as AH.
    """
    wikidata, brand, name = (
        tags.get(key, "") for key in ("brand:wikidata", "brand", "name")
    )
    return (
        next((c for c in CHAINS if wikidata in c.wikidata), None)
        or next((c for c in CHAINS if brand in c.brands), None)
        or next((c for c in CHAINS if re.match(c.name_pattern, name)), None)
    )


def _location(element: _Element) -> Coordinates | None:
    if element.lat is not None and element.lon is not None:
        return Coordinates(latitude=element.lat, longitude=element.lon)
    if element.center is not None:
        return Coordinates(latitude=element.center.lat, longitude=element.center.lon)
    return None


def _address(street: str | None, number: str | None, city: str | None) -> str | None:
    """ "Breestraat 130, Leiden", or as much of it as is known."""
    line = " ".join(part for part in (street, number) if part) if street else None
    return ", ".join(part for part in (line, city) if part) or None


def _without_duplicates(stores: Iterable[Store]) -> Iterable[Store]:
    """Each store once: a same-named store within 100 m is the same store mapped twice.

    Compared only within a name, so it's a few comparisons per store, not n².
    """
    kept: dict[str, list[Store]] = {}
    for store in stores:
        same_name = kept.setdefault(store.name, [])
        if all(
            haversine_km(store.location, other.location) > DUPLICATE_WITHIN_KM
            for other in same_name
        ):
            same_name.append(store)
            yield store

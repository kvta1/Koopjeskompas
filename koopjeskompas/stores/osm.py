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

Like AH's payloads, OSM's shapes stop at this module's border: the rest of the code
only sees ``Store``.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from koopjeskompas.chains import CHAINS, Chain
from koopjeskompas.domain.distance import haversine_km
from koopjeskompas.domain.models import Coordinates, Store

DEFAULT_SERVER = "https://overpass-api.de/api/interpreter"
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


def overpass_query(chains: Sequence[Chain] = CHAINS) -> str:
    """Every supermarket of these chains in the Netherlands, as Overpass QL.

    The country is the area with ISO code NL, so stores across the border (other
    deals) stay out. Each chain's stores are matched on the brand's Wikidata ID, on
    the brand name for stores without it, and on the name alone for stores mapped with
    neither. Only ``shop=supermarket``: "AH to go" is a convenience shop.
    """
    lines = []
    for chain in chains:
        lines += [
            f'  nwr["shop"="supermarket"]["brand:wikidata"="{q}"](area.nl);'
            for q in chain.wikidata
        ]
        lines += [
            f'  nwr["shop"="supermarket"]["brand"="{b}"](area.nl);'
            for b in chain.brands
        ]
        lines.append(
            f'  nwr["shop"="supermarket"]["name"~"{chain.name_pattern}"](area.nl);'
        )
    body = "\n".join(lines)
    return f"""[out:json][timeout:180];
area["ISO3166-1"="NL"]["admin_level"="2"]->.nl;
(
{body}
);
out center tags;
"""


# --- fetching --------------------------------------------------------------


def fetch_overpass(
    query: str, server: str = DEFAULT_SERVER, http: httpx.Client | None = None
) -> Any:
    """Run ``query`` on an Overpass server and return its JSON answer."""
    client = http or httpx.Client(timeout=180)  # a country-wide query takes a while
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
        store = _store_from(element)
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


def _store_from(element: _Element) -> Store | str:
    """The element as a ``Store``, or the reason it isn't one."""
    tags = element.tags
    if tags.get("shop") != "supermarket":
        return "not a supermarket"  # e.g. an "AH to go", with a smaller assortment
    chain = _chain_of(tags)
    if chain is None:
        return "not a store of a known chain"
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

"""The supermarket chains Koopjeskompas knows, in one place.

Each chain's deals and stores meet on its ``name`` ("AH", "Jumbo"): a ``Deal`` and a
``Store`` of the same chain carry the same name. The ``key`` is the same chain as the
command line and the files know it: ``fetch-deals --chain jumbo``, ``data/raw/jumbo/``,
``deals/jumbo.json``.

Adding a chain means one entry here, plus a deal source in ``ingestion/``. This module
has no dependencies, so the Lambda can read it without importing any scraper code.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    key: str  # lower case, for the command line and file names
    name: str  # as stores and deals carry it, and as the page shows it
    # How OpenStreetMap knows the chain's stores (koopjeskompas fetch-stores):
    wikidata: tuple[str, ...]  # brand:wikidata IDs, which mappers set consistently
    brands: tuple[str, ...]  # brand names, for stores mapped without the ID
    # A regular expression for names, for stores mapped with neither (OSM's
    # regex dialect, which Python's re also understands for these simple ones).
    name_pattern: str


CHAINS: tuple[Chain, ...] = (
    Chain(
        key="ah",
        name="AH",
        # The XL stores carry their own brand and Wikidata ID.
        wikidata=("Q1653985", "Q78163765"),
        brands=("Albert Heijn", "Albert Heijn XL"),
        name_pattern="^(AH|Albert Heijn)( |$)",
    ),
    Chain(
        key="jumbo",
        name="Jumbo",
        wikidata=("Q2262314",),
        brands=("Jumbo",),
        name_pattern="^Jumbo( |$)",
    ),
    Chain(
        key="lidl",
        name="Lidl",
        wikidata=("Q151954",),
        brands=("Lidl",),
        name_pattern="^Lidl( |$)",
    ),
)


def chain_named(name: str) -> Chain | None:
    """The chain a store or deal belongs to, by its name; case doesn't matter."""
    return next((c for c in CHAINS if c.name.casefold() == name.casefold()), None)

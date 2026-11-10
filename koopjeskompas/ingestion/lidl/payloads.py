"""Pydantic models of the product tiles on Lidl's deals page, as observed in November 2026.

The anti-corruption layer: Lidl's shapes stop here. Each tile on
``lidl.nl/c/aanbiedingen/…`` carries its product as JSON in a ``data-grid-data``
attribute; ``client.py`` collects those, and the parser validates them one by one.

Prices are per region (``regionsPrices``, keyed "1" to "6"); in November 2026 every
region had the same prices, so the first one is used. Each region has a
``currentPrice`` and, for Lidl Plus deals, a ``currentLidlPlusPrice``: both with the
price, the old price if there is one, and when they apply.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Lidl's own coarse categories that aren't food: non-food, and plants and flowers.
NON_FOOD = frozenset({"NonFood", "P+F"})

# An end date this far off means "no end": the regular assortment, not a deal.
INDEFINITE_FROM_YEAR = 2100


class _LidlModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", frozen=True)


class Price(_LidlModel):
    price: Decimal  # euros, e.g. 1.99
    old_price: Decimal | None = None  # the struck-through price, if shown
    start_date: datetime | None = None  # UTC, e.g. 2026-11-04T23:00Z
    end_date: datetime | None = None  # UTC, e.g. 2026-11-15T22:59:59Z

    @property
    def indefinite(self) -> bool:
        return self.end_date is None or self.end_date.year >= INDEFINITE_FROM_YEAR


class LidlPlusPrice(_LidlModel):
    price: Price
    lidl_plus_text: str | None = None  # "met Lidl Plus"


class RegionPrices(_LidlModel):
    current_price: Price
    current_lidl_plus_price: LidlPlusPrice | None = None


class KeyFacts(_LidlModel):
    analytics_category: str | None = None  # "Food", "F+V", "NonFood", "P+F"
    # e.g. "Werelden van nood/Eten en dichtbij voedsel/Snoep & snacks/Hartige hapjes"
    won_category_primary: str | None = None


class GridItem(_LidlModel):
    product_id: int
    full_title: str  # with the brand: "Bellarom Koffiecups", not "Koffiecups"
    keyfacts: KeyFacts = KeyFacts()
    regions_prices: dict[str, RegionPrices]

    @property
    def name(self) -> str:
        # Lidl sometimes starts a title with "- ", as in "- Boerenbruin heel".
        return self.full_title.removeprefix("- ").strip()

    @property
    def category(self) -> str | None:
        """The narrowest category: "Hartige hapjes" in the example above."""
        path = self.keyfacts.won_category_primary
        return path.rsplit("/", 1)[-1] if path else None

    @property
    def prices(self) -> RegionPrices:
        return next(iter(self.regions_prices.values()))

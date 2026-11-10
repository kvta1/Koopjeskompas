"""Pydantic models of the data Jumbo's deal pages embed, as observed in November 2026.

The anti-corruption layer: Jumbo's shapes stop here and never reach the domain. Only
the fields we use are declared. Lists whose items are validated one by one are typed
``list[Any]``, so one odd promotion can't sink the whole page; the parser reports it.

Two pages are read (see ``client.py``):

- the overview, ``/aanbiedingen/nu``: this week's and next week's promotions
  (Wednesday to Tuesday), each listed in a highlights section and in its aisle;
- a promotion's own page, for promotions whose discount depends on a price ("2 voor
  3,49"): its products, with prices in cents.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# A section that repeats promotions from the aisles; it says nothing about category.
HIGHLIGHTS = frozenset({"Nu in de aanbieding"})

# Jumbo's aisles without food: their deals would crowd out the ones that matter for
# food preferences, as AH's non-food sections would (ingestion/ah/payloads.py).
NON_FOOD_CATEGORIES = frozenset({
    "Baby en kind", "Drogisterij en gezondheid", "Huishouden en dieren",
    "Non-food en servicebalie",
})  # fmt: skip


class _JumboModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", frozen=True)


class Tag(_JumboModel):
    """A label on a promotion. The deal itself, e.g. "2 voor 3,49", is a plain tag;
    an inverse one is a remark, such as "Alleen online" or "Alleen in de winkel"."""

    text: str
    inverse: bool = False


class Moment(_JumboModel):
    iso: datetime  # e.g. 2026-11-10T23:59:00+01:00, Dutch time


class Promotion(_JumboModel):
    id: str
    title: str  # e.g. "Campina Vla", "Alle Nalys"
    tags: list[Tag] = []
    start: Moment
    end: Moment
    url: str  # its own page, e.g. /aanbiedingen/campina-vla/3021834
    active: bool = True
    hidden: bool = False

    @property
    def mechanic(self) -> str | None:
        """The deal, as Jumbo words it: the first plain tag."""
        return next((tag.text for tag in self.tags if not tag.inverse), None)

    @property
    def online_only(self) -> bool:
        """Only for online orders, so not in a store: "Alleen online", "Online ..."."""
        return any(tag.inverse and "online" in tag.text.lower() for tag in self.tags)


class Category(_JumboModel):
    title: str | None = None
    promotions: list[Any] | None = None


class Section(_JumboModel):
    """A section holds promotions directly (the highlights) or per category (aisles)."""

    title: str | None = None
    promotions: list[Any] | None = None
    categories: list[Category] | None = None


class Runtime(_JumboModel):
    """One week of promotions, e.g. id "actieprijs_20261104-20261110"."""

    id: str
    sections: list[Section] = []


class _ActiveTab(_JumboModel):
    runtimes: list[Runtime]


class _NuTab(_JumboModel):
    active_tab: _ActiveTab


class _OverviewData(_JumboModel):
    nu_tab: _NuTab


class OverviewPage(_JumboModel):
    data: _OverviewData

    @property
    def runtimes(self) -> list[Runtime]:
        return self.data.nu_tab.active_tab.runtimes


class PricePerUnit(_JumboModel):
    price: int  # cents per unit
    unit: str  # "l", "kg", "pieces"


class Price(_JumboModel):
    price: int  # cents: the normal price
    promo_price: int | None = None  # cents: the price with the deal, when it has one
    price_per_unit: PricePerUnit | None = None


class Product(_JumboModel):
    title: str
    price: Price | None = None


def promotion_products(page: Any) -> list[Any]:
    """A promotion page's products, unvalidated. The page keeps them under
    ``data["promotion-detail:<id>"]["promotion"]["products"]``."""
    data = page.get("data", {}) if isinstance(page, dict) else {}
    for key, value in data.items():
        if key.startswith("promotion-detail:") and isinstance(value, dict):
            products = (value.get("promotion") or {}).get("products")
            return products if isinstance(products, list) else []
    return []


@dataclass
class JumboWeek:
    """The raw result of one fetch: the overview, and the promotion pages looked up."""

    overview: Any
    # Unpacked promotion pages by promotion id, and the ids whose lookup failed.
    promotions: dict[str, Any] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)

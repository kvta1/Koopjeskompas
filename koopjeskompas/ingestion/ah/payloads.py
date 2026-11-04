"""Pydantic models of AH's JSON, as observed. Only the fields we use are declared.

These are the anti-corruption layer: AH's shapes stop here and never reach the domain.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _AhModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", frozen=True)


# --- bonus metadata: which sections exist for which week -------------------

# AH bonus categories without food. Koopjeskompas ranks stores on food preferences,
# so deals on detergent or shampoo would only crowd out the deals that matter.
NON_FOOD_SECTIONS = frozenset({
    "AH Voordeelshop", "Baby en kind", "Drogisterij", "Gezondheid en sport",
    "Huisdier", "Huishouden", "Koken, tafelen, vrije tijd",
})  # fmt: skip


class SectionMetadata(_AhModel):
    url: str
    bonus_type: str
    description: str


class BonusTab(_AhModel):
    url_metadata_list: list[SectionMetadata]


class BonusPeriod(_AhModel):
    bonus_start_date: date
    bonus_end_date: date
    tabs: list[BonusTab]

    def food_sections(self) -> list[SectionMetadata]:
        """The NATIONAL (in-store, chain-wide) food sections, each listed once.

        Online-only, Gall & Gall and Etos sections don't apply in an AH store, and
        non-food categories don't apply to food preferences.
        """
        seen: dict[str, SectionMetadata] = {}
        for tab in self.tabs:
            for meta in tab.url_metadata_list:
                if (
                    meta.bonus_type == "NATIONAL"
                    and meta.description not in NON_FOOD_SECTIONS
                ):
                    seen.setdefault(meta.url, meta)
        return list(seen.values())


class BonusMetadata(_AhModel):
    periods: list[BonusPeriod]


# --- bonus sections: the deals themselves ----------------------------------


class Product(_AhModel):
    """One product on offer, e.g. "AH Spruitjes 500 gram" for "VOOR 0.99"."""

    title: str
    bonus_mechanism: str | None = None
    price_before_bonus: Decimal | None = None
    current_price: Decimal | None = None
    bonus_start_date: date | None = None
    bonus_end_date: date | None = None
    promotion_type: str | None = None


class BonusGroup(_AhModel):
    """A deal on a range, e.g. "Alle Unox rookworsten" for "25% KORTING".

    ``products`` is usually empty; nested items are validated one by one by the
    parser so one odd product can't sink the whole group.
    """

    segment_description: str
    category: str | None = None
    discount_description: str | None = None
    example_from_price: Decimal | None = None
    example_for_price: Decimal | None = None
    bonus_start_date: date | None = None
    bonus_end_date: date | None = None
    promotion_type: str | None = None
    products: list[Any] = []


class SectionItem(_AhModel):
    product: Product | None = None
    bonus_group: BonusGroup | None = None


class Section(_AhModel):
    """One bonus category. Items are validated one by one by the parser."""

    section_description: str | None = None  # the category, e.g. "Vlees"
    bonus_group_or_products: list[Any]


@dataclass
class BonusWeek:
    """The raw result of one fetch: the week's period and its section payloads."""

    period: BonusPeriod
    sections: list[Any]
    failed_sections: list[str] = field(default_factory=list)

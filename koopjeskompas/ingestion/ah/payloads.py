"""Pydantic models of AH's JSON, as observed. Only the fields we use are declared.

These are the anti-corruption layer: AH's shapes stop here and never reach the domain.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from koopjeskompas.domain.beer import is_beer


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
    # e.g. "normale prijs per kg €14.98"; the parser reads the kilo price from it.
    unit_price_description: str | None = None
    bonus_start_date: date | None = None
    bonus_end_date: date | None = None
    promotion_type: str | None = None


# Discount label codes whose discount depends on the product's price: "2 voor 12.00"
# says nothing until you know what one pizza normally costs. Ranges with these codes
# are looked up product by product; "25% korting" or "1+1 gratis" need no price.
PRICE_DEPENDENT_CODES = frozenset({
    "DISCOUNT_X_FOR_Y", "DISCOUNT_FIXED_PRICE", "DISCOUNT_AMOUNT", "DISCOUNT_WEIGHT",
})  # fmt: skip


class DiscountLabel(_AhModel):
    code: str


class BonusGroup(_AhModel):
    """A deal on a range, e.g. "Alle Unox rookworsten" for "25% KORTING".

    ``products`` is usually empty; nested items are validated one by one by the
    parser so one odd product can't sink the whole group. The ``segment_id`` is
    what the range lookup (``client.RANGE_QUERY``) asks for.
    """

    segment_id: int | None = None
    discount_labels: list[DiscountLabel] = []
    segment_description: str
    category: str | None = None
    discount_description: str | None = None
    example_from_price: Decimal | None = None
    example_for_price: Decimal | None = None
    bonus_start_date: date | None = None
    bonus_end_date: date | None = None
    promotion_type: str | None = None
    products: list[Any] = []

    @property
    def needs_product_prices(self) -> bool:
        """A range without products whose discount depends on a price."""
        return (
            self.segment_id is not None
            and not self.products
            and any(
                label.code in PRICE_DEPENDENT_CODES for label in self.discount_labels
            )
        )


class SectionItem(_AhModel):
    product: Product | None = None
    bonus_group: BonusGroup | None = None


class Section(_AhModel):
    """One bonus category. Items are validated one by one by the parser."""

    section_description: str | None = None  # the category, e.g. "Vlees"
    bonus_group_or_products: list[Any]


def ranges_to_look_up(sections: list[Any]) -> list[int]:
    """Segment ids of the ranges to look up product by product, each listed once:
    those whose discount depends on a price, and beer ranges, whose products the beer
    section compares by size and price per litre (PLAN.md §9.5).

    Items that don't validate are passed over here; the parser reports them.
    """
    ids: dict[int, None] = {}  # a dict keeps the order, unlike a set
    for payload in sections:
        if not isinstance(payload, dict):
            continue
        for raw_item in payload.get("bonusGroupOrProducts", []):
            try:
                group = SectionItem.model_validate(raw_item).bonus_group
            except ValidationError:
                continue
            if (
                group is not None
                and group.promotion_type in (None, "NATIONAL")
                and group.segment_id is not None
                and not group.products
                and (group.needs_product_prices or is_beer(group.segment_description))
            ):
                ids[group.segment_id] = None
    return list(ids)


# --- range lookups: the products of one range, from the GraphQL API --------


class Amount(_AhModel):
    amount: Decimal


class RangePrice(_AhModel):
    # "was" is the normal price. For "2 voor 12.00" it equals "now", because the
    # discount only applies at the checkout.
    was: Amount | None = None
    now: Amount | None = None


class RangeProductPayload(_AhModel):
    title: str
    sales_unit_size: str | None = None  # e.g. "450 g", "ca. 110 g", "570 ml"
    price_v2: RangePrice | None = None


class BonusPromotion(_AhModel):
    products: list[Any] = []  # validated one by one by the parser


class _PromotionsData(_AhModel):
    bonus_promotions: list[BonusPromotion]


class RangeResponse(_AhModel):
    data: _PromotionsData


@dataclass
class BonusWeek:
    """The raw result of one fetch: the week's period, sections and range lookups."""

    period: BonusPeriod
    sections: list[Any]
    failed_sections: list[str] = field(default_factory=list)
    # Raw range lookup responses by segment id, and the ids whose lookup failed.
    ranges: dict[int, Any] = field(default_factory=dict)
    failed_ranges: list[int] = field(default_factory=list)

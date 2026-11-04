"""Turns raw AH bonus sections into domain ``Deal`` models. Pure: no I/O.

Range deals get the products their range lookup returned (``BonusWeek.ranges``), each
with its own normal price. A malformed item is skipped with a reason; it never fails
the whole week. Deals whose
discount we can't determine (an unrecognised mechanic, or a price-based mechanic with
no normal price) are kept, logged and counted, so the mechanic table in
``domain/deal_mechanic.py`` can be extended deliberately instead of guessed.
"""

import logging
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from koopjeskompas.domain.deal_mechanic import is_scorable
from koopjeskompas.domain.models import Deal, RangeProduct
from koopjeskompas.ingestion.ah.payloads import (
    BonusGroup,
    BonusPeriod,
    BonusWeek,
    Product,
    RangeProductPayload,
    RangeResponse,
    Section,
    SectionItem,
)

logger = logging.getLogger(__name__)

CHAIN = "AH"

# Combideals are labelled just "BONUS"; their example prices carry the discount.
_PRICE_ONLY_MECHANICS = {"BONUS"}


@dataclass
class ParseResult:
    deals: list[Deal] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # Mechanic text -> how many deals carry it without a determinable discount,
    # either because the mechanic is unrecognised or a normal price is missing.
    no_discount: Counter[str] = field(default_factory=Counter)
    # Range deals that got their products from a lookup, and how many products.
    ranges_priced: int = 0
    range_products: int = 0


def parse_bonus_week(week: BonusWeek) -> ParseResult:
    result = ParseResult()
    seen: set[tuple[str, str | None, date, date]] = set()

    for payload in week.sections:
        for deal in _parse_section(payload, week, result):
            key = (
                deal.product_name,
                deal.mechanic_string,
                deal.valid_from,
                deal.valid_to,
            )
            if key in seen:
                continue
            seen.add(key)
            result.deals.append(deal)
            if deal.products:
                result.ranges_priced += 1
                result.range_products += len(deal.products)
            if not is_scorable(deal):
                mechanic = deal.mechanic_string or "(prices only)"
                logger.info("no discount for %r (%s)", deal.product_name, mechanic)
                result.no_discount[mechanic] += 1
    return result


def _parse_section(
    payload: Any, week: BonusWeek, result: ParseResult
) -> Iterator[Deal]:
    try:
        section = Section.model_validate(payload)
    except ValidationError as error:
        _skip(result, f"unexpected section shape: {_first_error(error)}")
        return

    category = section.section_description
    for raw_item in section.bonus_group_or_products:
        try:
            item = SectionItem.model_validate(raw_item)
            if item.product is not None:
                yield from _deals_from_product(
                    item.product, week.period, category, fallback=None
                )
            elif item.bonus_group is not None:
                yield from _deals_from_group(item.bonus_group, week, category, result)
            else:
                _skip(result, "item is neither a product nor a bonus group")
        except ValidationError as error:
            _skip(result, f"malformed item: {_first_error(error)}")


def _deals_from_group(
    group: BonusGroup,
    week: BonusWeek,
    category: str | None,
    result: ParseResult,
) -> Iterator[Deal]:
    if not _is_national(group.promotion_type):
        return
    period = week.period
    category = category or group.category
    if not group.products:
        looked_up = (
            week.ranges.get(group.segment_id) if group.segment_id is not None else None
        )
        yield _make_deal(
            name=group.segment_description,
            category=category,
            mechanic=group.discount_description,
            normal_price=group.example_from_price,
            deal_price=group.example_for_price,
            valid_from=group.bonus_start_date or period.bonus_start_date,
            valid_to=group.bonus_end_date or period.bonus_end_date,
            products=_range_products(looked_up, group.segment_description, result),
        )
        return
    for raw_product in group.products:
        try:
            product = Product.model_validate(raw_product)
        except ValidationError as error:
            where = f"product in {group.segment_description!r}"
            _skip(result, f"malformed {where}: {_first_error(error)}")
            continue
        yield from _deals_from_product(product, period, category, fallback=group)


def _deals_from_product(
    product: Product,
    period: BonusPeriod,
    category: str | None,
    fallback: BonusGroup | None,
) -> Iterator[Deal]:
    if not _is_national(product.promotion_type):
        return
    mechanic = product.bonus_mechanism
    if mechanic is None and fallback is not None:
        mechanic = fallback.discount_description
    yield _make_deal(
        name=product.title,
        category=category,
        mechanic=mechanic,
        normal_price=product.price_before_bonus,
        deal_price=product.current_price,
        valid_from=product.bonus_start_date or period.bonus_start_date,
        valid_to=product.bonus_end_date or period.bonus_end_date,
        normal_price_per_kg=price_per_kg(product.unit_price_description),
    )


def _make_deal(
    name: str,
    category: str | None,
    mechanic: str | None,
    normal_price: Decimal | None,
    deal_price: Decimal | None,
    valid_from: date,
    valid_to: date,
    normal_price_per_kg: Decimal | None = None,
    products: tuple[RangeProduct, ...] = (),
) -> Deal:
    if mechanic is not None and mechanic.strip().upper() in _PRICE_ONLY_MECHANICS:
        mechanic = None
    return Deal(
        chain=CHAIN,
        product_name=name,
        category=category,
        mechanic_string=mechanic,
        normal_price=normal_price,
        normal_price_per_kg=normal_price_per_kg,
        deal_price=deal_price,
        valid_from=valid_from,
        valid_to=valid_to,
        products=products,
    )


def _range_products(
    payload: Any, range_name: str, result: ParseResult
) -> tuple[RangeProduct, ...]:
    """The products of a range lookup response, each with its normal price.

    ``was`` is the normal price; ``now`` is the fallback, because for "2 voor 12.00"
    AH only applies the discount at the checkout and both are the same.
    """
    if payload is None:
        return ()
    try:
        response = RangeResponse.model_validate(payload)
    except ValidationError as error:
        _skip(result, f"unexpected lookup for {range_name!r}: {_first_error(error)}")
        return ()

    products: dict[str, RangeProduct] = {}
    for promotion in response.data.bonus_promotions:
        for raw_product in promotion.products:
            try:
                product = RangeProductPayload.model_validate(raw_product)
            except ValidationError as error:
                where = f"product in {range_name!r}"
                _skip(result, f"malformed {where}: {_first_error(error)}")
                continue
            prices = product.price_v2
            price = (prices.was or prices.now) if prices else None
            if not price or price.amount <= 0:
                _skip(result, f"no price for {product.title!r} in {range_name!r}")
                continue
            products.setdefault(
                product.title,
                RangeProduct(
                    name=product.title,
                    normal_price=price.amount,
                    normal_price_per_kg=_price_per_kg_from_size(
                        price.amount, product.sales_unit_size
                    ),
                ),
            )
    return tuple(products.values())


_GRAMS_RE = re.compile(
    r"(?:ca\.?\s*)?(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>g|gram|kg|kilo)"
)


def _price_per_kg_from_size(price: Decimal, size: str | None) -> Decimal | None:
    """€3.49 for "ca. 110 g" is €31.73 per kilo; None for "570 ml" or "2 x 100 g"."""
    if size is None:
        return None
    match = _GRAMS_RE.fullmatch(size.strip().lower())
    if match is None:
        return None
    grams = Decimal(match["qty"].replace(",", "."))
    if match["unit"] in ("kg", "kilo"):
        grams *= 1000
    if grams == 0:
        return None
    return (price * 1000 / grams).quantize(Decimal("0.01"))


_PER_KG_RE = re.compile(r"per (?:kg|kilo)\s*€\s*(?P<price>\d+(?:[.,]\d{1,2})?)")


def price_per_kg(unit_price_description: str | None) -> Decimal | None:
    """The kilo price in AH's "normale prijs per kg €14.98", or None.

    Other units ("per liter") are left out: AH's per-weight deals are all in grams.
    """
    if unit_price_description is None:
        return None
    match = _PER_KG_RE.search(unit_price_description.lower())
    if match is None:
        return None
    price = Decimal(match["price"].replace(",", "."))
    return price if price > 0 else None


def _is_national(promotion_type: str | None) -> bool:
    # Items inside a NATIONAL section sometimes omit the field; trust the section then.
    return promotion_type in (None, "NATIONAL")


def _skip(result: ParseResult, reason: str) -> None:
    logger.warning("skipping AH item: %s", reason)
    result.skipped.append(reason)


def _first_error(error: ValidationError) -> str:
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}"

"""Turns raw AH bonus sections into domain ``Deal`` models. Pure: no I/O.

A malformed item is skipped with a reason; it never fails the whole week. Deals whose
discount we can't determine (an unrecognised mechanic, or a price-based mechanic with
no normal price) are kept, logged and counted, so the mechanic table in
``domain/deal_mechanic.py`` can be extended deliberately instead of guessed.
"""

import logging
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from koopjeskompas.domain.deal_mechanic import deal_discount
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.ah.payloads import (
    BonusGroup,
    BonusPeriod,
    BonusWeek,
    Product,
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


def parse_bonus_week(week: BonusWeek) -> ParseResult:
    result = ParseResult()
    seen: set[tuple[str, str | None, date, date]] = set()

    for payload in week.sections:
        for deal in _parse_section(payload, week.period, result):
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
            if deal_discount(deal) is None:
                mechanic = deal.mechanic_string or "(prices only)"
                logger.info("no discount for %r (%s)", deal.product_name, mechanic)
                result.no_discount[mechanic] += 1
    return result


def _parse_section(
    payload: Any, period: BonusPeriod, result: ParseResult
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
                    item.product, period, category, fallback=None
                )
            elif item.bonus_group is not None:
                yield from _deals_from_group(item.bonus_group, period, category, result)
            else:
                _skip(result, "item is neither a product nor a bonus group")
        except ValidationError as error:
            _skip(result, f"malformed item: {_first_error(error)}")


def _deals_from_group(
    group: BonusGroup,
    period: BonusPeriod,
    category: str | None,
    result: ParseResult,
) -> Iterator[Deal]:
    if not _is_national(group.promotion_type):
        return
    category = category or group.category
    if not group.products:
        yield _make_deal(
            name=group.segment_description,
            category=category,
            mechanic=group.discount_description,
            normal_price=group.example_from_price,
            deal_price=group.example_for_price,
            valid_from=group.bonus_start_date or period.bonus_start_date,
            valid_to=group.bonus_end_date or period.bonus_end_date,
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
    )


def _make_deal(
    name: str,
    category: str | None,
    mechanic: str | None,
    normal_price: Decimal | None,
    deal_price: Decimal | None,
    valid_from: date,
    valid_to: date,
) -> Deal:
    if mechanic is not None and mechanic.strip().upper() in _PRICE_ONLY_MECHANICS:
        mechanic = None
    return Deal(
        chain=CHAIN,
        product_name=name,
        category=category,
        mechanic_string=mechanic,
        normal_price=normal_price,
        deal_price=deal_price,
        valid_from=valid_from,
        valid_to=valid_to,
    )


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

"""Turn the tiles of Lidl's deals page into ``Deal``s. Pure: no I/O.

Lidl shows a deal's price and, often, the price it replaces, so most discounts need
no further lookup. Each tile becomes at most one deal, the first that applies:

1. a Lidl Plus price: only with Lidl's free app, so the deal's name says
   "(met Lidl Plus)"; it counts like any other (decided 2026-11-11);
2. a price with a struck-through old price: a discount at the till;
3. a price for a limited time but no old price (a week's action, an XXL pack):
   kept, but without a normal price it scores zero, as AH's and Jumbo's would;
4. otherwise, the regular assortment at its regular price: not a deal, left out.

Each deal reads "voor 1,99", the wording the domain already understands, with the old
price as the normal price. Lidl's times are UTC: a deal from 2026-11-04T23:00Z starts
on 5 November in the Netherlands, so dates are taken in Dutch time.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from koopjeskompas.domain.deal_mechanic import is_scorable
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.lidl.payloads import NON_FOOD, GridItem, Price

logger = logging.getLogger(__name__)

CHAIN = "Lidl"
DUTCH_TIME = ZoneInfo("Europe/Amsterdam")
LIDL_PLUS = "met Lidl Plus"


@dataclass
class ParseResult:
    deals: list[Deal] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # tiles that couldn't be read
    left_out: Counter[str] = field(default_factory=Counter)  # on purpose, by reason
    no_discount: Counter[str] = field(default_factory=Counter)
    lidl_plus: int = 0  # deals that need the Lidl Plus app


def parse_tiles(tiles: list[Any]) -> ParseResult:
    result = ParseResult()
    seen: set[int] = set()
    for raw in tiles:
        try:
            item = GridItem.model_validate(raw)
        except ValidationError as error:
            logger.warning("skipping a tile that doesn't validate: %s", error)
            label = str(raw.get("fullTitle")) if isinstance(raw, dict) else repr(raw)
            result.skipped.append(label[:40])
            continue
        if item.product_id in seen:
            continue
        seen.add(item.product_id)

        deal = _deal(item, result)
        if deal is None:
            continue
        if not is_scorable(deal):
            result.no_discount[deal.mechanic_string or "(no price)"] += 1
        result.deals.append(deal)
    return result


def _deal(item: GridItem, result: ParseResult) -> Deal | None:
    if item.keyfacts.analytics_category in NON_FOOD:
        result.left_out["not food"] += 1
        return None
    prices = item.prices
    lidl_plus = prices.current_lidl_plus_price
    if lidl_plus is not None and _discounted(lidl_plus.price):
        result.lidl_plus += 1
        label = lidl_plus.lidl_plus_text or LIDL_PLUS
        return _make(item, lidl_plus.price, name=f"{item.name} ({label})")
    current = prices.current_price
    if _discounted(current) or not current.indefinite:
        return _make(item, current, name=item.name)
    result.left_out["regular price, not a deal"] += 1
    return None


def _discounted(price: Price) -> bool:
    return price.old_price is not None and price.old_price > price.price


def _make(item: GridItem, price: Price, name: str) -> Deal:
    return Deal(
        chain=CHAIN,
        product_name=name,
        category=item.category,
        mechanic_string=f"voor {price.price:.2f}".replace(".", ","),
        normal_price=price.old_price,
        deal_price=price.price,
        valid_from=_dutch_date(price.start_date) or date.min,
        valid_to=_dutch_date(price.end_date) or date.max,
    )


def _dutch_date(moment: datetime | None) -> date | None:
    if moment is None or moment.year >= 9999:
        return None
    return moment.astimezone(DUTCH_TIME).date()

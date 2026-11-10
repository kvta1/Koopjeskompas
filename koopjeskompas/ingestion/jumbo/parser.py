"""Turn Jumbo's page data into ``Deal``s. Pure: no I/O, so tests replay saved pages.

Each promotion becomes one deal. A promotion whose discount depends on a price ("2
voor 3,49") gets the products from its own page, with their normal prices, so it is
scored as a range deal: the median over its products that pass the diet filters,
like AH's ranges. Without that page it is kept, but scores zero.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from koopjeskompas.domain.deal_mechanic import (
    UnknownMechanicError,
    is_scorable,
    parse_deal_mechanic,
)
from koopjeskompas.domain.models import Deal, RangeProduct
from koopjeskompas.ingestion.jumbo.payloads import (
    HIGHLIGHTS,
    NON_FOOD_CATEGORIES,
    JumboWeek,
    OverviewPage,
    Product,
    Promotion,
    promotion_products,
)

logger = logging.getLogger(__name__)

CHAIN = "Jumbo"


@dataclass
class ParseResult:
    deals: list[Deal] = field(default_factory=list)
    # Items that couldn't be read, each also logged as a warning.
    skipped: list[str] = field(default_factory=list)
    # Promotions left out on purpose, by reason: online only, not food, ...
    left_out: Counter[str] = field(default_factory=Counter)
    no_discount: Counter[str] = field(default_factory=Counter)
    priced: int = 0  # promotions priced per product, from their own page
    products: int = 0


@dataclass
class _Found:
    promotion: Promotion
    category: str | None


def in_store_food_promotions(overview: Any, result: ParseResult) -> list[_Found]:
    """The promotions that apply in a store and are food, each once, in page order.

    A promotion appears in the highlights and in its aisle; it's kept once, with the
    aisle as its category.
    """
    page = OverviewPage.model_validate(overview)
    found: dict[str, _Found] = {}
    for runtime in page.runtimes:
        for section in runtime.sections:
            groups = [(section.title, section.promotions or [])]
            groups += [(c.title, c.promotions or []) for c in section.categories or []]
            for title, raw_promotions in groups:
                category = None if title in HIGHLIGHTS else title
                for raw in raw_promotions:
                    promotion = _validate(raw, result)
                    if promotion is None:
                        continue
                    seen = found.setdefault(promotion.id, _Found(promotion, category))
                    seen.category = seen.category or category

    kept = []
    for item in found.values():
        reason = _left_out_because(item)
        if reason:
            result.left_out[reason] += 1
        else:
            kept.append(item)
    return kept


def promotions_needing_prices(overview: Any) -> list[Promotion]:
    """The kept promotions whose discount can't be worked out without a price."""
    found = in_store_food_promotions(overview, ParseResult())
    return [f.promotion for f in found if _needs_price(f.promotion.mechanic)]


def parse_week(week: JumboWeek) -> ParseResult:
    result = ParseResult()
    for item in in_store_food_promotions(week.overview, result):
        promotion = item.promotion
        products = _products(week.promotions.get(promotion.id), result)
        if products:
            result.priced += 1
            result.products += len(products)
        deal = Deal(
            chain=CHAIN,
            product_name=promotion.title,
            category=item.category,
            mechanic_string=promotion.mechanic,
            valid_from=promotion.start.iso.date(),
            valid_to=promotion.end.iso.date(),
            products=tuple(products),
        )
        if not is_scorable(deal):
            result.no_discount[promotion.mechanic or "(no deal text)"] += 1
        result.deals.append(deal)
    return result


def _validate(raw: Any, result: ParseResult) -> Promotion | None:
    try:
        return Promotion.model_validate(raw)
    except ValidationError as error:
        logger.warning("skipping a promotion that doesn't validate: %s", error)
        label = str(raw.get("id")) if isinstance(raw, dict) else repr(raw)
        result.skipped.append(label[:40])
        return None


def _left_out_because(item: _Found) -> str | None:
    promotion = item.promotion
    if promotion.hidden or not promotion.active:
        return "hidden or inactive"
    if promotion.online_only:
        return "online only"
    if item.category in NON_FOOD_CATEGORIES:
        return "not food"
    if promotion.mechanic is None:
        return "no deal text"
    return None


def _needs_price(mechanic: str | None) -> bool:
    """Whether ``mechanic`` is understood, but only with a normal price to go on."""
    if mechanic is None:
        return False
    try:
        parse_deal_mechanic(mechanic, None)
    except UnknownMechanicError:
        return False  # a price wouldn't help ("Gratis beanie bij 2 stuks")
    except ValueError:
        return True  # "2 voor 3,49": needs to know what one costs
    return False  # "1+1 gratis": the discount is in the words


def _products(page: Any, result: ParseResult) -> list[RangeProduct]:
    """The products on a promotion's page that are still sold and have a price."""
    if page is None:
        return []
    products = []
    for raw in promotion_products(page):
        try:
            product = Product.model_validate(raw)
        except ValidationError as error:
            logger.warning("skipping a product that doesn't validate: %s", error)
            result.skipped.append(f"product {raw!r:.40}")
            continue
        price = product.price.price if product.price else 0
        delisted = product.availability and product.availability.reason == "DELISTED"
        if price > 0 and not delisted:
            products.append(
                RangeProduct(name=product.title, normal_price=Decimal(price) / 100)
            )
    return products

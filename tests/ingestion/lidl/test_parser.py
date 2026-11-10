"""Lidl's deal tiles into deals, on the page captured on 2026-11-10."""

import copy
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from koopjeskompas.domain.deal_mechanic import deal_discount
from koopjeskompas.ingestion.lidl.parser import parse_tiles
from tests.lidl_fixtures import tile, tiles


def deals_by_name(page_tiles: list[Any]) -> dict[str, Any]:
    return {d.product_name: d for d in parse_tiles(page_tiles).deals}


def test_the_whole_page() -> None:
    result = parse_tiles(tiles())
    # 47 tiles: 6 not food; 19 Lidl Plus deals, 3 with an old price, 19 week
    # actions without one (kept, unscored).
    assert len(result.deals) == 41
    assert result.left_out == {"not food": 6}
    assert result.lidl_plus == 19
    assert sum(result.no_discount.values()) == 19
    assert result.skipped == []
    assert sum(deal_discount(d) is not None for d in result.deals) == 22


def test_a_lidl_plus_deal_says_so_and_scores() -> None:
    (deal,) = parse_tiles([tile("Handsinaasappels")]).deals
    assert deal.product_name == "Handsinaasappels (met Lidl Plus)"
    assert deal.chain == "Lidl"
    assert deal.mechanic_string == "voor 1,99"
    assert deal.normal_price == Decimal("2.89")
    assert deal_discount(deal) == pytest.approx(Decimal("0.3114"), abs=1e-4)


def test_a_struck_through_price_is_the_normal_price() -> None:
    (deal,) = parse_tiles([tile("Zwagerman Kipfilet")]).deals
    assert deal.product_name == "Zwagerman Kipfilet naturel"  # no Lidl Plus here
    assert (deal.normal_price, deal.deal_price) == (Decimal("2.49"), Decimal("1.99"))
    assert deal_discount(deal) == pytest.approx(Decimal("0.2008"), abs=1e-4)


def test_dates_are_dutch_not_utc() -> None:
    # Lidl says 2026-11-04T23:00Z to 2026-11-15T22:59:59Z: 5 to 15 November here.
    (deal,) = parse_tiles([tile("Zwagerman Kipfilet")]).deals
    assert (deal.valid_from, deal.valid_to) == (date(2026, 11, 5), date(2026, 11, 15))


def test_a_weeks_action_without_an_old_price_is_kept_but_unscored() -> None:
    (deal,) = parse_tiles([tile("Croky chips")]).deals
    assert deal.mechanic_string == "voor 1,99"
    assert deal.normal_price is None
    assert deal_discount(deal) is None


def test_the_regular_assortment_is_not_a_deal() -> None:
    # Oranges without their Lidl Plus price: a regular price, with no end.
    regular = copy.deepcopy(tile("Handsinaasappels"))
    for region in regular["regionsPrices"].values():
        del region["currentLidlPlusPrice"]
    result = parse_tiles([regular])
    assert result.deals == []
    assert result.left_out == {"regular price, not a deal": 1}


def test_names_and_categories() -> None:
    deals = deals_by_name(tiles())
    # The full title, with brand, without Lidl's leading "- ".
    assert "Boerenbruin heel" in deals
    assert "Bellarom Koffiecups" in deals
    assert deals["Boerenbruin heel"].category == "Vers brood"


def test_an_unreadable_tile_is_skipped_not_fatal() -> None:
    result = parse_tiles([{"fullTitle": "No prices"}, tile("Croky chips")])
    assert result.skipped == ["No prices"]
    assert len(result.deals) == 1


def test_a_tile_listed_twice_counts_once() -> None:
    croky = tile("Croky chips")
    assert len(parse_tiles([croky, croky]).deals) == 1

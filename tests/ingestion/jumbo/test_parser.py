"""Jumbo's page data into deals, on pages captured on 2026-11-10."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from koopjeskompas.domain.deal_mechanic import product_discount
from koopjeskompas.ingestion.jumbo.parser import (
    ParseResult,
    in_store_food_promotions,
    parse_week,
    promotions_needing_prices,
)
from koopjeskompas.ingestion.jumbo.payloads import JumboWeek
from koopjeskompas.ingestion.nuxt import page_data
from tests.jumbo_fixtures import overview_data, pack, vla_page

VLA = "3021834"


@pytest.fixture
def week() -> JumboWeek:
    return JumboWeek(overview=overview_data(), promotions={VLA: page_data(vla_page())})


def deals_by_name(week: JumboWeek) -> dict[str, Any]:
    return {deal.product_name: deal for deal in parse_week(week).deals}


def test_each_in_store_food_promotion_becomes_one_deal(week: JumboWeek) -> None:
    assert list(deals_by_name(week)) == [
        "Alle Apetina, Castello of Garlan",
        "Campina Vla",
        "Mango",
        "Alle Kanzi appels",
    ]


def test_what_is_left_out_and_why() -> None:
    result = ParseResult()
    in_store_food_promotions(overview_data(), result)
    # Online only: Campina Optimel, the beanie. Not food: Nalys, Dove.
    assert result.left_out == {"online only": 2, "not food": 2}


def test_a_highlighted_promotion_takes_its_aisle_as_category(week: JumboWeek) -> None:
    # Apetina is listed first under "Nu in de aanbieding", then in its aisle.
    apetina = deals_by_name(week)["Alle Apetina, Castello of Garlan"]
    assert apetina.category == "Vleeswaren, kaas en tapas"


def test_the_deal_and_its_dates(week: JumboWeek) -> None:
    deals = deals_by_name(week)
    vla = deals["Campina Vla"]
    assert vla.chain == "Jumbo"
    assert vla.mechanic_string == "2 voor 3,49"
    assert (vla.valid_from, vla.valid_to) == (date(2026, 11, 4), date(2026, 11, 10))
    # Next week's promotions come along: they count from Wednesday.
    kanzi = deals["Alle Kanzi appels"]
    assert (kanzi.valid_from, kanzi.valid_to) == (
        date(2026, 11, 11),
        date(2026, 11, 17),
    )


def test_only_promotions_that_need_a_price_are_looked_up() -> None:
    titles = [p.title for p in promotions_needing_prices(overview_data())]
    # Not "25% korting" (in the words), "2,49 per kilo" (not understood yet), nor
    # the online-only and non-food ones.
    assert titles == ["Campina Vla", "Mango"]


def test_a_looked_up_promotion_is_priced_per_product(week: JumboWeek) -> None:
    vla = deals_by_name(week)["Campina Vla"]
    # 17 on the page; 2 no longer sold ("DELISTED") don't count.
    assert len(vla.products) == 15
    first = vla.products[0]
    assert first.name == "Campina Bolletjes Vla Vanille Smaak 1 L"
    assert first.normal_price == Decimal("2.39")  # from 239 cents
    # Two for 3,49 instead of 2 × 2,39 saves 27%.
    assert product_discount(vla, first) == pytest.approx(Decimal("0.2699"), abs=1e-4)


def test_what_scores_zero_is_counted(week: JumboWeek) -> None:
    result = parse_week(week)
    assert result.priced == 1
    assert result.products == 15
    # Mango's page wasn't fetched; per-kilo deals aren't understood yet.
    assert result.no_discount == {"voor 1,49": 1, "2,49 per kilo": 1}


def test_an_unreadable_promotion_is_skipped_not_fatal() -> None:
    overview = overview_data()
    section = overview["data"]["nuTab"]["activeTab"]["runtimes"][0]["sections"][0]
    section["promotions"].insert(0, {"id": "broken", "title": "No dates"})

    result = parse_week(JumboWeek(overview=overview))

    assert result.skipped == ["broken"]
    assert len(result.deals) == 4


def test_the_packer_in_the_tests_matches_the_unpacker() -> None:
    # Client tests build pages with ``pack``; it must write what ``unpack`` reads.
    from koopjeskompas.ingestion.nuxt import unpack

    assert unpack(pack(overview_data())) == overview_data()

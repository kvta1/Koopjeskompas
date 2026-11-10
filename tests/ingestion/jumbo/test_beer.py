"""Jumbo beer promotions: their pages are fetched, and their products compared per litre."""

import copy
from datetime import date
from decimal import Decimal
from typing import Any

from koopjeskompas.domain.beer import Packaging, beer_offers
from koopjeskompas.ingestion.jumbo.parser import parse_week, promotions_to_look_up
from koopjeskompas.ingestion.jumbo.payloads import JumboWeek
from koopjeskompas.ingestion.nuxt import unpack_json
from tests.beer_fixtures import jumbo_promotion_data
from tests.jumbo_fixtures import overview_data

PILS = "3022187"


def overview_with_pils() -> Any:
    """The trimmed overview, plus this week's pils promotion in the beer aisle."""
    overview = copy.deepcopy(overview_data())
    aisles = overview["data"]["nuTab"]["activeTab"]["runtimes"][0]["sections"][1]
    aisles["categories"].append(
        {
            "title": "Bier en wijn",
            "promotions": [
                {
                    "id": PILS,
                    "title": "Pils van Alfa, Warsteiner, Stella Artois of Corona",
                    "tags": [{"text": "25% korting", "inverse": False}],
                    "start": {"iso": "2026-11-04T00:01:00+01:00"},
                    "end": {"iso": "2026-11-10T23:59:00+01:00"},
                    "url": f"/aanbiedingen/pils-van-alfa-warsteiner-stella-artois-of-corona/{PILS}",
                }
            ],
        }
    )
    return overview


def test_beer_promotions_are_fetched_even_when_their_discount_needs_no_price() -> None:
    titles = [p.title for p in promotions_to_look_up(overview_with_pils())]
    assert "Pils van Alfa, Warsteiner, Stella Artois of Corona" in titles


def test_beer_products_become_offers_per_packaging() -> None:
    week = JumboWeek(
        overview=overview_with_pils(),
        promotions={PILS: unpack_json(jumbo_promotion_data(PILS))},
    )
    offers = beer_offers(parse_week(week).deals, date(2026, 11, 10))
    by_name = {o.product: o for o in offers}

    crate = by_name["Stella Artois Krat 24x330ML"]
    assert crate.packaging is Packaging.CRATE
    assert crate.chain == "Jumbo"
    assert crate.deal_price == Decimal("17.99")  # 25% off 23.99
    assert crate.price_per_litre == Decimal("2.27")  # 17.99 / 7.92 l
    assert by_name["Alfa Edel Pils Blikken 6 x 33 cl"].packaging is Packaging.CAN
    assert (
        by_name["Corona Extra Bier Pils Flessen 20x25cl"].packaging is Packaging.BOTTLE
    )
    assert by_name["Warsteiner - Alcoholvrij <0.5% - Fles - 6 x 330ML"].alcohol_free


def test_the_volume_comes_from_jumbos_own_prices() -> None:
    week = JumboWeek(
        overview=overview_with_pils(),
        promotions={PILS: unpack_json(jumbo_promotion_data(PILS))},
    )
    pils = next(
        d for d in parse_week(week).deals if d.product_name.startswith("Pils van")
    )
    alfa = next(
        p for p in pils.products if p.name == "Alfa Edel Pils Blikken 6 x 33 cl"
    )
    # Jumbo: normal 6.39, deal 4.79, 2.42 per litre (of the deal price): 1.979 l.
    assert alfa.litres == Decimal("1.979")

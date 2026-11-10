"""AH beer ranges: looked up product by product, each size kept, on real lookups."""

from datetime import date
from typing import Any

import pytest

from koopjeskompas.domain.beer import Packaging, beer_offers
from koopjeskompas.ingestion.ah.parser import parse_bonus_week
from koopjeskompas.ingestion.ah.payloads import (
    BonusMetadata,
    BonusPeriod,
    BonusWeek,
    ranges_to_look_up,
)
from tests.ah_fixtures import load_ah_fixture
from tests.beer_fixtures import ah_range

HEINEKEN = 824679


def group(segment_id: int, name: str, mechanic: str, code: str) -> dict[str, Any]:
    return {
        "bonusGroup": {
            "segmentId": segment_id,
            "segmentDescription": name,
            "discountDescription": mechanic,
            "discountLabels": [{"code": code}],
            "bonusStartDate": "2026-11-09",
            "bonusEndDate": "2026-11-15",
            "promotionType": "NATIONAL",
            "products": [],
        }
    }


SECTION = {
    "sectionDescription": "Bier, wijn, aperitieven",
    "bonusGroupOrProducts": [
        group(
            HEINEKEN, "Alle Heineken multipacks*", "25% KORTING", "DISCOUNT_PERCENTAGE"
        ),
        group(
            824710,
            "Diverse prijswinnende wijnen",
            "2E HALVE PRIJS",
            "DISCOUNT_ONE_HALF_PRICE",
        ),
    ],
}


@pytest.fixture
def period() -> BonusPeriod:
    return BonusMetadata.model_validate(load_ah_fixture("metadata.json")).periods[0]


def test_beer_ranges_are_looked_up_even_when_their_discount_needs_no_price() -> None:
    # 25% needs no price, but the beer section needs each product's size and price;
    # the wine range, with a discount in its words too, isn't looked up.
    assert ranges_to_look_up([SECTION]) == [HEINEKEN]


def test_each_size_of_a_product_is_its_own_product(period: BonusPeriod) -> None:
    week = BonusWeek(
        period=period, sections=[SECTION], ranges={HEINEKEN: ah_range(HEINEKEN)}
    )
    heineken = next(
        d
        for d in parse_bonus_week(week).deals
        if d.product_name.startswith("Alle Heineken")
    )

    sixpacks = sorted(
        (p.unit_size or "")
        for p in heineken.products
        if p.name == "Heineken Premium pilsener 6-pack"
    )
    assert sixpacks == ["6 x 0,33 l", "6 x 0,5 l"]  # same title, two products
    assert len(heineken.products) == 22


def test_the_lookup_becomes_beer_offers(period: BonusPeriod) -> None:
    week = BonusWeek(
        period=period, sections=[SECTION], ranges={HEINEKEN: ah_range(HEINEKEN)}
    )
    offers = beer_offers(parse_bonus_week(week).deals, date(2026, 11, 10))

    assert {o.chain for o in offers} == {"AH"}
    assert {o.packaging for o in offers} == {Packaging.CAN, Packaging.BOTTLE}
    cheapest = offers[0]
    assert cheapest.price_per_litre == min(o.price_per_litre for o in offers)
    tray = next(o for o in offers if o.product == "Heineken Premium pilsener 24-pack")
    assert tray.packaging is Packaging.CAN  # 24 x 0,33 l: a tray of cans
    assert tray.size_text == "24 x 0,33 l"

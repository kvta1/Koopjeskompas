"""Parser tests against real AH responses captured on 2026-10-18 (images trimmed)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from koopjeskompas.domain.deal_mechanic import deal_discount
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.ah.parser import parse_bonus_week
from koopjeskompas.ingestion.ah.payloads import (
    NON_FOOD_SECTIONS,
    BonusMetadata,
    BonusPeriod,
    BonusWeek,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ah"
SECTIONS = ["section_groente_aardappelen.json", "section_vlees.json"]


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def period() -> BonusPeriod:
    return BonusMetadata.model_validate(load("metadata.json")).periods[0]


def week_of(period: BonusPeriod, *sections: Any) -> BonusWeek:
    return BonusWeek(period=period, sections=list(sections))


def by_name(deals: list[Deal]) -> dict[str, Deal]:
    return {d.product_name: d for d in deals}


def test_metadata_lists_only_national_food_sections(period: BonusPeriod) -> None:
    sections = period.food_sections()
    # 26 national sections that week, 6 of them non-food.
    assert len(sections) == 20
    assert all("promotionType=NATIONAL" in s.url for s in sections)
    descriptions = {s.description for s in sections}
    assert "Vlees" in descriptions
    assert not descriptions & NON_FOOD_SECTIONS


def test_parses_every_item_of_the_real_sections(period: BonusPeriod) -> None:
    result = parse_bonus_week(week_of(period, *(load(n) for n in SECTIONS)))
    assert len(result.deals) == 23
    assert result.skipped == []
    assert {d.chain for d in result.deals} == {"AH"}
    assert {(d.valid_from, d.valid_to) for d in result.deals} == {
        (date(2026, 10, 12), date(2026, 10, 18))
    }


@pytest.mark.parametrize(
    ("name", "mechanic", "normal_price", "deal_price", "discount"),
    [
        # A single product with a fixed deal price.
        ("AH Spruitjes 500 gram", "VOOR 0.99", "1.49", None, "0.3356"),
        # A "stapel" deal: four for 2.49 at 0.95 each.
        ("AH Paprika rood", "4 stapelen voor 2.49", "0.95", None, "0.3447"),
        ("AH Witlof zak 4 stuks", "30% korting", "2.29", "1.6", "0.3"),
        # A bonus group: a whole range, no prices.
        ("Alle Unox rookworsten", "25% KORTING", None, None, "0.25"),
        # A combideal: labelled "BONUS", priced through the example prices.
        (
            "Combideal voor 7.50: AH Verspakket nacho bowl Mexicaanse stijl",
            None,
            "12.87",
            "7.5",
            "0.4172",
        ),
    ],
)
def test_maps_items_to_deals(
    period: BonusPeriod,
    name: str,
    mechanic: str | None,
    normal_price: str | None,
    deal_price: str | None,
    discount: str,
) -> None:
    result = parse_bonus_week(week_of(period, *(load(n) for n in SECTIONS)))
    deal = by_name(result.deals)[name]
    assert deal.mechanic_string == mechanic
    assert deal.normal_price == (Decimal(normal_price) if normal_price else None)
    assert deal.deal_price == (Decimal(deal_price) if deal_price else None)
    found = deal_discount(deal)
    assert found is not None
    assert found.quantize(Decimal("0.0001")) == Decimal(discount)


def test_deals_carry_their_section_category(period: BonusPeriod) -> None:
    result = parse_bonus_week(week_of(period, *(load(n) for n in SECTIONS)))
    deals = by_name(result.deals)
    assert deals["Wahid"].category == "Vlees"
    assert deals["AH Spruitjes 500 gram"].category == "Groente, aardappelen"


def test_counts_deals_without_a_determinable_discount(period: BonusPeriod) -> None:
    result = parse_bonus_week(week_of(period, *(load(n) for n in SECTIONS)))
    assert result.no_discount == {
        # Group deals priced per pack, with no normal price to compare against.
        "2 VOOR 2.49": 1,
        "2 VOOR 2.99": 1,
        "2 VOOR 4.00": 1,
        "3 VOOR 6.00": 1,
        "VOOR 2.49": 1,
        "1 EURO KORTING": 1,
        # A per-weight price: unrecognised on purpose.
        "100 GRAM VOOR 2.99": 1,
    }


def test_malformed_items_are_skipped_not_fatal(period: BonusPeriod) -> None:
    section = load("section_vlees.json")
    section["bonusGroupOrProducts"] += [
        {"product": {"bonusMechanism": "25% KORTING"}},  # no title
        {"somethingNew": {}},
        {"product": {"title": "Kaas", "priceBeforeBonus": 0}},  # invalid price
    ]
    result = parse_bonus_week(week_of(period, section, {"unexpected": "shape"}))
    assert len(result.deals) == 10
    assert len(result.skipped) == 4


def test_non_national_items_are_ignored(period: BonusPeriod) -> None:
    section = {
        "bonusGroupOrProducts": [
            {"product": {"title": "Online only", "promotionType": "AHONLINE"}},
            {
                "bonusGroup": {
                    "segmentDescription": "Etos",
                    "promotionType": "ETOS",
                    "discountDescription": "25% KORTING",
                }
            },
            {"product": {"title": "In store", "bonusMechanism": "25% korting"}},
        ]
    }
    result = parse_bonus_week(week_of(period, section))
    assert [d.product_name for d in result.deals] == ["In store"]


def test_nested_group_products_fall_back_to_the_group_mechanic(
    period: BonusPeriod,
) -> None:
    section = {
        "bonusGroupOrProducts": [
            {
                "bonusGroup": {
                    "segmentDescription": "Alle hummus",
                    "discountDescription": "2E HALVE PRIJS",
                    "products": [
                        {"title": "Hummus naturel"},
                        {"title": "Hummus pikant", "bonusMechanism": "25% korting"},
                        {"no": "title"},
                    ],
                }
            }
        ]
    }
    result = parse_bonus_week(week_of(period, section))
    deals = by_name(result.deals)
    assert deals["Hummus naturel"].mechanic_string == "2E HALVE PRIJS"
    assert deals["Hummus pikant"].mechanic_string == "25% korting"
    assert len(result.skipped) == 1


def test_duplicate_deals_across_sections_are_kept_once(period: BonusPeriod) -> None:
    section = load("section_vlees.json")
    result = parse_bonus_week(week_of(period, section, section))
    assert len(result.deals) == 10

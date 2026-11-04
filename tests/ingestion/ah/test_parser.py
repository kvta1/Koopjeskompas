"""Parser tests against real AH responses captured on 2026-10-18 (images trimmed)."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from koopjeskompas.domain.deal_mechanic import deal_discount
from koopjeskompas.domain.models import Deal, Diet, Preferences
from koopjeskompas.domain.scoring import score_deals
from koopjeskompas.ingestion.ah.parser import parse_bonus_week, price_per_kg
from koopjeskompas.ingestion.ah.payloads import (
    NON_FOOD_SECTIONS,
    BonusMetadata,
    BonusPeriod,
    BonusWeek,
)
from tests.ah_fixtures import load_ah_fixture

SECTIONS = ["section_groente_aardappelen.json", "section_vlees.json"]


@pytest.fixture
def period() -> BonusPeriod:
    return BonusMetadata.model_validate(load_ah_fixture("metadata.json")).periods[0]


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
    result = parse_bonus_week(week_of(period, *(load_ah_fixture(n) for n in SECTIONS)))
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
        # A per-weight price: €29.90/kg against a normal €36.50/kg.
        ("AH Kogelbiefstuk 2 stuks", "100 GRAM VOOR 2.99", "9.49", None, "0.1808"),
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
    result = parse_bonus_week(week_of(period, *(load_ah_fixture(n) for n in SECTIONS)))
    deal = by_name(result.deals)[name]
    assert deal.mechanic_string == mechanic
    assert deal.normal_price == (Decimal(normal_price) if normal_price else None)
    assert deal.deal_price == (Decimal(deal_price) if deal_price else None)
    found = deal_discount(deal)
    assert found is not None
    assert found.quantize(Decimal("0.0001")) == Decimal(discount)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("normale prijs per kg €14.98", Decimal("14.98")),
        ("Normale prijs per KG € 9,50", Decimal("9.50")),
        ("normale prijs per kilo €3", Decimal("3")),
        ("normale prijs per liter €2.40", None),  # not a weight
        ("normale prijs per kg €0.00", None),
        (None, None),
    ],
)
def test_price_per_kg(description: str | None, expected: Decimal | None) -> None:
    assert price_per_kg(description) == expected


def test_deals_carry_their_section_category(period: BonusPeriod) -> None:
    result = parse_bonus_week(week_of(period, *(load_ah_fixture(n) for n in SECTIONS)))
    deals = by_name(result.deals)
    assert deals["Wahid"].category == "Vlees"
    assert deals["AH Spruitjes 500 gram"].category == "Groente, aardappelen"


def test_counts_deals_without_a_determinable_discount(period: BonusPeriod) -> None:
    result = parse_bonus_week(week_of(period, *(load_ah_fixture(n) for n in SECTIONS)))
    assert result.no_discount == {
        # Group deals priced per pack, with no normal price to compare against.
        "2 VOOR 2.49": 1,
        "2 VOOR 2.99": 1,
        "2 VOOR 4.00": 1,
        "3 VOOR 6.00": 1,
        "VOOR 2.49": 1,
        "1 EURO KORTING": 1,
    }


def test_malformed_items_are_skipped_not_fatal(period: BonusPeriod) -> None:
    section = load_ah_fixture("section_vlees.json")
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
    section = load_ah_fixture("section_vlees.json")
    result = parse_bonus_week(week_of(period, section, section))
    assert len(result.deals) == 10


# --- range deals, with products from a range lookup --------------------------
# Real AH responses captured on 2026-11-04: three ranges, and their lookups.

RANGE_IDS = {"pizzas": 823274, "unox": 823490, "yorkham": 817938}


def range_week(period: BonusPeriod, ranges: dict[int, Any] | None = None) -> BonusWeek:
    if ranges is None:
        ranges = {
            seg: load_ah_fixture(f"range_{seg}.json") for seg in RANGE_IDS.values()
        }
    return BonusWeek(
        period=period, sections=[load_ah_fixture("section_ranges.json")], ranges=ranges
    )


def range_deal(result_deals: list[Deal], key: str) -> Deal:
    names = {
        "pizzas": "Alle AH Verse pizza's",
        "unox": "Unox soep in zak romige of Chinese tomatensoep 570 ml",
        "yorkham": "AH Yorkham van de versafdeling",
    }
    return by_name(result_deals)[names[key]]


def test_ranges_get_the_products_of_their_lookup(period: BonusPeriod) -> None:
    result = parse_bonus_week(range_week(period))

    assert result.skipped == []
    assert result.no_discount == {}
    assert (result.ranges_priced, result.range_products) == (3, 12)
    pizzas = range_deal(result.deals, "pizzas")
    assert pizzas.category == "Maaltijden, salades"
    assert len(pizzas.products) == 8
    assert {p.normal_price for p in pizzas.products} == {
        Decimal("6.99"),
        Decimal("6.89"),
    }
    # Unox's fixed price: "was" is the normal price, "now" the deal price.
    unox = range_deal(result.deals, "unox")
    assert [p.normal_price for p in unox.products] == [Decimal("3.29"), Decimal("3.85")]


@pytest.mark.parametrize(
    ("key", "size_price_per_kg"),
    [
        ("yorkham", Decimal("31.73")),  # €3.49 for "ca. 110 g"
        ("pizzas", Decimal("15.53")),  # €6.99 for "450 g"
        ("unox", None),  # "570 ml" is not a weight
    ],
)
def test_range_products_get_a_kilo_price_from_their_size(
    period: BonusPeriod, key: str, size_price_per_kg: Decimal | None
) -> None:
    deal = range_deal(parse_bonus_week(range_week(period)).deals, key)
    assert deal.products[0].normal_price_per_kg == size_price_per_kg


@pytest.mark.parametrize(
    ("key", "diet", "discount", "counted"),
    [
        # 2 voor 12.00 is €6.00 a pizza: 12.9% off €6.89, 14.2% off €6.99.
        ("pizzas", Diet.NONE, "0.1292", 8),
        # Vegetarian: no salami, prosciutto, tonno or meatlovers.
        ("pizzas", Diet.VEGETARIAN, "0.1292", 3),
        # Voor 1.49: 54.7% off €3.29 and 61.3% off €3.85.
        ("unox", Diet.NONE, "0.5800", 2),
        # €1.99 per 100 g is €19.90/kg, against €31.73/kg.
        ("yorkham", Diet.NONE, "0.3728", 2),
    ],
)
def test_range_deals_score_the_median_of_their_products(
    period: BonusPeriod, key: str, diet: Diet, discount: str, counted: int
) -> None:
    deal = range_deal(parse_bonus_week(range_week(period)).deals, key)
    (scored,) = score_deals([deal], Preferences(diet=diet), deal.valid_from)
    assert round(scored.discount, 4) == float(discount)
    assert scored.products_counted == counted


def test_bad_lookups_leave_the_range_without_products(period: BonusPeriod) -> None:
    lookup = load_ah_fixture("range_823490.json")
    unox_products = lookup["data"]["bonusPromotions"][0]["products"]
    unox_products[0]["priceV2"] = {"was": None, "now": None}  # no price
    del unox_products[1]["title"]  # malformed

    ranges = {RANGE_IDS["pizzas"]: {"unexpected": "shape"}, RANGE_IDS["unox"]: lookup}

    result = parse_bonus_week(range_week(period, ranges))

    assert len(result.deals) == 3, "the ranges themselves are kept"
    assert range_deal(result.deals, "pizzas").products == ()
    assert range_deal(result.deals, "unox").products == ()
    assert range_deal(result.deals, "yorkham").products == ()  # no lookup at all
    assert len(result.skipped) == 3
    assert result.ranges_priced == 0

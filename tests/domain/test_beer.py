"""Beer rules, on product and deal names as AH and Jumbo wrote them in November 2026."""

from datetime import date
from decimal import Decimal

import pytest

from koopjeskompas.domain.beer import (
    Packaging,
    beer_offers,
    is_alcohol_free,
    is_beer,
    packaging,
    parse_pack,
)
from koopjeskompas.domain.models import Deal, RangeProduct

TODAY = date(2026, 11, 10)


@pytest.mark.parametrize(
    "name",
    [
        "Alle Heineken multipacks*",
        "Alle herfstbokbieren multipacks",
        "Alle Hertog Jan, Amstel, Bavaria of Warsteiner multipacks",
        "Texels",  # a beer brand alone
        "Jopen, Uiltje, Brewdog of TwoChefs",
        "Leffe of Kasteelbier",
        "Pils van Grolsch, Peroni of Veltins",
        "Amstel Rosé bier 6-pack",  # rosé, but beer
        "Grolsch Gerijpte herfstbok 6-pack",  # a compound: herfst + bok
    ],
)
def test_beer(name: str) -> None:
    assert is_beer(name)


@pytest.mark.parametrize(
    "name",
    [
        "Diverse prijswinnende wijnen",
        "Alle Cadis wit of El Maestro",  # "wit" alone is wine here
        "Primitivo wijn",
        "Orbea Pinot Grigio",
        "Glen Talloch whisky, Esbjaerg vodka of Old Captain rum",
        "Hartevelt Jonge Jenever Prima 1 L",
        "Alle DubbelFrisss en Van de Boom Fruitwater",  # "dubbel", but not the word
        "Bokma Jonge Jenever",  # "bok" inside a word, but not at its end
    ],
)
def test_not_beer(name: str) -> None:
    assert not is_beer(name)


@pytest.mark.parametrize(
    ("name", "free"),
    [
        ("Heineken Premium pilsener 0.0 6-pack", True),
        ("Amstel Rosé 0.0% 6-pack", True),
        ("Warsteiner Alkoholfrei pilsener 6-pack", True),
        ("Hertog Jan 0.0 Alcoholvrij bier 6-pack", True),
        ("Tripel Karmeliet 0.4% 3 granenbier 4-pack", True),  # at most 0.5%
        ("Jopen - IPA - Craft Beer - <0.5% Alcoholvrij - Blik - 330ML", True),
        ("Grolsch Radler Citroen 2.0 Bier Blik 6-pack 330ML", False),
        ("Hertog Jan Pilsener bier 6-pack", False),
    ],
)
def test_alcohol_free(name: str, free: bool) -> None:
    assert is_alcohol_free(name) is free


@pytest.mark.parametrize(
    ("text", "units", "unit_litres", "litres"),
    [
        ("24 x 30 cl Hertog Jan Pilsener bier krat", 24, "0.3", "7.2"),
        ("6 x 0,33 l Heineken Premium pilsener 6-pack", 6, "0.33", "1.98"),
        ("Stella Artois Krat 24x330ML", 24, "0.33", "7.92"),
        ("300 ml Hertog Jan Weizener", 1, "0.3", "0.3"),
        # AH: the count in the title, the whole pack in the size field.
        ("1,8 l Heineken Witpils 6-pack", 6, "0.3", "1.8"),
        ("4,26 l Hertog Jan Pilsener bier 12-pack", 12, "0.355", "4.26"),
        ("4x 0,33 l La Trappe Bockbier 4-pack", 4, "0.33", "1.32"),
        ("Grolsch Puur Weizen Bier Fles 6-pack 300ML", 6, "0.3", "1.8"),
        ("Warsteiner Premium Beer Blik 0,5 L", 1, "0.5", "0.5"),
    ],
)
def test_parse_pack(text: str, units: int, unit_litres: str, litres: str) -> None:
    pack = parse_pack(text)
    assert pack is not None
    assert pack.units == units
    assert pack.unit_litres == Decimal(unit_litres)
    assert pack.litres == Decimal(litres)


def test_a_crate_by_its_total_alone_has_no_unit_count() -> None:
    pack = parse_pack("7,2 l Hertog Jan 0.0% alcoholvrij bier krat")
    assert pack is not None
    assert (pack.litres, pack.units) == (Decimal("7.2"), None)


def test_no_size_no_pack() -> None:
    assert parse_pack("Grimbergen Mix Speciaalbier rad") is None


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        # An explicit word wins.
        ("24 x 30 cl Hertog Jan Pilsener bier krat", Packaging.CRATE),
        ("24 x 0,3 l Bavaria pils 24fl", Packaging.CRATE),
        ("12 x 0,3 l Bavaria Pilsener 12-krat", Packaging.CRATE),
        ("0,33 l Bavaria pilsener bier bl.", Packaging.CAN),
        ("Alfa Edel Pils Blikken 6 x 33 cl", Packaging.CAN),
        ("Tripel Karmeliet Bier Flessen 4 x 33 cl", Packaging.BOTTLE),  # 33 cl bottles
        ("24 x 0,25 l Heineken Premium pilsener draaidop 24-pack", Packaging.BOTTLE),
        ("Grolsch Premium Pilsner Beugel Bier Fles 4-pack 450ML", Packaging.BOTTLE),
        # Otherwise Dutch conventions.
        ("24 x 0,3 l Warsteiner Pilsener", Packaging.CRATE),  # 24 × 30 cl
        ("6 x 0,3 l Hertog Jan Weizener 6-pack", Packaging.BOTTLE),  # 30 cl
        ("0,75 l Leffe Blond", Packaging.BOTTLE),
        ("6 x 0,33 l Heineken Premium pilsener 6-pack", Packaging.CAN),  # 33 cl
        ("24 x 0,5 l Amstel Bier 24-pack", Packaging.CAN),  # 50 cl
    ],
)
def test_packaging(text: str, kind: Packaging) -> None:
    pack = parse_pack(text)
    assert pack is not None
    assert packaging(text, pack) is kind


def test_a_24_pack_of_30_cl_is_a_tray_not_a_crate() -> None:
    text = "24 x 0,3 l Some pils 24-pack"
    pack = parse_pack(text)
    assert pack is not None
    assert packaging(text, pack) is Packaging.BOTTLE


# --- the offers -------------------------------------------------------------


def product(
    name: str, price: str, size: str | None = None, **extra: str
) -> RangeProduct:
    return RangeProduct(
        name=name,
        normal_price=Decimal(price),
        unit_size=size,
        **{key: Decimal(value) for key, value in extra.items()},
    )


def beer_deal(*products: RangeProduct, **fields: object) -> Deal:
    values: dict[str, object] = {
        "chain": "AH",
        "product_name": "Alle Hertog Jan, Amstel, Bavaria of Warsteiner multipacks",
        "mechanic_string": "25% KORTING",
        "valid_from": date(2026, 11, 9),
        "valid_to": date(2026, 11, 15),
        "products": products,
    }
    return Deal.model_validate(values | fields)


def test_each_product_is_an_offer_cheapest_per_litre_first() -> None:
    crate = product("Hertog Jan Pilsener bier krat", "21.32", "24 x 30 cl")
    sixpack = product("Hertog Jan Pilsener bier 6-pack", "7.32", "6 x 33 cl")

    offers = beer_offers([beer_deal(sixpack, crate)], TODAY)

    assert [o.product for o in offers] == [crate.name, sixpack.name]
    first = offers[0]
    assert first.packaging is Packaging.CRATE
    assert first.deal_price == Decimal("15.99")  # 25% off 21.32
    assert first.price_per_litre == Decimal("2.22")  # 15.99 / 7.2 l
    assert first.size_text == "24 x 30 cl"
    assert (first.chain, first.mechanic) == ("AH", "25% KORTING")


def test_without_a_size_the_price_per_litre_still_gives_the_volume() -> None:
    # Jumbo sometimes names a product "xx", but tells its price per litre.
    mystery = product("xx", "6.51", normal_price_per_litre="3.62")
    offers = beer_offers(
        [beer_deal(mystery, product_name="Leffe of Kasteelbier")], TODAY
    )
    # Volume known (1.8 l), packaging not: so it isn't listed in a tab.
    assert offers == []


def test_only_beer_deals_active_today() -> None:
    six = product("Heineken Premium pilsener 6-pack", "6.65", "6 x 0,33 l")
    expired = beer_deal(six, valid_from=date(2026, 11, 2), valid_to=date(2026, 11, 8))
    wine = beer_deal(
        product("Alpaca - Merlot - 750ML", "4.79"), product_name="Primitivo wijn"
    )
    assert beer_offers([expired, wine], TODAY) == []


def test_wine_inside_a_beer_deal_is_left_out() -> None:
    deal = beer_deal(
        product("Cadis Garganega pinot grigio", "4.49", "0,75 l"),
        product("Leffe Blond", "6.99", "0,75 l"),
    )
    assert [o.product for o in beer_offers([deal], TODAY)] == ["Leffe Blond"]


def test_alcohol_free_offers_are_marked() -> None:
    deal = beer_deal(
        product("Heineken Premium pilsener 0.0 6-pack", "6.65", "6 x 0,33 l")
    )
    (offer,) = beer_offers([deal], TODAY)
    assert offer.alcohol_free

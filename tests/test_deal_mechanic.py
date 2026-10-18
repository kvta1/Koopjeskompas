from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from koopjeskompas.domain.deal_mechanic import (
    UnknownMechanicError,
    deal_discount,
    parse_deal_mechanic,
)
from koopjeskompas.domain.models import Deal


@pytest.mark.parametrize(
    ("mechanic", "normal_price", "deal_price", "expected"),
    [
        ("2e halve prijs", None, None, Decimal("0.25")),
        ("2E Halve Prijs", None, None, Decimal("0.25")),
        ("  2e   halve prijs ", None, None, Decimal("0.25")),
        ("2e gratis", None, None, Decimal("0.5")),
        ("1+1 gratis", None, None, Decimal("0.5")),
        ("2+1 gratis", None, None, Decimal(1) / 3),
        ("3 voor 2", None, None, Decimal(1) / 3),
        ("25% korting", None, None, Decimal("0.25")),
        ("50 % korting", None, None, Decimal("0.5")),
        ("100% korting", None, None, Decimal(1)),
        # 2 voor €5 on a €3.00 product: €2.50 each, saving 1/6.
        ("2 voor €5", Decimal("3.00"), None, Decimal(1) / 6),
        ("2 voor €5,00", Decimal("3.00"), None, Decimal(1) / 6),
        ("3 voor € 4.50", Decimal("2.00"), None, Decimal("0.25")),
        # Not actually cheaper: no discount rather than a negative one.
        ("2 voor €5", Decimal("2.00"), None, Decimal(0)),
        # No mechanic: derive the discount from the two prices.
        (None, Decimal("2.00"), Decimal("1.50"), Decimal("0.25")),
        ("", Decimal("2.00"), Decimal("1.50"), Decimal("0.25")),
        (None, Decimal("2.00"), Decimal("2.50"), Decimal(0)),
    ],
)
def test_parse_deal_mechanic(
    mechanic: str | None,
    normal_price: Decimal | None,
    deal_price: Decimal | None,
    expected: Decimal,
) -> None:
    assert parse_deal_mechanic(mechanic, normal_price, deal_price) == expected


@pytest.mark.parametrize("mechanic", ["gratis bezorging", "150% korting", "0 voor €5"])
def test_unknown_mechanic(mechanic: str) -> None:
    with pytest.raises(UnknownMechanicError):
        parse_deal_mechanic(mechanic, Decimal("1.00"))


@pytest.mark.parametrize(
    ("mechanic", "normal_price", "deal_price"),
    [
        ("2 voor €5", None, None),  # price-based mechanic needs a normal price
        (None, Decimal("1.00"), None),  # no mechanic needs a deal price
        (None, None, Decimal("1.00")),
        ("25% korting", Decimal(0), None),
        (None, Decimal("1.00"), Decimal("-1")),
    ],
)
def test_invalid_prices(
    mechanic: str | None, normal_price: Decimal | None, deal_price: Decimal | None
) -> None:
    with pytest.raises(ValueError):
        parse_deal_mechanic(mechanic, normal_price, deal_price)


prices = st.decimals(min_value="0.01", max_value="1000", places=2)


@given(normal=prices, deal=prices)
def test_price_based_discount_is_a_fraction(normal: Decimal, deal: Decimal) -> None:
    assert 0 <= parse_deal_mechanic(None, normal, deal) <= 1


@given(n=st.integers(1, 10), total=prices, normal=prices)
def test_n_voor_discount_is_a_fraction(n: int, total: Decimal, normal: Decimal) -> None:
    assert 0 <= parse_deal_mechanic(f"{n} voor €{total}", normal) <= 1


def test_deal_discount_returns_none_when_undeterminable() -> None:
    deal = Deal(
        chain="AH",
        product_name="kikkererwten",
        mechanic_string="2 voor €5",
        valid_from=date(2026, 10, 12),
        valid_to=date(2026, 10, 18),
    )
    assert deal_discount(deal) is None

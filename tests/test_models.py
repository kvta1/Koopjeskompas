from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from koopjeskompas.domain.models import (
    Coordinates,
    Cuisine,
    Deal,
    Diet,
    Preferences,
    Store,
)


def make_deal(**overrides: object) -> Deal:
    fields: dict[str, object] = {
        "chain": "Jumbo",
        "product_name": "appel",
        "normal_price": Decimal("1.00"),
        "mechanic_string": "2e halve prijs",
        "valid_from": date(2026, 7, 21),
        "valid_to": date(2026, 7, 25),
    }
    fields.update(overrides)
    return Deal.model_validate(fields)


def test_instantiate_deal() -> None:
    deal = make_deal()
    assert deal.product_name == "appel"


def test_deal_rejects_inverted_validity_window() -> None:
    with pytest.raises(ValidationError):
        make_deal(valid_from=date(2026, 7, 25), valid_to=date(2026, 7, 21))


def test_deal_rejects_non_positive_normal_price() -> None:
    with pytest.raises(ValidationError):
        make_deal(normal_price=Decimal(0))


@pytest.mark.parametrize(
    ("day", "active"),
    [
        (date(2026, 7, 20), False),
        (date(2026, 7, 21), True),
        (date(2026, 7, 25), True),
        (date(2026, 7, 26), False),
    ],
)
def test_deal_is_active_on_inclusive_window(day: date, active: bool) -> None:
    assert make_deal().is_active_on(day) is active


def test_instantiate_store() -> None:
    store = Store(
        chain="Jumbo",
        name="Jumbo Delft",
        location=Coordinates(latitude=52.009066, longitude=4.364620),
    )
    assert store.location.latitude == 52.009066


@pytest.mark.parametrize(("lat", "lon"), [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_coordinates_out_of_range(lat: float, lon: float) -> None:
    with pytest.raises(ValidationError):
        Coordinates(latitude=lat, longitude=lon)


def test_instantiate_preferences() -> None:
    preferences = Preferences.model_validate(
        {"diet": "vegetarian", "cuisines": ["asian"]}
    )
    assert preferences.diet is Diet.VEGETARIAN
    assert preferences.cuisines == {Cuisine.ASIAN}


def test_preferences_reject_unknown_cuisine() -> None:
    with pytest.raises(ValidationError):
        Preferences.model_validate({"cuisines": ["martian"]})

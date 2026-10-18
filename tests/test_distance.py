import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from koopjeskompas.domain.distance import EARTH_RADIUS_KM, haversine_km
from koopjeskompas.domain.models import Coordinates

WHITE_HOUSE = Coordinates(latitude=38.898, longitude=-77.037)  # 77.037° *West*
EIFFEL_TOWER = Coordinates(latitude=48.858, longitude=2.294)
LEIDEN_CENTRAAL = Coordinates(latitude=52.1664, longitude=4.4817)
AMSTERDAM_CENTRAAL = Coordinates(latitude=52.3791, longitude=4.9003)

coordinates = st.builds(
    Coordinates,
    latitude=st.floats(min_value=-90, max_value=90),
    longitude=st.floats(min_value=-180, max_value=180),
)


@pytest.mark.parametrize(
    ("a", "b", "expected_km"),
    [
        # https://en.wikipedia.org/wiki/Haversine_formula
        (WHITE_HOUSE, EIFFEL_TOWER, 6177.45),
        (LEIDEN_CENTRAAL, AMSTERDAM_CENTRAAL, 37.0),
        # A quarter of the way around the equator.
        (
            Coordinates(latitude=0, longitude=0),
            Coordinates(latitude=0, longitude=90),
            math.pi * EARTH_RADIUS_KM / 2,
        ),
    ],
)
def test_known_distances(a: Coordinates, b: Coordinates, expected_km: float) -> None:
    assert haversine_km(a, b) == pytest.approx(expected_km, rel=0.01)


def test_antipodal_points_do_not_crash() -> None:
    a = Coordinates(latitude=0, longitude=0)
    b = Coordinates(latitude=0, longitude=180)
    assert haversine_km(a, b) == pytest.approx(math.pi * EARTH_RADIUS_KM)


@given(coordinates)
def test_distance_to_self_is_zero(a: Coordinates) -> None:
    assert haversine_km(a, a) == pytest.approx(0, abs=1e-6)


@given(coordinates, coordinates)
def test_distance_is_symmetric_and_bounded(a: Coordinates, b: Coordinates) -> None:
    d = haversine_km(a, b)
    assert d == pytest.approx(haversine_km(b, a))
    assert 0 <= d <= math.pi * EARTH_RADIUS_KM + 1e-6

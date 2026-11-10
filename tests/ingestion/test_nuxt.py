"""Unpacking Nuxt's page data: small hand-made devalue tables, and one real page."""

import json
import math
from pathlib import Path

import pytest

from koopjeskompas.ingestion.nuxt import NuxtDataError, page_data, unpack

REAL_PAGE = Path(__file__).parents[1] / "fixtures" / "jumbo" / "promotion_3021834.html"


def test_objects_and_arrays_hold_positions() -> None:
    # {"title": "Vla", "tags": ["2 voor 3,49"], "price": 249}
    table = [{"title": 1, "tags": 2, "price": 4}, "Vla", [3], "2 voor 3,49", 249]
    assert unpack(table) == {"title": "Vla", "tags": ["2 voor 3,49"], "price": 249}


def test_a_value_used_twice_is_stored_once() -> None:
    table = [[1, 1], {"name": 2}, "Jumbo"]
    first, second = unpack(table)
    assert first == {"name": "Jumbo"}
    assert first is second  # shared, as in the page


def test_a_cycle_does_not_loop_forever() -> None:
    node = unpack([{"self": 0}])
    assert node["self"] is node


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        (["Reactive", 1], "wrapped"),
        (["ShallowRef", 1], "wrapped"),
        (["EmptyRef"], None),
        (["Date", "2026-11-04T00:01:00.000Z"], "2026-11-04T00:01:00.000Z"),
        (["Set", 1, 1], ["wrapped", "wrapped"]),
    ],
)
def test_markers(marker: list[object], expected: object) -> None:
    assert unpack([marker, "wrapped"]) == expected


def test_map_and_null_prototype_objects() -> None:
    assert unpack([["Map", 1, 2], "key", "value"]) == {"key": "value"}
    assert unpack([["null", "key", 1], "value"]) == {"key": "value"}


def test_negative_positions_stand_for_special_values() -> None:
    undefined, nan, infinity = unpack([[-1, -3, -4]])
    assert undefined is None
    assert math.isnan(nan)
    assert infinity == math.inf


def test_an_unknown_marker_is_an_error_not_a_guess() -> None:
    with pytest.raises(NuxtDataError, match="Island"):
        unpack([["Island", 1], "x"])


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>No data here</body></html>",  # e.g. a bot-check page
        '<script id="__NUXT_DATA__" type="application/json">not json</script>',
        '<script id="__NUXT_DATA__" type="application/json">[]</script>',
    ],
)
def test_a_page_without_usable_data_is_an_error(html: str) -> None:
    with pytest.raises(NuxtDataError):
        page_data(html)


def test_a_real_page() -> None:
    data = page_data(REAL_PAGE.read_text(encoding="utf-8"))
    promotion = data["data"]["promotion-detail:3021834"]["promotion"]
    assert promotion["title"] == "Campina Vla"
    assert [t["text"] for t in promotion["tags"]] == ["2 voor 3,49"]
    first = promotion["products"][0]
    assert first["title"] == "Campina Dubbelvla aardbei-vanille 1 L"
    assert first["price"]["price"] == 249  # cents
    json.dumps(data)  # plain dicts and lists all the way down

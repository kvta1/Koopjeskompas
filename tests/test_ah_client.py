import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from koopjeskompas.ingestion.ah.client import (
    BASE_URL,
    GRAPHQL_PATH,
    METADATA_PATH,
    TOKEN_PATH,
    AhApiError,
    AhClient,
    load_raw_week,
)


def section_meta(category: str, bonus_type: str = "NATIONAL") -> dict[str, Any]:
    query = httpx.QueryParams(
        application="AHWEBSHOP",
        date="2026-10-12",
        promotionType=bonus_type,
        category=category,
    )
    return {
        "url": f"bonuspage/v2/section?{query}",
        "bonusType": bonus_type,
        "description": category,
    }


METADATA = {
    "periods": [
        {
            "bonusStartDate": "2026-10-12",
            "bonusEndDate": "2026-10-18",
            "tabs": [
                {"urlMetadataList": [section_meta("Groente", "SPOTLIGHT")]},
                {
                    "urlMetadataList": [
                        section_meta("Groente, aardappelen"),
                        section_meta("Vlees"),
                        section_meta("Drogisterij"),
                        section_meta("Etos acties", "ETOS"),
                    ]
                },
            ],
        },
        {"bonusStartDate": "2026-10-19", "bonusEndDate": "2026-10-25", "tabs": []},
    ]
}


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.post(TOKEN_PATH, name="token").respond(
            json={"access_token": "secret-token"}
        )
        router.get(METADATA_PATH, name="metadata").respond(json=METADATA)
        yield router


def make_client(tmp_path: Path) -> AhClient:
    return AhClient(raw_dir=tmp_path, sleep=lambda _: None)


def section_route(api: respx.MockRouter, category: str) -> respx.Route:
    return api.get(
        "/mobile-services/bonuspage/v2/section", params={"category": category}
    )


def test_fetches_only_national_food_sections_of_the_current_week(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    veg = section_route(api, "Groente, aardappelen").respond(json={"id": "veg"})
    meat = section_route(api, "Vlees").respond(json={"id": "meat"})

    week = make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))

    assert week.period.bonus_start_date == date(2026, 10, 12)
    assert week.sections == [{"id": "veg"}, {"id": "meat"}]
    assert week.failed_sections == []
    assert veg.called and meat.called
    # Spotlight, Drogisterij, Etos and the other week were not requested.
    assert len(api.calls) == 4


def test_sends_app_headers_and_bearer_token(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    route = section_route(api, "Groente, aardappelen").respond(json={})
    section_route(api, "Vlees").respond(json={})

    make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["x-application"] == "AHWEBSHOP"
    assert request.headers["User-Agent"].startswith("Appie/")


def test_writes_every_raw_response_to_disk(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    section_route(api, "Groente, aardappelen").respond(json={"id": "veg"})
    section_route(api, "Vlees").respond(json={"id": "meat"})

    make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "metadata.json",
        "section_groente_aardappelen.json",
        "section_vlees.json",
    ]
    saved = json.loads((tmp_path / "section_vlees.json").read_text())
    assert saved == {"id": "meat"}


def test_a_failing_section_is_skipped_not_fatal(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    section_route(api, "Groente, aardappelen").respond(500)
    section_route(api, "Vlees").respond(json={"id": "meat"})

    week = make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))

    assert week.sections == [{"id": "meat"}]
    assert week.failed_sections == ["Groente, aardappelen"]


def test_waits_between_requests(api: respx.MockRouter, tmp_path: Path) -> None:
    section_route(api, "Groente, aardappelen").respond(json={})
    section_route(api, "Vlees").respond(json={})
    sleeps: list[float] = []

    AhClient(raw_dir=tmp_path, delay_s=1.5, sleep=sleeps.append).fetch_bonus_week(
        date(2026, 10, 15)
    )

    assert sleeps == [1.5] * 4


@pytest.mark.parametrize(
    ("route", "response"),
    [
        ("token", httpx.Response(503)),
        ("token", httpx.Response(200, json={"no": "token"})),
        ("metadata", httpx.Response(500)),
        ("metadata", httpx.Response(200, json={"periods": "nope"})),
        ("metadata", httpx.Response(200, text="<html>not json</html>")),
    ],
)
def test_token_and_metadata_failures_raise_a_clear_error(
    api: respx.MockRouter, tmp_path: Path, route: str, response: httpx.Response
) -> None:
    api[route].return_value = response

    with pytest.raises(AhApiError):
        make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))


def test_network_errors_raise_a_clear_error(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    api["token"].side_effect = httpx.ConnectError("offline")
    with pytest.raises(AhApiError, match="failed"):
        make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))


def test_day_outside_any_bonus_period(api: respx.MockRouter, tmp_path: Path) -> None:
    with pytest.raises(AhApiError, match="no bonus period"):
        make_client(tmp_path).fetch_bonus_week(date(2026, 11, 30))


def test_saved_responses_can_be_reparsed_without_the_api(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    section_route(api, "Groente, aardappelen").respond(json={"id": "veg"})
    section_route(api, "Vlees").respond(500)
    fetched = make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15))
    calls = len(api.calls)

    reloaded = load_raw_week(tmp_path, date(2026, 10, 15))

    assert len(api.calls) == calls, "re-parsing must not touch the network"
    assert reloaded.period == fetched.period
    assert reloaded.sections == [{"id": "veg"}]
    assert reloaded.failed_sections == ["Vlees"]


def test_reparsing_needs_saved_responses(tmp_path: Path) -> None:
    with pytest.raises(AhApiError, match="no saved responses"):
        load_raw_week(tmp_path, date(2026, 10, 15))


# --- range lookups -------------------------------------------------------


def group(segment_id: int, code: str, **extra: Any) -> dict[str, Any]:
    return {
        "bonusGroup": {
            "segmentId": segment_id,
            "segmentDescription": f"Range {segment_id}",
            "discountLabels": [{"code": code}],
            **extra,
        }
    }


SECTION_WITH_RANGES = {
    "bonusGroupOrProducts": [
        group(1, "DISCOUNT_X_FOR_Y"),  # "2 voor 12.00": needs prices
        group(2, "DISCOUNT_PERCENTAGE"),  # "25% korting": doesn't
        group(3, "DISCOUNT_FIXED_PRICE", products=[{"title": "Already listed"}]),
        group(4, "DISCOUNT_FIXED_PRICE", promotionType="AHONLINE"),  # not in store
        group(1, "DISCOUNT_X_FOR_Y"),  # listed twice, looked up once
        {"unexpected": "shape"},
    ]
}
RANGE_RESPONSE = {"data": {"bonusPromotions": [{"id": "1", "products": []}]}}


def fetch_with_ranges(
    api: respx.MockRouter, tmp_path: Path, graphql: httpx.Response
) -> tuple[Any, respx.Route]:
    section_route(api, "Groente, aardappelen").respond(json=SECTION_WITH_RANGES)
    section_route(api, "Vlees").respond(json={})
    route = api.post(GRAPHQL_PATH).mock(return_value=graphql)
    return make_client(tmp_path).fetch_bonus_week(date(2026, 10, 15)), route


def test_looks_up_only_price_dependent_ranges_once(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    week, route = fetch_with_ranges(
        api, tmp_path, httpx.Response(200, json=RANGE_RESPONSE)
    )

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    assert "bonusPromotions" in body["query"]
    assert body["variables"] == {
        "id": "1",
        "periodStart": "2026-10-12",
        "periodEnd": "2026-10-18",
    }
    assert week.ranges == {1: RANGE_RESPONSE}
    assert week.failed_ranges == []
    saved = json.loads((tmp_path / "range_1.json").read_text())
    assert saved == RANGE_RESPONSE


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"errors": [{"message": "not allowed"}]}),
        httpx.Response(200, json=["not", "an", "object"]),
    ],
)
def test_a_failing_range_lookup_is_skipped_not_fatal(
    api: respx.MockRouter, tmp_path: Path, response: httpx.Response
) -> None:
    week, _ = fetch_with_ranges(api, tmp_path, response)

    assert week.ranges == {}
    assert week.failed_ranges == [1]
    assert not (tmp_path / "range_1.json").exists()
    assert len(week.sections) == 2, "the sections themselves still count"


def test_saved_range_lookups_can_be_reparsed(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    fetch_with_ranges(api, tmp_path, httpx.Response(200, json=RANGE_RESPONSE))

    reloaded = load_raw_week(tmp_path, date(2026, 10, 15))
    assert reloaded.ranges == {1: RANGE_RESPONSE}

    (tmp_path / "range_1.json").unlink()
    assert load_raw_week(tmp_path, date(2026, 10, 15)).failed_ranges == [1]

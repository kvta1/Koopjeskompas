import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from koopjeskompas.api.app import get_today
from koopjeskompas.cli import main
from koopjeskompas.ingestion.ah.client import (
    BASE_URL,
    GRAPHQL_PATH,
    METADATA_PATH,
    TOKEN_PATH,
)
from tests.ah_fixtures import load_ah_fixture

TODAY = "2026-10-15"  # inside the fixture's bonus week


def test_help_lists_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "fetch-deals" in out
    assert "rank" in out


def test_subcommand_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code != 0


@pytest.fixture
def ah_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    """Serve the captured AH responses; sections without a fixture are empty."""
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.post(TOKEN_PATH).respond(json={"access_token": "t"})
        router.get(METADATA_PATH).respond(json=load_ah_fixture("metadata.json"))
        for category, fixture in [
            ("Groente, aardappelen", "section_groente_aardappelen.json"),
            ("Vlees", "section_vlees.json"),
        ]:
            router.get(
                "/mobile-services/bonuspage/v2/section", params={"category": category}
            ).respond(json=load_ah_fixture(fixture))
        router.get("/mobile-services/bonuspage/v2/section").respond(
            json={"bonusGroupOrProducts": []}
        )
        router.post(GRAPHQL_PATH).mock(side_effect=_range_lookup)
        yield router


# A hand-made lookup for "Alle AH Rauwkost" (2 VOOR 4.00) in the fixture week: €2.00
# each saves 12.7% on the first product and 19.7% on the second. The fixture week's
# other ranges come back without products.
RAUWKOST_SEGMENT_ID = "818834"
RAUWKOST_PRODUCTS = [("AH Rauwkost wortel", 2.29), ("AH Rauwkost bietjes", 2.49)]


def _range_lookup(request: httpx.Request) -> httpx.Response:
    segment_id = json.loads(request.content)["variables"]["id"]
    products = [
        {"title": title, "priceV2": {"was": {"amount": price}}}
        for title, price in RAUWKOST_PRODUCTS
        if segment_id == RAUWKOST_SEGMENT_ID
    ]
    promotions = [{"id": segment_id, "products": products}]
    return httpx.Response(200, json={"data": {"bonusPromotions": promotions}})


def test_fetch_then_rank(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--data-dir", str(tmp_path), "--today", TODAY]

    assert main([*base, "fetch-deals"]) == 0
    out = capsys.readouterr().out
    assert "23 deals saved" in out
    assert "Range deals priced per product: 1 (2 products)" in out
    assert "1 EURO KORTING" in out  # a range whose lookup returned no products
    assert "2 VOOR 4.00" not in out  # Alle AH Rauwkost, now priced per product
    assert (tmp_path / "deals" / "ah.json").exists()
    assert (tmp_path / "raw" / "ah" / TODAY / "section_vlees.json").exists()

    assert main([*base, "rank", "--diet", "vegetarian", "--radius-km", "10"]) == 0
    out = capsys.readouterr().out
    # All stores share AH's deals, so the one nearest Leiden Centraal comes first.
    assert out.startswith("1. AH Breestraat")
    assert "AH Spruitjes 500 gram" in out
    assert "Alle AH Rauwkost  [2 VOOR 4.00]  median of 2 products" in out
    for meat in ["rookworst", "kip", "bacon", "wahid"]:
        assert meat not in out.lower()


def test_fetch_deals_from_raw_reuses_saved_responses(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--data-dir", str(tmp_path), "--today", TODAY, "fetch-deals"]
    assert main(base) == 0
    calls = len(ah_api.calls)
    (tmp_path / "deals" / "ah.json").unlink()
    capsys.readouterr()

    assert main([*base, "--from-raw"]) == 0

    assert len(ah_api.calls) == calls
    assert "23 deals saved" in capsys.readouterr().out
    assert (tmp_path / "deals" / "ah.json").exists()


def test_fetch_deals_reports_failed_range_lookups(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ah_api.post(GRAPHQL_PATH).respond(500)
    assert main(["--data-dir", str(tmp_path), "--today", TODAY, "fetch-deals"]) == 0
    out = capsys.readouterr().out
    assert "23 deals saved" in out
    assert "Range lookups that failed or are missing: 6" in out


def test_fetch_deals_reports_api_failure(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ah_api.post(TOKEN_PATH).respond(503)
    assert main(["--data-dir", str(tmp_path), "--today", TODAY, "fetch-deals"]) == 1
    assert "HTTP 503" in capsys.readouterr().err
    assert not (tmp_path / "deals").exists()


def test_rank_without_cached_deals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(tmp_path), "rank"]) == 1
    assert "run 'koopjeskompas fetch-deals' first" in capsys.readouterr().out


def test_serve_runs_the_api_on_the_given_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: dict[str, Any] = {}

    def fake_run(app: FastAPI, host: str, port: int) -> None:
        started.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    argv = ["--data-dir", str(tmp_path), "--today", TODAY, "serve", "--port", "9000"]

    assert main(argv) == 0

    assert (started["host"], started["port"]) == ("127.0.0.1", 9000)
    client = TestClient(started["app"])
    response = client.post("/api/rank", json={"location": {"lat": 52.16, "lon": 4.48}})
    assert response.status_code == 503  # nothing cached in tmp_path yet
    app: FastAPI = started["app"]
    assert app.dependency_overrides[get_today]() == date(2026, 10, 15)

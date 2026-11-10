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

from koopjeskompas import cli
from koopjeskompas.api.app import create_app, get_today, openapi_json
from koopjeskompas.cli import main
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.cache import deals_path, load_deals
from koopjeskompas.ingestion.source import SourceError, SourceResult
from koopjeskompas.ingestion.ah.client import (
    BASE_URL,
    GRAPHQL_PATH,
    METADATA_PATH,
    TOKEN_PATH,
)
from koopjeskompas.ingestion.jumbo.client import BASE_URL as JUMBO_URL
from koopjeskompas.ingestion.jumbo.client import OVERVIEW_PATH
from tests.ah_fixtures import load_ah_fixture
from koopjeskompas.ingestion.lidl.client import BASE_URL as LIDL_URL
from koopjeskompas.ingestion.lidl.client import DEALS_PATH as LIDL_DEALS_PATH
from tests.jumbo_fixtures import overview_data, page_with, vla_page
from tests.lidl_fixtures import deals_page

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

    assert main([*base, "fetch-deals", "--chain", "ah"]) == 0
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
    base = [
        "--data-dir",
        str(tmp_path),
        "--today",
        TODAY,
        "fetch-deals",
        "--chain",
        "ah",
    ]
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
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--today",
                TODAY,
                "fetch-deals",
                "--chain",
                "ah",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "23 deals saved" in out
    assert "Range lookups that failed or are missing: 6" in out


def test_fetch_deals_reports_api_failure(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ah_api.post(TOKEN_PATH).respond(503)
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--today",
                TODAY,
                "fetch-deals",
                "--chain",
                "ah",
            ]
        )
        == 1
    )
    assert "HTTP 503" in capsys.readouterr().err
    assert not (tmp_path / "deals").exists()


@pytest.fixture
def jumbo_site(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    """Jumbo's overview and the Campina Vla page as captured; other pages 404."""
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with respx.mock(base_url=JUMBO_URL, assert_all_called=False) as router:
        router.get(OVERVIEW_PATH).respond(text=page_with(overview_data()))
        router.get("/aanbiedingen/campina-vla/3021834").respond(text=vla_page())
        router.get(path__startswith="/aanbiedingen/").respond(404)
        yield router


def test_fetch_jumbo_deals(
    jumbo_site: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--data-dir", str(tmp_path), "--today", "2026-11-10", "fetch-deals"]

    assert main([*base, "--chain", "jumbo"]) == 0

    out = capsys.readouterr().out
    assert "Jumbo deals 2026-11-04 to 2026-11-17: 4 deals saved" in out
    assert "Promotions priced per product: 1 (17 products)" in out
    assert "Promotion pages that failed or are missing: 1" in out  # the mango
    assert "Left out: 2 not food, 2 online only" in out
    deals = load_deals(deals_path(tmp_path, "Jumbo"))
    assert {d.chain for d in deals} == {"Jumbo"}
    raw = tmp_path / "raw" / "jumbo" / "2026-11-10"
    assert (raw / "overview.json").exists()

    # Re-parsing the saved pages asks Jumbo nothing.
    calls = len(jumbo_site.calls)
    assert main([*base, "--chain", "jumbo", "--from-raw"]) == 0
    assert len(jumbo_site.calls) == calls
    assert "4 deals saved" in capsys.readouterr().out


def test_fetch_lidl_deals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--data-dir", str(tmp_path), "--today", "2026-11-10", "fetch-deals"]
    with respx.mock(base_url=LIDL_URL) as lidl:
        lidl.get(LIDL_DEALS_PATH).respond(text=deals_page())

        assert main([*base, "--chain", "lidl"]) == 0
        out = capsys.readouterr().out
        assert "Lidl deals 2026-11-05 to 2026-11-15: 41 deals saved" in out
        assert "Lidl Plus deals (need the app): 19" in out
        assert "Left out: 6 not food" in out
        assert {d.chain for d in load_deals(deals_path(tmp_path, "Lidl"))} == {"Lidl"}

        assert main([*base, "--chain", "lidl", "--from-raw"]) == 0
        assert len(lidl.calls) == 1  # the re-parse asked nothing


class WorkingSource:
    chain = "Good"

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        deal = Deal(
            chain=self.chain,
            product_name="Hummus",
            mechanic_string="25% korting",
            valid_from=day,
            valid_to=day,
        )
        return SourceResult(title="Good deals", deals=[deal], notes=["all fine"])

    reparse = fetch


class BrokenSource:
    chain = "Broken"

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        raise SourceError("blocked")

    reparse = fetch


def test_one_failing_chain_does_not_cost_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "SOURCES", {"broken": BrokenSource, "good": WorkingSource})

    # Nonzero, so a script notices the failure...
    assert main(["--data-dir", str(tmp_path), "--today", TODAY, "fetch-deals"]) == 1

    # ...but the chain that worked is saved and reported.
    (deal,) = load_deals(deals_path(tmp_path, "Good"))
    assert deal.product_name == "Hummus"
    captured = capsys.readouterr()
    assert "Fetching Broken deals failed: blocked" in captured.err
    assert "Good deals: 1 deals saved" in captured.out
    assert "all fine" in captured.out


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


def test_openapi_writes_the_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "openapi.json"

    assert main(["openapi", "--output", str(output)]) == 0

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert "/api/rank" in schema["paths"]
    assert output.read_text(encoding="utf-8") == openapi_json(create_app(tmp_path))
    assert str(output) in capsys.readouterr().out

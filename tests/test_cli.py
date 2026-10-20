import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from koopjeskompas.cli import main
from koopjeskompas.ingestion.ah.client import BASE_URL, METADATA_PATH, TOKEN_PATH

FIXTURES = Path(__file__).parent / "fixtures" / "ah"
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
        router.get(METADATA_PATH).respond(
            json=json.loads((FIXTURES / "metadata.json").read_text())
        )
        for category, fixture in [
            ("Groente, aardappelen", "section_groente_aardappelen.json"),
            ("Vlees", "section_vlees.json"),
        ]:
            router.get(
                "/mobile-services/bonuspage/v2/section", params={"category": category}
            ).respond(json=json.loads((FIXTURES / fixture).read_text()))
        router.get("/mobile-services/bonuspage/v2/section").respond(
            json={"bonusGroupOrProducts": []}
        )
        yield router


def test_fetch_then_rank(
    ah_api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--data-dir", str(tmp_path), "--today", TODAY]

    assert main([*base, "fetch-deals"]) == 0
    out = capsys.readouterr().out
    assert "23 deals saved" in out
    assert "100 GRAM VOOR 2.99" in out
    assert (tmp_path / "deals" / "ah.json").exists()
    assert (tmp_path / "raw" / "ah" / TODAY / "section_vlees.json").exists()

    assert main([*base, "rank", "--diet", "vegetarian", "--radius-km", "10"]) == 0
    out = capsys.readouterr().out
    # All stores share AH's deals, so the one nearest Leiden Centraal comes first.
    assert out.startswith("1. AH Breestraat")
    assert "AH Spruitjes 500 gram" in out
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

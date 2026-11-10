"""Fetching Jumbo's pages, with HTTP mocked by respx: no request reaches Jumbo."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from koopjeskompas.ingestion.http import BlockedError
from koopjeskompas.ingestion.jumbo.client import (
    BASE_URL,
    OVERVIEW_PATH,
    JumboClient,
    load_raw_week,
)
from koopjeskompas.ingestion.nuxt import script_json
from koopjeskompas.ingestion.source import SourceError
from tests.jumbo_fixtures import overview_data, page_with, vla_page

VLA_PATH = "/aanbiedingen/campina-vla/3021834"
MANGO_PATH = "/aanbiedingen/mango/3023582"


@pytest.fixture
def jumbo() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get(OVERVIEW_PATH).respond(text=page_with(overview_data()))
        router.get(VLA_PATH).respond(text=vla_page())
        router.get(MANGO_PATH).respond(404)
        yield router


def client(raw_dir: Path) -> JumboClient:
    return JumboClient(raw_dir, sleep=lambda _: None)


def test_the_overview_then_each_promotion_that_needs_a_price(
    jumbo: respx.MockRouter, tmp_path: Path
) -> None:
    week = client(tmp_path).fetch_week()

    asked = [call.request.url.path for call in jumbo.calls]
    assert asked == [OVERVIEW_PATH, VLA_PATH, MANGO_PATH]
    assert set(week.promotions) == {"3021834"}
    assert week.failed == ["3023582"]  # the 404 costs only the mango


def test_it_presents_itself_as_a_browser(
    jumbo: respx.MockRouter, tmp_path: Path
) -> None:
    # Jumbo's Akamai drops honest requests; the scraping policy allows this.
    client(tmp_path).fetch_week()
    assert jumbo.calls[0].request.headers["user-agent"].startswith("Mozilla/5.0")


def test_only_the_pages_data_is_saved(jumbo: respx.MockRouter, tmp_path: Path) -> None:
    client(tmp_path).fetch_week()

    saved = (tmp_path / "promotion_3021834.json").read_text()
    assert saved == script_json(vla_page())  # the data script, not the page
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "overview.json",
        "promotion_3021834.json",
    ]


def test_a_bot_check_page_stops_the_lookups(
    jumbo: respx.MockRouter, tmp_path: Path
) -> None:
    # Akamai can answer 200 with a challenge instead of the page.
    jumbo.get(VLA_PATH).respond(text="<html>Even geduld…</html>")

    week = client(tmp_path).fetch_week()

    assert week.promotions == {}
    assert week.failed == ["3021834", "3023582"]
    assert len(jumbo.calls) == 2  # the mango wasn't asked for


def test_a_blocked_overview_fails_the_whole_source(
    jumbo: respx.MockRouter, tmp_path: Path
) -> None:
    jumbo.get(OVERVIEW_PATH).respond(403)
    with pytest.raises(BlockedError):
        client(tmp_path).fetch_week()


def test_saved_pages_are_read_back_without_asking(
    jumbo: respx.MockRouter, tmp_path: Path
) -> None:
    fetched = client(tmp_path).fetch_week()
    calls = len(jumbo.calls)

    reread = load_raw_week(tmp_path)

    assert len(jumbo.calls) == calls
    assert reread.overview == fetched.overview
    assert reread.promotions == fetched.promotions
    assert reread.failed == ["3023582"]


def test_without_saved_pages_reparsing_is_a_source_error(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="no saved Jumbo pages"):
        load_raw_week(tmp_path)

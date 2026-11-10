"""Fetching Lidl's deals page, with HTTP mocked by respx: no request reaches Lidl."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from koopjeskompas.ingestion.http import HONEST_HEADERS
from koopjeskompas.ingestion.lidl.client import (
    BASE_URL,
    DEALS_PATH,
    LidlClient,
    NoTilesError,
    load_raw_tiles,
)
from koopjeskompas.ingestion.source import SourceError
from tests.lidl_fixtures import deals_page, tiles


@pytest.fixture
def lidl() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE_URL) as router:
        router.get(DEALS_PATH).respond(text=deals_page())
        yield router


def test_one_honest_request_gives_every_tile(
    lidl: respx.MockRouter, tmp_path: Path
) -> None:
    assert LidlClient(tmp_path).fetch_tiles() == tiles()
    assert len(lidl.calls) == 1
    # Lidl answers an honest identity, so that's what it gets.
    agent = lidl.calls[0].request.headers["user-agent"]
    assert agent == HONEST_HEADERS["User-Agent"]


def test_only_the_tiles_are_saved(lidl: respx.MockRouter, tmp_path: Path) -> None:
    LidlClient(tmp_path).fetch_tiles()
    saved = (tmp_path / "grid.json").read_text()
    assert json.loads(saved) == tiles()
    assert len(saved) < len(deals_page())


def test_a_page_without_tiles_is_an_error_not_an_empty_week(
    lidl: respx.MockRouter, tmp_path: Path
) -> None:
    lidl.get(DEALS_PATH).respond(text="<html><body>Nieuwe pagina</body></html>")
    with pytest.raises(NoTilesError, match="layout"):
        LidlClient(tmp_path).fetch_tiles()
    assert not (tmp_path / "grid.json").exists()


def test_saved_tiles_are_read_back_without_asking(
    lidl: respx.MockRouter, tmp_path: Path
) -> None:
    LidlClient(tmp_path).fetch_tiles()
    assert load_raw_tiles(tmp_path) == tiles()
    assert len(lidl.calls) == 1


def test_without_a_saved_page_reparsing_is_a_source_error(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="no saved Lidl page"):
        load_raw_tiles(tmp_path)

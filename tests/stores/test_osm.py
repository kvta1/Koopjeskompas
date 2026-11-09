"""Turning OpenStreetMap's answer into stores, and asking Overpass for it.

The fixture is built by hand in Overpass's documented JSON format, one element per
rule, modelled on what the real answer contains; HTTP is mocked with respx, so no
test contacts Overpass.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from koopjeskompas.cli import main
from koopjeskompas.stores import load_stores
from koopjeskompas.stores.osm import (
    DEFAULT_SERVER,
    OverpassError,
    fetch_overpass,
    stores_from_overpass,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "osm" / "overpass_ah.json"


@pytest.fixture
def overpass_answer() -> Any:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --- converting ------------------------------------------------------------


def test_supermarkets_become_stores(overpass_answer: Any) -> None:
    result = stores_from_overpass(overpass_answer)
    by_address = {s.address: s for s in result.stores}

    breestraat = by_address["Breestraat 130, Leiden"]
    assert breestraat.name == "AH Breestraat"
    assert breestraat.chain == "AH"
    assert (breestraat.location.latitude, breestraat.location.longitude) == (
        52.1570015,
        4.4919905,
    )
    # A building outline has no point of its own; Overpass gives its centre.
    assert by_address["Hooigracht 85, Leiden"].location.latitude == 52.1597304


def test_a_store_without_a_street_is_named_by_branch_or_town(
    overpass_answer: Any,
) -> None:
    names = {s.name: s.address for s in stores_from_overpass(overpass_answer).stores}
    assert names["AH Oegstgeest Lange Voort"] is None  # no address known at all
    assert names["AH Leiderdorp"] == "Leiderdorp"


def test_xl_stores_say_so(overpass_answer: Any) -> None:
    names = {s.address: s.name for s in stores_from_overpass(overpass_answer).stores}
    assert names["Bevrijdingsplein 50, Leiden"] == "AH XL Bevrijdingsplein"


def test_a_store_mapped_twice_counts_once(overpass_answer: Any) -> None:
    result = stores_from_overpass(overpass_answer)
    kopermolen = [s for s in result.stores if s.name == "AH Kopermolen"]
    assert len(kopermolen) == 1
    assert kopermolen[0].address == "Kopermolen 44, Leiden"  # the first one is kept
    assert result.duplicates == 1


def test_same_named_stores_in_different_towns_are_both_kept(
    overpass_answer: Any,
) -> None:
    stores = stores_from_overpass(overpass_answer).stores
    assert [s.address for s in stores if s.name == "AH Breestraat"] == [
        "Breestraat 130, Leiden",
        "Breestraat 2, Utrecht",
    ]


def test_what_is_left_out_is_reported_with_a_reason(overpass_answer: Any) -> None:
    skipped = stores_from_overpass(overpass_answer).skipped
    assert skipped == [
        "node/1007: no street, branch or town to name it by",
        "node/1008: not a supermarket",
        "node/1009: a pickup point, not a store",
        "relation/3001: no location",
    ]


def test_stores_come_out_sorted(overpass_answer: Any) -> None:
    stores = stores_from_overpass(overpass_answer).stores
    assert [s.name for s in stores] == sorted(s.name for s in stores)


@pytest.mark.parametrize("payload", [{}, {"elements": []}, None, ["not", "a dict"]])
def test_an_empty_or_odd_answer_gives_no_stores(payload: Any) -> None:
    assert stores_from_overpass(payload).stores == []


def test_an_element_that_is_not_osm_is_skipped() -> None:
    result = stores_from_overpass({"elements": [{"type": "node"}]})
    assert result.stores == []
    assert len(result.skipped) == 1


# --- fetching --------------------------------------------------------------


@respx.mock
def test_fetch_sends_the_query_and_identifies_itself(overpass_answer: Any) -> None:
    route = respx.post(DEFAULT_SERVER).respond(json=overpass_answer)

    assert fetch_overpass("[out:json];") == overpass_answer

    request = route.calls.last.request
    assert request.content == b"data=%5Bout%3Ajson%5D%3B"  # form-encoded, as asked
    assert "koopjeskompas" in request.headers["user-agent"]


@respx.mock
@pytest.mark.parametrize("status", [429, 502, 504])
def test_a_busy_server_is_reported_with_what_to_do(status: int) -> None:
    respx.post(DEFAULT_SERVER).respond(status)
    with pytest.raises(OverpassError, match="busy.*another --server"):
        fetch_overpass("[out:json];")


@respx.mock
def test_a_runtime_error_inside_a_200_is_still_an_error() -> None:
    respx.post(DEFAULT_SERVER).respond(
        json={
            "elements": [],
            "remark": 'runtime error: Query timed out in "query" at line 4',
        }
    )
    with pytest.raises(OverpassError, match="timed out"):
        fetch_overpass("[out:json];")


@respx.mock
def test_an_answer_that_is_not_json_is_an_error() -> None:
    respx.post(DEFAULT_SERVER).respond(200, text="<html>busy</html>")
    with pytest.raises(OverpassError, match="other than JSON"):
        fetch_overpass("[out:json];")


@respx.mock
def test_an_unreachable_server_is_an_error() -> None:
    respx.post(DEFAULT_SERVER).mock(side_effect=httpx.ConnectTimeout("too slow"))
    with pytest.raises(OverpassError, match="could not be reached"):
        fetch_overpass("[out:json];")


# --- the command -----------------------------------------------------------


def fetch_stores(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "--today",
            "2026-11-10",
            "fetch-stores",
            "--output",
            str(tmp_path / "stores.json"),
            *extra,
        ]
    )


@respx.mock
def test_fetch_stores_writes_the_list_and_keeps_the_raw_answer(
    tmp_path: Path, overpass_answer: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(DEFAULT_SERVER).respond(json=overpass_answer)

    assert fetch_stores(tmp_path) == 0

    stores = load_stores(tmp_path / "stores.json")
    assert len(stores) == 7
    raw = tmp_path / "data" / "raw" / "osm" / "2026-11-10" / "nl_ah.json"
    assert json.loads(raw.read_text()) == overpass_answer
    out = capsys.readouterr().out
    assert "7 stores written" in out
    assert "Merged 1" in out
    assert "Skipped 4" in out


@respx.mock
def test_fetch_stores_from_raw_asks_nobody(
    tmp_path: Path, overpass_answer: Any
) -> None:
    route = respx.post(DEFAULT_SERVER).respond(json=overpass_answer)
    fetch_stores(tmp_path)
    (tmp_path / "stores.json").unlink()

    assert fetch_stores(tmp_path, "--from-raw") == 0
    assert route.call_count == 1  # only the first run asked Overpass
    assert len(load_stores(tmp_path / "stores.json")) == 7


@respx.mock
def test_finding_no_stores_never_replaces_the_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # What a server without area data answers: a valid, empty result.
    respx.post(DEFAULT_SERVER).respond(json={"elements": []})
    existing = tmp_path / "stores.json"
    existing.write_text("[]")

    assert fetch_stores(tmp_path) == 1
    assert existing.read_text() == "[]"  # untouched
    assert "another --server" in capsys.readouterr().err


@respx.mock
def test_fetch_stores_reports_a_busy_server(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(DEFAULT_SERVER).respond(504)
    assert fetch_stores(tmp_path) == 1
    assert "504" in capsys.readouterr().err
    assert not (tmp_path / "stores.json").exists()

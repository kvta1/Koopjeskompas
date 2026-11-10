"""The polite client, with HTTP mocked by respx and the pause recorded, not slept."""

from pathlib import Path

import httpx
import pytest
import respx

from koopjeskompas.ingestion.http import (
    BROWSER_HEADERS,
    HONEST_HEADERS,
    BlockedError,
    FetchError,
    PoliteClient,
)
from koopjeskompas.ingestion.source import SourceError

BASE = "https://shop.example"


@pytest.fixture
def pauses() -> list[float]:
    return []


@pytest.fixture
def client(tmp_path: Path, pauses: list[float]) -> PoliteClient:
    return PoliteClient(BASE, tmp_path / "raw", sleep=pauses.append)


@respx.mock
def test_pages_are_saved_before_anything_parses_them(
    client: PoliteClient, tmp_path: Path
) -> None:
    respx.get(f"{BASE}/aanbiedingen").respond(text="<html>deals</html>")

    assert client.get_text("/aanbiedingen", "overview.html") == "<html>deals</html>"
    saved = tmp_path / "raw" / "overview.html"
    assert saved.read_text() == "<html>deals</html>"
    assert client.read_saved("overview.html") == "<html>deals</html>"


@respx.mock
def test_only_the_part_worth_keeping_is_saved(
    client: PoliteClient, tmp_path: Path
) -> None:
    respx.get(f"{BASE}/deal").respond(text="<html>layout<data>42</data></html>")

    def data_only(html: str) -> str:
        return html.split("<data>")[1].split("</data>")[0]

    assert client.get_text("/deal", "deal.json", keep=data_only) == "42"
    assert (tmp_path / "raw" / "deal.json").read_text() == "42"


@respx.mock
def test_one_request_at_a_time_with_a_pause_between(
    client: PoliteClient, pauses: list[float]
) -> None:
    respx.get(url__startswith=BASE).respond(text="ok")
    for page in ["a", "b", "c"]:
        client.get_text(f"/{page}", f"{page}.html")
    assert pauses == [1.0, 1.0]  # before the 2nd and 3rd, not the 1st


@respx.mock
def test_identity_is_honest_unless_asked_otherwise(tmp_path: Path) -> None:
    route = respx.get(url__startswith=BASE).respond(text="ok")

    PoliteClient(BASE, tmp_path, sleep=lambda _: None).get_text("/", "a.html")
    honest = route.calls.last.request.headers["user-agent"]
    assert honest == HONEST_HEADERS["User-Agent"]

    browser = PoliteClient(BASE, tmp_path, BROWSER_HEADERS, sleep=lambda _: None)
    browser.get_text("/", "b.html")
    assert route.calls.last.request.headers["user-agent"].startswith("Mozilla/5.0")


@respx.mock
@pytest.mark.parametrize("status", [403, 429])
def test_a_block_stops_every_later_request(client: PoliteClient, status: int) -> None:
    route = respx.get(url__startswith=BASE).respond(status)

    with pytest.raises(BlockedError, match=str(status)):
        client.get_text("/a", "a.html")
    with pytest.raises(BlockedError, match="not asking again"):
        client.get_text("/b", "b.html")
    assert route.call_count == 1


@respx.mock
def test_a_source_can_report_a_block_it_recognised(client: PoliteClient) -> None:
    route = respx.get(url__startswith=BASE).respond(
        text="<html>Are you a robot?</html>"
    )
    client.get_text("/a", "a.html")

    with pytest.raises(BlockedError):
        client.blocked("the page is a bot check")
    with pytest.raises(BlockedError):
        client.get_text("/b", "b.html")
    assert route.call_count == 1


@respx.mock
def test_other_failures_cost_only_that_page(client: PoliteClient) -> None:
    respx.get(f"{BASE}/gone").respond(404)
    respx.get(f"{BASE}/slow").mock(side_effect=httpx.ReadTimeout("too slow"))
    respx.get(f"{BASE}/fine").respond(text="ok")

    with pytest.raises(FetchError, match="404"):
        client.get_text("/gone", "gone.html")
    with pytest.raises(FetchError, match="could not be fetched"):
        client.get_text("/slow", "slow.html")
    assert client.get_text("/fine", "fine.html") == "ok"


def test_every_failure_is_a_source_error() -> None:
    # So fetch-deals reports it as that chain failing and carries on with the rest.
    assert issubclass(BlockedError, FetchError)
    assert issubclass(FetchError, SourceError)

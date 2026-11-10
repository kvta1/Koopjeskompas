"""HTTP access to Lidl's deals page, through the polite client.

One request a week: the deals page lists every deal as a tile, each with its prices
and dates in a ``data-grid-data`` attribute, so nothing else needs asking. Lidl
answers an honest identity, so that is what this client uses (HONEST_HEADERS, the
default). Only the tiles' data is saved, as a JSON list (``grid.json``).
"""

import html
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from koopjeskompas.ingestion.http import PoliteClient
from koopjeskompas.ingestion.source import SourceError

BASE_URL = "https://www.lidl.nl"
# Redirects to /c/store/aanbiedingen/a10008785, the in-store deals.
DEALS_PATH = "/c/aanbiedingen/a10008785"
GRID_FILE = "grid.json"

_TILE = re.compile(r'data-grid-data="([^"]*)"')


class NoTilesError(SourceError):
    """The page came without deal tiles: Lidl changed its page, or sent another one."""


def tiles_json(page: str) -> str:
    """Every tile's data, as one JSON list: what a fetch saves and the parser reads."""
    tiles = [json.loads(html.unescape(raw)) for raw in _TILE.findall(page)]
    if not tiles:
        raise NoTilesError(
            "the deals page has no product tiles; did its layout change?"
        )
    return json.dumps(tiles, ensure_ascii=False)


class LidlClient:
    def __init__(
        self,
        raw_dir: Path,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = PoliteClient(BASE_URL, raw_dir, sleep=sleep, http=http)

    def fetch_tiles(self) -> list[Any]:
        text = self._client.get_text(DEALS_PATH, GRID_FILE, keep=tiles_json)
        tiles: list[Any] = json.loads(text)
        return tiles


def load_raw_tiles(raw_dir: Path) -> list[Any]:
    """The tiles an earlier fetch saved in ``raw_dir``."""
    try:
        tiles: list[Any] = json.loads((raw_dir / GRID_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SourceError(f"no saved Lidl page in {raw_dir}") from error
    return tiles

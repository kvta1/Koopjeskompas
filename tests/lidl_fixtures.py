"""Lidl's deals page as captured on 2026-11-10 (47 tiles, unmodified)."""

import html
import json
import re
from pathlib import Path
from typing import Any

LIDL_FIXTURES = Path(__file__).parent / "fixtures" / "lidl"


def deals_page() -> str:
    return (LIDL_FIXTURES / "aanbiedingen.html").read_text(encoding="utf-8")


def tiles() -> list[Any]:
    """The page's tiles as data, the way the client saves them."""
    return [
        json.loads(html.unescape(raw))
        for raw in re.findall(r'data-grid-data="([^"]*)"', deals_page())
    ]


def tile(name: str) -> Any:
    """One tile, by the start of its full title."""
    return next(
        t for t in tiles() if t["fullTitle"].removeprefix("- ").startswith(name)
    )

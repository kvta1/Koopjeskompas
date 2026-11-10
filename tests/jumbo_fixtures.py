"""Jumbo's pages as captured on 2026-11-10, and a way to build pages from data.

``overview.json`` is the real overview's data, unpacked and trimmed to one
promotion per case the parser handles. ``promotion_3021834.html`` is a real
promotion page (Campina Vla), trimmed to its data script.
"""

import json
from pathlib import Path
from typing import Any

JUMBO_FIXTURES = Path(__file__).parent / "fixtures" / "jumbo"


def overview_data() -> Any:
    return json.loads((JUMBO_FIXTURES / "overview.json").read_text(encoding="utf-8"))


def vla_page() -> str:
    return (JUMBO_FIXTURES / "promotion_3021834.html").read_text(encoding="utf-8")


def pack(value: Any) -> list[Any]:
    """The reverse of ``nuxt.unpack``: a value as a devalue table, as Nuxt writes it."""
    table: list[Any] = []

    def add(item: Any) -> int:
        position = len(table)
        table.append(None)  # reserve the spot; children come after it
        if isinstance(item, dict):
            table[position] = {key: add(child) for key, child in item.items()}
        elif isinstance(item, list):
            table[position] = [add(child) for child in item]
        else:
            table[position] = item
        return position

    add(value)
    return table


def page_with(value: Any) -> str:
    """A minimal page embedding ``value`` the way a Nuxt site does."""
    data = json.dumps(pack(value))
    return (
        "<html><body><div id='__nuxt'>…</div>"
        f'<script type="application/json" id="__NUXT_DATA__">{data}</script>'
        "</body></html>"
    )

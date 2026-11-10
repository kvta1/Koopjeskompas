"""Read the data a Nuxt page embeds for the browser: the ``__NUXT_DATA__`` script.

Shared by the sources of chains whose sites are built with Nuxt (Jumbo, Lidl).

Nuxt renders each page on the server and sends the data it used along, so the
browser needn't fetch it again. That data is in the
*devalue* format: one flat JSON array in which objects and arrays hold positions
in that same array instead of values. A value used twice is stored once, and
cycles are possible. Some entries are markers instead: ``["Date", "2026-11-04"]``,
or ``["Reactive", 5]`` for a Vue reactive wrapper around entry 5.

This module only unpacks; what the data means is each chain's ``payloads.py``.
"""

import json
import re
from typing import Any

_SCRIPT = re.compile(
    r'<script[^>]*\bid="__NUXT_DATA__"[^>]*>(?P<data>.*?)</script>', re.DOTALL
)

# devalue's negative positions stand for values that JSON can't hold.
_SPECIAL: dict[int, Any] = {
    -1: None,  # undefined
    -2: None,  # a hole in a sparse array
    -3: float("nan"),
    -4: float("inf"),
    -5: float("-inf"),
    -6: -0.0,
}
# Markers that just wrap the entry they point at.
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "NuxtError"}


class NuxtDataError(ValueError):
    """The page has no embedded data, or data this module doesn't understand."""


def page_data(html: str) -> Any:
    """The data embedded in a Nuxt page, unpacked into plain dicts and lists."""
    return unpack_json(script_json(html))


def script_json(html: str) -> str:
    """Just the ``__NUXT_DATA__`` script's text: a fraction of the page, and all the
    data in it. What a source saves as the raw answer."""
    match = _SCRIPT.search(html)
    if match is None:
        raise NuxtDataError("the page has no __NUXT_DATA__")
    return match["data"]


def unpack_json(text: str) -> Any:
    """Unpack the text ``script_json`` returned."""
    try:
        table = json.loads(text)
    except ValueError as error:
        raise NuxtDataError("__NUXT_DATA__ is not JSON") from error
    return unpack(table)


def unpack(table: Any) -> Any:
    """Rebuild the value at position 0 of a devalue table."""
    if not isinstance(table, list) or not table:
        raise NuxtDataError("devalue data must be a non-empty array")
    built: dict[int, Any] = {}

    def value(position: int) -> Any:
        if position < 0:
            return _SPECIAL[position]
        if position in built:  # shared, or a cycle back to an object being built
            return built[position]
        entry = table[position]
        if isinstance(entry, dict):
            result: dict[str, Any] = {}
            built[position] = result
            for key, item in entry.items():
                result[key] = value(item)
            return result
        if isinstance(entry, list):
            return (
                marker(position, entry)
                if entry and isinstance(entry[0], str)
                else (array(position, entry))
            )
        return entry  # a string, number, boolean or null: itself

    def array(position: int, entry: list[Any]) -> list[Any]:
        result: list[Any] = []
        built[position] = result
        result.extend(value(item) for item in entry)
        return result

    def marker(position: int, entry: list[Any]) -> Any:
        # A plain array only ever holds positions, so a string first means a marker.
        kind, *args = entry
        if kind in _WRAPPERS:
            result = value(args[0])
        elif kind in ("EmptyRef", "EmptyShallowRef"):
            result = None
        elif kind in ("Date", "BigInt", "RegExp"):
            result = args[0]  # kept as text: an ISO date, digits, a pattern
        elif kind == "Set":
            result = [value(item) for item in args]
        elif kind == "Map":  # key position, value position, ...
            result = {str(value(k)): value(v) for k, v in zip(args[::2], args[1::2])}
        elif kind == "null":  # an object without prototype: key text, value position
            result = {k: value(v) for k, v in zip(args[::2], args[1::2])}
        else:
            raise NuxtDataError(f"unknown devalue marker {kind!r}")
        built[position] = result
        return result

    return value(0)

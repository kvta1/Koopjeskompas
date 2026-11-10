"""Lidl as a ``DealSource``: the client and the parser, behind one interface."""

from datetime import date
from pathlib import Path
from typing import Any

from koopjeskompas.ingestion.lidl.client import LidlClient, load_raw_tiles
from koopjeskompas.ingestion.lidl.parser import parse_tiles
from koopjeskompas.ingestion.source import SourceResult


class LidlSource:
    chain = "Lidl"

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        # The page shows whatever is on offer now: ``day`` isn't needed.
        return _result(LidlClient(raw_dir).fetch_tiles())

    def reparse(self, raw_dir: Path, day: date) -> SourceResult:
        return _result(load_raw_tiles(raw_dir))


def _result(tiles: list[Any]) -> SourceResult:
    parsed = parse_tiles(tiles)
    notes = []
    if parsed.lidl_plus:
        notes.append(f"Lidl Plus deals (need the app): {parsed.lidl_plus}")
    if parsed.left_out:
        reasons = ", ".join(f"{n} {why}" for why, n in parsed.left_out.most_common())
        notes.append(f"Left out: {reasons}")
    dated = [d for d in parsed.deals if d.valid_from != date.min]
    span = (
        f"{min(d.valid_from for d in dated)} to {max(d.valid_to for d in dated)}"
        if dated
        else "(dates unknown)"
    )
    return SourceResult(
        title=f"Lidl deals {span}",
        deals=parsed.deals,
        notes=notes,
        skipped=parsed.skipped,
        no_discount=parsed.no_discount,
    )

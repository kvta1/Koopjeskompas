"""Jumbo as a ``DealSource``: the client and the parser, behind one interface."""

import re
from datetime import date
from pathlib import Path

from koopjeskompas.ingestion.jumbo.client import JumboClient, load_raw_week
from koopjeskompas.ingestion.jumbo.parser import parse_week
from koopjeskompas.ingestion.jumbo.payloads import JumboWeek, OverviewPage
from koopjeskompas.ingestion.source import SourceResult

# A week's id, e.g. "actieprijs_20261104-20261110".
_WEEK_ID = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{4})(\d{2})(\d{2})$")


class JumboSource:
    chain = "Jumbo"

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        # The overview always shows the current and next week: ``day`` isn't needed.
        return _result(JumboClient(raw_dir).fetch_week())

    def reparse(self, raw_dir: Path, day: date) -> SourceResult:
        return _result(load_raw_week(raw_dir))


def _result(week: JumboWeek) -> SourceResult:
    parsed = parse_week(week)
    notes = []
    if parsed.priced:
        notes.append(
            f"Promotions priced per product: {parsed.priced} ({parsed.products} products)"
        )
    if week.failed:
        notes.append(
            f"Promotion pages that failed or are missing: {len(week.failed)}; "
            "those promotions stay unscored"
        )
    if parsed.left_out:
        reasons = ", ".join(f"{n} {why}" for why, n in parsed.left_out.most_common())
        notes.append(f"Left out: {reasons}")
    return SourceResult(
        title=f"Jumbo deals {_weeks(week)}",
        deals=parsed.deals,
        notes=notes,
        skipped=parsed.skipped,
        no_discount=parsed.no_discount,
    )


def _weeks(week: JumboWeek) -> str:
    """ "2026-11-04 to 2026-11-17": from the first week's start to the last one's end."""
    spans = [
        m.groups()
        for runtime in OverviewPage.model_validate(week.overview).runtimes
        if (m := _WEEK_ID.search(runtime.id))
    ]
    if not spans:
        return "(weeks unknown)"
    starts = sorted("-".join(s[:3]) for s in spans)
    ends = sorted("-".join(s[3:]) for s in spans)
    return f"{starts[0]} to {ends[-1]}"

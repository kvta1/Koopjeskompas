"""Albert Heijn as a ``DealSource``: the client and the parser, behind one interface."""

from datetime import date
from pathlib import Path

from koopjeskompas.ingestion.ah.client import AhClient, load_raw_week
from koopjeskompas.ingestion.ah.parser import parse_bonus_week
from koopjeskompas.ingestion.ah.payloads import BonusWeek
from koopjeskompas.ingestion.source import SourceResult


class AhSource:
    chain = "AH"

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        return _result(AhClient(raw_dir=raw_dir).fetch_bonus_week(day))

    def reparse(self, raw_dir: Path, day: date) -> SourceResult:
        return _result(load_raw_week(raw_dir, day))


def _result(week: BonusWeek) -> SourceResult:
    parsed = parse_bonus_week(week)
    notes = []
    if parsed.ranges_priced:
        notes.append(
            f"Range deals priced per product: {parsed.ranges_priced} "
            f"({parsed.range_products} products)"
        )
    if week.failed_sections:
        notes.append(f"Sections that failed: {', '.join(week.failed_sections)}")
    if week.failed_ranges:
        notes.append(
            f"Range lookups that failed or are missing: {len(week.failed_ranges)}; "
            "those ranges stay unscored"
        )
    period = week.period
    return SourceResult(
        title=f"AH bonus {period.bonus_start_date} to {period.bonus_end_date}",
        deals=parsed.deals,
        notes=notes,
        skipped=parsed.skipped,
        no_discount=parsed.no_discount,
    )

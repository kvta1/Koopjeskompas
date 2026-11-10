"""What every deal source has in common: one per supermarket chain.

A source fetches its chain's current deals, saves the raw answers before parsing
anything, and turns them into validated ``Deal``s. Each chain's site works
differently (AH: an app API; Jumbo: the data embedded in its web pages), so all
of that stays inside the chain's own package under ``ingestion/``; this interface
is the only thing the CLI knows about.

``fetch-deals`` runs every source on its own: one chain failing doesn't stop the
others, and what did work is still saved.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from koopjeskompas.domain.models import Deal


class SourceError(RuntimeError):
    """A source couldn't get its deals at all; the message says why."""


@dataclass
class SourceResult:
    # Which deals these are, for the summary, e.g. "AH bonus 2026-11-09 to 2026-11-15".
    title: str
    deals: list[Deal]
    # Lines worth telling whoever ran the fetch, e.g. how many lookups failed.
    notes: list[str] = field(default_factory=list)
    # Items left out because they couldn't be read (each also logged as a warning).
    skipped: list[str] = field(default_factory=list)
    # Deal texts kept, but without a determinable discount, so they score zero.
    no_discount: Counter[str] = field(default_factory=Counter)


class DealSource(Protocol):
    # The chain's name as stores carry it (Store.chain): deals and stores meet on it.
    chain: str

    def fetch(self, raw_dir: Path, day: date) -> SourceResult:
        """Fetch the deals that apply on ``day``, saving raw answers in ``raw_dir``."""
        ...

    def reparse(self, raw_dir: Path, day: date) -> SourceResult:
        """Parse what an earlier ``fetch`` saved in ``raw_dir``, without the network."""
        ...

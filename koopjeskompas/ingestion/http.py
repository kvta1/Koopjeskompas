"""Polite HTTP for the deal sources that read web pages (Jumbo, Lidl).

What each such source needs, in one place, following the scraping policy in
PLAN.md §9.4 step 3:

- one request at a time, with a fixed pause between them, and a timeout;
- every answer saved to the raw directory before anything parses it, so a parser
  fix never needs a refetch (``reparse`` reads them back);
- a block recognised as one (403, 429, or a page without the expected data). After a
  block the client refuses further requests for this run: asking again at once
  would only look more like a bot, and the rest of the source's pages can wait for
  next week.

Sites that block an honest identity may be asked with ``BROWSER_HEADERS``: that is
the one disguise the policy allows. Nothing here solves CAPTCHAs, rotates proxies or
forges bot-detection data.
"""

import logging
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NoReturn

import httpx

from koopjeskompas.ingestion.source import SourceError

logger = logging.getLogger(__name__)

# Our own name, plus what any well-behaved client says it accepts. Lidl's CDN answers
# 503 to a request with a User-Agent alone, and 200 to the same one with these.
HONEST_HEADERS = {
    "User-Agent": "koopjeskompas/0.1 (+https://github.com/kvta1/Koopjeskompas)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}
# A desktop browser's identity, for sites that block the honest one.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}
_BLOCKING_STATUSES = {403, 429}


class FetchError(SourceError):
    """One page couldn't be fetched: not found, a server error, a timeout."""


class BlockedError(FetchError):
    """The site refused us. No further requests this run."""


class PoliteClient:
    def __init__(
        self,
        base_url: str,
        raw_dir: Path,
        headers: Mapping[str, str] = HONEST_HEADERS,
        delay_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        http: httpx.Client | None = None,
    ) -> None:
        self._raw_dir = raw_dir
        self._http = http or httpx.Client(timeout=30, follow_redirects=True)
        self._http.base_url = httpx.URL(base_url)
        self._http.headers.update(headers)
        self._delay_s = delay_s
        self._sleep = sleep
        self._asked_before = False
        self._blocked_because: str | None = None

    def get_text(
        self, path: str, save_as: str, keep: Callable[[str], str] | None = None
    ) -> str:
        """GET ``path`` and return its body, saved as ``save_as`` in the raw directory.

        ``keep`` picks out the part worth keeping before it's saved and returned, such
        as a page's embedded data without its layout. If it raises, nothing is saved.
        """
        if self._blocked_because is not None:
            raise BlockedError(f"not asking again this run: {self._blocked_because}")
        if self._asked_before:
            self._sleep(self._delay_s)
        self._asked_before = True

        url = self._http.base_url.join(path)
        try:
            response = self._http.get(path)
        except httpx.HTTPError as error:
            raise FetchError(f"{url} could not be fetched: {error}") from error
        if response.status_code in _BLOCKING_STATUSES:
            self.blocked(f"{url} answered {response.status_code}")
        if not response.is_success:
            raise FetchError(f"{url} answered {response.status_code}")

        text = keep(response.text) if keep else response.text
        self._save(save_as, text)
        return text

    def blocked(self, reason: str) -> NoReturn:
        """Note a block, for instance a 200 page that is a bot check, and stop."""
        self._blocked_because = reason
        logger.warning("blocked: %s", reason)
        raise BlockedError(reason)

    def read_saved(self, name: str) -> str:
        """An answer an earlier run saved, for ``reparse``."""
        return (self._raw_dir / name).read_text(encoding="utf-8")

    def _save(self, name: str, text: str) -> None:
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        (self._raw_dir / name).write_text(text, encoding="utf-8")

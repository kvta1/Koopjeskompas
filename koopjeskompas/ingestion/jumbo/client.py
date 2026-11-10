"""HTTP access to Jumbo's deal pages, through the polite client.

One request for the overview (this week's and next week's promotions), then one per
promotion whose discount depends on a price, for its products: about 110 a week,
one second apart. Only each page's embedded data is saved (``nuxt.script_json``):
about 5 MB a week instead of 85 MB of full pages.

Jumbo's site is behind Akamai Bot Manager, which drops requests that identify
themselves honestly (PLAN.md §9.4, step 3). So this client presents itself as a
browser, as the scraping policy allows; nothing more. A page without its data is
taken for a bot check: that ends this run's requests, and the promotions fetched so
far are kept.
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from koopjeskompas.ingestion.http import (
    BROWSER_HEADERS,
    BlockedError,
    FetchError,
    PoliteClient,
)
from koopjeskompas.ingestion.jumbo.parser import promotions_needing_prices
from koopjeskompas.ingestion.jumbo.payloads import JumboWeek
from koopjeskompas.ingestion.nuxt import NuxtDataError, script_json, unpack_json
from koopjeskompas.ingestion.source import SourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jumbo.com"
OVERVIEW_PATH = "/aanbiedingen/nu"
OVERVIEW_FILE = "overview.json"


def promotion_file(promotion_id: str) -> str:
    return f"promotion_{promotion_id}.json"


class JumboClient:
    def __init__(
        self,
        raw_dir: Path,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = PoliteClient(
            BASE_URL, raw_dir, BROWSER_HEADERS, sleep=sleep, http=http
        )

    def fetch_week(self) -> JumboWeek:
        """The overview, then the page of each promotion that needs a price."""
        week = JumboWeek(overview=self._page(OVERVIEW_PATH, OVERVIEW_FILE))
        needing = promotions_needing_prices(week.overview)
        for done, promotion in enumerate(needing):
            try:
                week.promotions[promotion.id] = self._page(
                    promotion.url, promotion_file(promotion.id)
                )
            except BlockedError as error:
                # Stop asking; what came in so far still counts.
                rest = [p.id for p in needing[done:]]
                logger.warning("stopping after a block (%s); %d left", error, len(rest))
                week.failed.extend(rest)
                break
            except FetchError as error:
                logger.warning("skipping promotion %s: %s", promotion.id, error)
                week.failed.append(promotion.id)
        return week

    def _page(self, path: str, save_as: str) -> Any:
        try:
            text = self._client.get_text(path, save_as, keep=script_json)
        except NuxtDataError:
            self._client.blocked(f"{path} came without its data: a bot check?")
        return unpack_json(text)


def load_raw_week(raw_dir: Path) -> JumboWeek:
    """Rebuild a ``JumboWeek`` from the pages an earlier fetch saved in ``raw_dir``."""
    try:
        overview = unpack_json((raw_dir / OVERVIEW_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SourceError(f"no saved Jumbo pages in {raw_dir}") from error
    week = JumboWeek(overview=overview)
    for promotion in promotions_needing_prices(overview):
        path = raw_dir / promotion_file(promotion.id)
        if path.exists():
            week.promotions[promotion.id] = unpack_json(
                path.read_text(encoding="utf-8")
            )
        else:
            week.failed.append(promotion.id)
    return week

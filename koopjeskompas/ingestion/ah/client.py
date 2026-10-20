"""HTTP access to Albert Heijn's (unofficial) mobile API.

Fetches the national bonus sections for one bonus week: an anonymous token, the bonus
metadata (which lists one section URL per category), then each NATIONAL section. Every
raw response is written to disk before anything parses it, so a parser bug never
forces a refetch.

Politeness: one run per week, a fixed delay between requests, a timeout, no retries.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from koopjeskompas.ingestion.ah.payloads import (
    BonusMetadata,
    BonusPeriod,
    BonusWeek,
    SectionMetadata,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ah.nl"
HEADERS = {
    "User-Agent": "Appie/8.8.2 Model/phone Android/7.0-API24",
    "x-application": "AHWEBSHOP",
}
TOKEN_PATH = "/mobile-auth/v1/auth/token/anonymous"
METADATA_PATH = "/mobile-services/bonuspage/v3/metadata"
SECTION_PREFIX = "/mobile-services/"
METADATA_FILE = "metadata.json"


class AhApiError(RuntimeError):
    """The AH API could not be reached or answered with something unusable."""


class AhClient:
    def __init__(
        self,
        raw_dir: Path,
        http: httpx.Client | None = None,
        delay_s: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._raw_dir = raw_dir
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=30)
        self._http.headers.update(HEADERS)
        self._delay_s = delay_s
        self._sleep = sleep or time.sleep

    def fetch_bonus_week(self, day: date) -> BonusWeek:
        """Fetch every national food section of the bonus week containing ``day``."""
        self._authenticate()
        metadata = _parse_metadata(self._get_json(METADATA_PATH, METADATA_FILE))
        period = _period_containing(metadata, day)

        week = BonusWeek(period=period, sections=[])
        for meta in period.food_sections():
            path = SECTION_PREFIX + meta.url
            try:
                week.sections.append(self._get_json(path, section_filename(meta)))
            except AhApiError as error:
                # One broken category should not cost us the rest of the week.
                logger.warning("skipping section %r: %s", meta.description, error)
                week.failed_sections.append(meta.description)
        return week

    def _authenticate(self) -> None:
        payload = self._request("POST", TOKEN_PATH, json={"clientId": "appie"})
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str):
            raise AhApiError("token response has no access_token")
        self._http.headers["Authorization"] = f"Bearer {token}"

    def _get_json(self, path: str, raw_name: str) -> Any:
        payload = self._request("GET", path)
        self._save_raw(raw_name, payload)
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        self._sleep(self._delay_s)
        try:
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            raise AhApiError(f"{method} {path} returned HTTP {status}") from error
        except httpx.HTTPError as error:
            raise AhApiError(f"{method} {path} failed: {error}") from error
        except ValueError as error:
            raise AhApiError(f"{method} {path} did not return JSON") from error

    def _save_raw(self, name: str, payload: Any) -> None:
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        path = self._raw_dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))


def load_raw_week(raw_dir: Path, day: date) -> BonusWeek:
    """Rebuild a ``BonusWeek`` from responses an earlier fetch saved in ``raw_dir``.

    Lets the parser be rerun (after a fix, say) without asking AH again.
    """
    try:
        metadata = _parse_metadata(_read_json(raw_dir / METADATA_FILE))
    except FileNotFoundError as error:
        raise AhApiError(f"no saved responses in {raw_dir}") from error
    week = BonusWeek(period=_period_containing(metadata, day), sections=[])
    for meta in week.period.food_sections():
        try:
            week.sections.append(_read_json(raw_dir / section_filename(meta)))
        except FileNotFoundError:
            week.failed_sections.append(meta.description)
    return week


def section_filename(meta: SectionMetadata) -> str:
    return f"section_{_slug(meta.description)}.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _parse_metadata(payload: Any) -> BonusMetadata:
    try:
        return BonusMetadata.model_validate(payload)
    except ValidationError as error:
        raise AhApiError(f"unexpected bonus metadata shape: {error}") from error


def _period_containing(metadata: BonusMetadata, day: date) -> BonusPeriod:
    for period in metadata.periods:
        if period.bonus_start_date <= day <= period.bonus_end_date:
            return period
    raise AhApiError(f"no bonus period covers {day.isoformat()}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

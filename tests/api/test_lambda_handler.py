"""The Lambda entry point, fed events shaped like the ones a Function URL sends.

No AWS involved: S3 is a fake that copies a local file, and the events are built
here in the documented "version 2.0" payload format that Function URLs use.
"""

import json
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import boto3
import pytest
from botocore.exceptions import ClientError
from mangum.types import LambdaContext

from koopjeskompas.api import lambda_handler
from koopjeskompas.api.lambda_handler import (
    NoSnapshotsError,
    build_handler,
    download_snapshots,
)
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.cache import save_deals

BUCKET = "koopjeskompas-data"
KEY = "deals/ah.json"
CONTEXT = cast(LambdaContext, SimpleNamespace())  # Mangum only passes it on
LEIDEN_CENTRAAL = {"lat": 52.1664, "lon": 4.4817}


class FakeS3:
    """Serves objects from local files, like ``download_file`` serves them from S3."""

    def __init__(self, objects: dict[tuple[str, str], Path]) -> None:
        self.objects = objects
        self.downloads: list[tuple[str, str]] = []

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self.downloads.append((Bucket, Key))
        if (Bucket, Key) not in self.objects:
            # What S3 answers a role that may read objects but not list the bucket.
            error = {"Error": {"Code": "403", "Message": "Forbidden"}}
            raise ClientError(error, "HeadObject")  # type: ignore[arg-type]
        shutil.copyfile(self.objects[Bucket, Key], Filename)


@pytest.fixture
def s3(tmp_path: Path) -> FakeS3:
    snapshot = tmp_path / "snapshot.json"
    deal = Deal(
        chain="AH",
        product_name="AH Hummus naturel",
        mechanic_string="25% korting",
        valid_from=date(2026, 11, 2),
        valid_to=date(2026, 11, 8),
    )
    save_deals(snapshot, [deal])
    return FakeS3({(BUCKET, KEY): snapshot})


def function_url_event(
    method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A minimal Function URL request event (payload format version 2.0)."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {
            "host": "abc123.lambda-url.eu-north-1.on.aws",
            "content-type": "application/json",
        },
        "requestContext": {
            "domainName": "abc123.lambda-url.eu-north-1.on.aws",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "192.0.2.1",
                "userAgent": "pytest",
            },
            "requestId": "test-request",
            "routeKey": "$default",
            "stage": "$default",
        },
        "body": None if body is None else json.dumps(body),
        "isBase64Encoded": False,
    }


def test_each_chains_snapshot_lands_where_the_app_reads_it(
    s3: FakeS3, tmp_path: Path
) -> None:
    # Only AH's snapshot is in the bucket: Jumbo and Lidl are skipped, not errors.
    assert download_snapshots(s3, BUCKET, tmp_path / "data") == ["AH"]
    assert (tmp_path / "data" / "deals" / "ah.json").exists()
    assert [key for _, key in s3.downloads] == [
        "deals/ah.json",
        "deals/jumbo.json",
        "deals/lidl.json",
    ]


def test_an_empty_bucket_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(NoSnapshotsError):
        download_snapshots(FakeS3({}), BUCKET, tmp_path / "data")


def test_other_s3_errors_are_not_mistaken_for_a_missing_snapshot(
    tmp_path: Path,
) -> None:
    class Throttled(FakeS3):
        def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
            error = {"Error": {"Code": "SlowDown", "Message": "Slow down"}}
            raise ClientError(error, "GetObject")  # type: ignore[arg-type]

    with pytest.raises(ClientError):
        download_snapshots(Throttled({}), BUCKET, tmp_path / "data")


def test_the_handler_answers_function_url_events(s3: FakeS3, tmp_path: Path) -> None:
    handler = build_handler(s3, BUCKET, data_dir=tmp_path / "data")

    health = handler(function_url_event("GET", "/api/health"), CONTEXT)
    assert health["statusCode"] == 200
    assert json.loads(health["body"]) == {"status": "ok"}

    ranked = handler(
        function_url_event("POST", "/api/rank", {"location": LEIDEN_CENTRAAL}),
        CONTEXT,
    )
    assert ranked["statusCode"] == 200, ranked["body"]
    assert json.loads(ranked["body"])["stores"]

    invalid = handler(function_url_event("POST", "/api/rank", {}), CONTEXT)
    assert invalid["statusCode"] == 422


@pytest.fixture
def from_environment(
    s3: FakeS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeS3]:
    """``handler`` as AWS calls it: configured by environment variables."""
    monkeypatch.setattr(boto3, "client", lambda service: s3)
    monkeypatch.setattr(lambda_handler, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("DEALS_BUCKET", BUCKET)
    lambda_handler._handler_from_environment.cache_clear()
    yield s3
    lambda_handler._handler_from_environment.cache_clear()


def test_handler_downloads_once_per_environment(from_environment: FakeS3) -> None:
    for _ in range(3):
        response = lambda_handler.handler(
            function_url_event("GET", "/api/health"), CONTEXT
        )
        assert response["statusCode"] == 200
    # One cold start: each chain asked for once, not once per request.
    assert len(from_environment.downloads) == 3


def test_a_failed_download_is_retried_on_the_next_request(
    from_environment: FakeS3,
) -> None:
    snapshot = from_environment.objects.pop((BUCKET, KEY))
    with pytest.raises(NoSnapshotsError):
        lambda_handler.handler(function_url_event("GET", "/api/health"), CONTEXT)

    from_environment.objects[BUCKET, KEY] = snapshot
    response = lambda_handler.handler(function_url_event("GET", "/api/health"), CONTEXT)
    assert response["statusCode"] == 200

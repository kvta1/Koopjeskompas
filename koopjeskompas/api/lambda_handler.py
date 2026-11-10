"""AWS Lambda entry point: the same FastAPI app, with Mangum in front of it.

Locally, uvicorn is the server: it listens on a port, turns HTTP bytes into ASGI calls
to the app and the app's answers back into bytes. On Lambda nothing listens. AWS
calls ``handler`` once per request with the request as a JSON event (from the
Function URL) and expects a dict back. Mangum translates that event into an ASGI
call and the app's answer into that dict. The app can't tell the difference, so
``create_app`` is used unchanged; only the thing in front of it differs.

The deals come from S3: a Lambda has none of the laptop's ``data/`` directory. Each
chain's snapshot (``deals/ah.json``, ``deals/jumbo.json``, ...) is downloaded once
per execution environment (a "cold start") into ``/tmp``, the only writable place
in a Lambda, where ``create_app`` reads them as it would locally. A chain without a
snapshot is left out; with none at all, the request fails and the next one tries
again. A new upload reaches new environments, not ones that are already warm; those
are recycled within hours, or at once by any change to the function's configuration.

The bucket comes from the ``DEALS_BUCKET`` environment variable, so the code names
none.
"""

import logging
import os
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError
from mangum import Mangum
from mangum.types import LambdaContext, LambdaEvent

from koopjeskompas.api.app import create_app
from koopjeskompas.chains import CHAINS
from koopjeskompas.ingestion.cache import deals_path
from koopjeskompas.publish import DEALS_PREFIX

DATA_DIR = Path("/tmp/koopjeskompas")
# What S3 answers for a key that isn't there: 404, or 403 for a role that may read
# objects but not list the bucket, as this one (least privilege).
_MISSING = {"404", "NoSuchKey", "403", "AccessDenied"}

logger = logging.getLogger(__name__)


class S3Downloader(Protocol):
    """The one S3 call we make; boto3's S3 client fits it, and so does a test fake."""

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...


class NoSnapshotsError(RuntimeError):
    """No chain's snapshot is in the bucket: nothing to rank with."""


def download_snapshots(s3: S3Downloader, bucket: str, data_dir: Path) -> list[str]:
    """Copy each chain's snapshot from S3 to where ``create_app`` looks for it.

    Returns the chains found. A chain without a snapshot is skipped with a warning,
    so one chain's missing upload doesn't take the others down.
    """
    found = []
    for chain in CHAINS:
        key = f"{DEALS_PREFIX}{chain.key}.json"  # where publish-deals puts it
        path = deals_path(data_dir, chain.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            s3.download_file(Bucket=bucket, Key=key, Filename=str(path))
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code not in _MISSING:
                raise
            logger.warning(
                "No snapshot at s3://%s/%s (%s); skipping", bucket, key, code
            )
            continue
        logger.info("Downloaded s3://%s/%s", bucket, key)
        found.append(chain.name)
    if not found:
        raise NoSnapshotsError(f"no snapshot in s3://{bucket}/{DEALS_PREFIX}")
    return found


def build_handler(s3: S3Downloader, bucket: str, data_dir: Path = DATA_DIR) -> Mangum:
    download_snapshots(s3, bucket, data_dir)
    # lifespan="off": the app has no startup or shutdown hooks for Mangum to run.
    return Mangum(create_app(data_dir=data_dir), lifespan="off")


@cache
def _handler_from_environment() -> Mangum:
    # Built on the first request rather than at import, so importing this module
    # (in tests, say) needs no AWS. @cache keeps it for the environment's lifetime;
    # if the download fails, nothing is cached and the next request tries again.
    return build_handler(boto3.client("s3"), bucket=os.environ["DEALS_BUCKET"])


def handler(event: LambdaEvent, context: LambdaContext) -> dict[str, Any]:
    """What the Lambda function's handler setting points at:
    ``koopjeskompas.api.lambda_handler.handler``."""
    return _handler_from_environment()(event, context)

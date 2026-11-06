"""AWS Lambda entry point: the same FastAPI app, with Mangum in front of it.

Locally, uvicorn is the server: it listens on a port, turns HTTP bytes into ASGI calls
to the app and the app's answers back into bytes. On Lambda nothing listens. AWS
calls ``handler`` once per request with the request as a JSON event (from the
Function URL) and expects a dict back. Mangum translates that event into an ASGI
call and the app's answer into that dict. The app can't tell the difference, so
``create_app`` is used unchanged; only the thing in front of it differs.

The deals come from S3: a Lambda has none of the laptop's ``data/`` directory. The
snapshot is downloaded once per execution environment (a "cold start") into
``/tmp``, the only writable place in a Lambda, where ``create_app`` reads it as it
would locally. A new upload therefore reaches new environments, not ones that are
already warm; those are recycled within hours, or at once by any change to the
function's configuration.

Configuration comes from environment variables set on the function, so the code
names no bucket:

- ``DEALS_BUCKET``: the bucket holding the snapshot (required)
- ``DEALS_KEY``: its key (default ``deals/ah.json``)
"""

import logging
import os
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from mangum import Mangum
from mangum.types import LambdaContext, LambdaEvent

from koopjeskompas.api.app import CHAIN, create_app
from koopjeskompas.ingestion.cache import deals_path
from koopjeskompas.publish import DEALS_PREFIX

DATA_DIR = Path("/tmp/koopjeskompas")
DEFAULT_DEALS_KEY = f"{DEALS_PREFIX}{CHAIN.lower()}.json"  # where publish-deals puts it

logger = logging.getLogger(__name__)


class S3Downloader(Protocol):
    """The one S3 call we make; boto3's S3 client fits it, and so does a test fake."""

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...


def download_deals(s3: S3Downloader, bucket: str, key: str, data_dir: Path) -> Path:
    """Copy the deals snapshot from S3 to where ``create_app`` looks for it."""
    path = deals_path(data_dir, CHAIN)
    path.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(Bucket=bucket, Key=key, Filename=str(path))
    logger.info("Downloaded s3://%s/%s to %s", bucket, key, path)
    return path


def build_handler(
    s3: S3Downloader, bucket: str, key: str, data_dir: Path = DATA_DIR
) -> Mangum:
    download_deals(s3, bucket, key, data_dir)
    # lifespan="off": the app has no startup or shutdown hooks for Mangum to run.
    return Mangum(create_app(data_dir=data_dir), lifespan="off")


@cache
def _handler_from_environment() -> Mangum:
    # Built on the first request rather than at import, so importing this module
    # (in tests, say) needs no AWS. @cache keeps it for the environment's lifetime;
    # if the download fails, nothing is cached and the next request tries again.
    return build_handler(
        boto3.client("s3"),
        bucket=os.environ["DEALS_BUCKET"],
        key=os.environ.get("DEALS_KEY", DEFAULT_DEALS_KEY),
    )


def handler(event: LambdaEvent, context: LambdaContext) -> dict[str, Any]:
    """What the Lambda function's handler setting points at:
    ``koopjeskompas.api.lambda_handler.handler``."""
    return _handler_from_environment()(event, context)

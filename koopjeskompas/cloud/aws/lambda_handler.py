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

import os
from functools import cache
from pathlib import Path
from typing import Any

import boto3
from mangum import Mangum
from mangum.types import LambdaContext, LambdaEvent

from koopjeskompas.api.app import create_app
from koopjeskompas.cloud.aws.s3 import S3Client, S3Snapshots
from koopjeskompas.cloud.snapshots import download_snapshots

DATA_DIR = Path("/tmp/koopjeskompas")


def build_handler(s3: S3Client, bucket: str, data_dir: Path = DATA_DIR) -> Mangum:
    download_snapshots(S3Snapshots(s3, bucket), data_dir)
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
    ``koopjeskompas.cloud.aws.lambda_handler.handler``."""
    return _handler_from_environment()(event, context)

"""Publish the deal snapshots to the AWS demo: ``koopjeskompas publish-deals``.

``fetch-deals`` keeps running on the laptop (PLAN.md §9.3: AWS never contacts AH);
this uploads its result, one ``data/deals/<chain>.json`` per chain, to the data
bucket that the API's Lambda reads from. The bucket's name is read from the CDK
stack's outputs, so it never has to be copied by hand.

The names shared with the infrastructure live here, and ``infra/stack.py`` imports
them: the app package must not depend on ``infra/``, which isn't part of it.

A new snapshot reaches new Lambda environments; warm ones keep the old one until
AWS recycles them, within hours (see ``cloud/aws/lambda_handler.py``).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

REGION = "eu-north-1"  # this AWS project can only create resources here
STACK_NAME = "Koopjeskompas"
DATA_BUCKET_OUTPUT = "DataBucketName"
DEALS_PREFIX = "deals/"  # deals/ah.json, deals/jumbo.json, ...


class PublishError(Exception):
    """Publishing can't start; the message says why and what to do."""


class S3Uploader(Protocol):
    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None: ...


class StackDescriber(Protocol):
    def describe_stacks(self, *, StackName: str) -> Mapping[str, Any]: ...


def find_data_bucket(cloudformation: StackDescriber, stack_name: str) -> str:
    """The data bucket's name, from the deployed stack's outputs."""
    (stack,) = cloudformation.describe_stacks(StackName=stack_name)["Stacks"]
    for output in stack.get("Outputs", []):
        if output["OutputKey"] == DATA_BUCKET_OUTPUT:
            name: str = output["OutputValue"]
            return name
    raise PublishError(
        f"Stack {stack_name} has no {DATA_BUCKET_OUTPUT} output; deploy it first "
        "(scripts/deploy.sh)."
    )


def snapshots(deals_dir: Path) -> list[Path]:
    """The chain snapshots that fetch-deals wrote, e.g. data/deals/ah.json."""
    found = sorted(deals_dir.glob("*.json"))
    if not found:
        raise PublishError(
            f"No snapshots in {deals_dir}; run 'koopjeskompas fetch-deals' first."
        )
    return found


def publish_deals(s3: S3Uploader, bucket: str, files: Sequence[Path]) -> list[str]:
    """Upload each snapshot under ``deals/``; returns the keys written."""
    keys = []
    for path in files:
        key = f"{DEALS_PREFIX}{path.name}"
        s3.upload_file(
            Filename=str(path),
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/json"},
        )
        keys.append(key)
    return keys

"""Publish the deal snapshots to a demo: ``koopjeskompas publish-deals``.

``fetch-deals`` keeps running on the laptop (PLAN.md §9.3: the cloud never contacts
the supermarkets); this uploads its result, one ``data/deals/<chain>.json`` per chain,
to the storage the API reads from: the AWS data bucket (its name read from the CDK
stack's outputs, so it never has to be copied by hand) or the Azure Blob container.

Where to is a detail behind ``SnapshotTarget``, the write side of
``cloud/snapshots.py``'s ``SnapshotStore``; the same adapters implement both
(``cloud/aws/s3.py``, ``cloud/azure/blob.py``).

The names shared with the AWS infrastructure live here, and ``infra/stack.py`` imports
them: the app package must not depend on ``infra/``, which isn't part of it.
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


class SnapshotTarget(Protocol):
    """Where the snapshots go, by key: ``deals/ah.json``."""

    @property
    def location(self) -> str:
        """For messages: "s3://koopjeskompas-data"."""
        ...

    def upload(self, key: str, path: Path) -> None:
        """Store the file at ``path`` as ``key``, replacing what was there."""
        ...


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


def publish_deals(target: SnapshotTarget, files: Sequence[Path]) -> list[str]:
    """Upload each snapshot under ``deals/``; returns the keys written."""
    keys = []
    for path in files:
        key = f"{DEALS_PREFIX}{path.name}"
        target.upload(key, path)
        keys.append(key)
    return keys

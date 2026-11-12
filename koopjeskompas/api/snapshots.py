"""Copy each chain's deal snapshot from cloud storage to where the app reads it.

The app reads deals from a local directory (``<data_dir>/deals/ah.json``, ...), as
``fetch-deals`` writes them on the laptop. A server in the cloud has no laptop: the
weekly ``publish-deals`` uploads the same files to storage, and the server copies them
down when it starts.

Which storage is a detail: S3 for the AWS Lambda, Blob Storage for the Azure container.
So this module holds only what they share, the loop over the chains, and talks to
storage through ``SnapshotStore``, a one-method interface (a "port"). Each cloud has a
small class that fits it (an "adapter"): ``S3Snapshots`` in ``lambda_handler.py``,
``BlobSnapshots`` in ``container.py``. The same pattern as ``DealSource`` for the
supermarkets.
"""

import logging
from pathlib import Path
from typing import Protocol

from koopjeskompas.chains import CHAINS
from koopjeskompas.ingestion.cache import deals_path
from koopjeskompas.publish import DEALS_PREFIX

logger = logging.getLogger(__name__)


class SnapshotStore(Protocol):
    """Where the snapshots are kept, by key: ``deals/ah.json``."""

    @property
    def location(self) -> str:
        """For messages: "s3://koopjeskompas-data"."""
        ...

    def download(self, key: str, path: Path) -> bool:
        """Copy ``key`` to ``path``; False if there is no such snapshot.

        Any other failure (no permission, a network error) raises: that's a broken
        setup, and it shouldn't pass for a chain that has no deals this week.
        """
        ...


class NoSnapshotsError(RuntimeError):
    """No chain's snapshot is in storage: nothing to rank with."""


def download_snapshots(store: SnapshotStore, data_dir: Path) -> list[str]:
    """Copy each chain's snapshot to where ``create_app`` looks for it.

    Returns the chains found. A chain without a snapshot is skipped with a warning,
    so one chain's missing upload doesn't take the others down.
    """
    found = []
    for chain in CHAINS:
        key = f"{DEALS_PREFIX}{chain.key}.json"  # where publish-deals puts it
        path = deals_path(data_dir, chain.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not store.download(key, path):
            logger.warning("No snapshot at %s/%s; skipping", store.location, key)
            continue
        logger.info("Downloaded %s/%s", store.location, key)
        found.append(chain.name)
    if not found:
        raise NoSnapshotsError(f"no snapshot in {store.location}/{DEALS_PREFIX}")
    return found

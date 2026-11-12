"""The snapshots in a Blob Storage container: the Azure adapter for ``SnapshotStore``.

Used by a container on Azure (Container Apps) through ``DEALS_CONTAINER_URL``, and
ready for an Azure Functions entry point, should one come. No keys or passwords:
``DefaultAzureCredential`` finds an identity by itself. In Azure that's the app's
managed identity, which only needs the "Storage Blob Data Reader" role on the
container; on the laptop it's your ``az login``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from azure.core.exceptions import ResourceNotFoundError


class _Download(Protocol):
    def readall(self) -> bytes: ...


class BlobContainer(Protocol):
    """The part of the SDK's ``ContainerClient`` we use, so tests can fake it."""

    @property
    def url(self) -> str: ...

    def download_blob(self, blob: str) -> _Download: ...


@dataclass(frozen=True)
class BlobSnapshots:
    container: BlobContainer

    @property
    def location(self) -> str:
        return self.container.url

    def download(self, key: str, path: Path) -> bool:
        try:
            data = self.container.download_blob(key).readall()
        except ResourceNotFoundError:  # 404. Not 403: a missing role should be loud.
            return False
        path.write_bytes(data)
        return True


def open_blob_snapshots(url: str) -> BlobSnapshots:
    """The snapshots in the container at ``url``, e.g.
    ``https://<account>.blob.core.windows.net/data``."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    return BlobSnapshots(
        ContainerClient.from_container_url(url, credential=DefaultAzureCredential())
    )

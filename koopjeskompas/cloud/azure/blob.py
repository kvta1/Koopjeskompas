"""The snapshots in a Blob Storage container: the Azure adapter for ``SnapshotStore``
and ``SnapshotTarget``.

Read by a container on Azure (Container Apps) through ``DEALS_CONTAINER_URL``, and
ready for an Azure Functions entry point, should one come; written by
``publish-deals --cloud azure``. No keys or passwords: ``DefaultAzureCredential``
finds an identity by itself. In Azure that's the app's managed identity, which only
needs the "Storage Blob Data Reader" role on the container (with ``AZURE_CLIENT_ID``
naming it, for a user-assigned one); on the laptop it's your ``az login``, which needs
"Storage Blob Data Contributor" to upload.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import ContentSettings


class _Download(Protocol):
    def readall(self) -> bytes: ...


class BlobContainer(Protocol):
    """The part of the SDK's ``ContainerClient`` we use, so tests can fake it."""

    @property
    def url(self) -> str: ...

    def download_blob(self, blob: str) -> _Download: ...

    def upload_blob(
        self,
        name: str,
        data: bytes,
        *,
        overwrite: bool,
        content_settings: ContentSettings,
    ) -> object: ...


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

    def upload(self, key: str, path: Path) -> None:
        self.container.upload_blob(
            key,
            path.read_bytes(),
            overwrite=True,  # last week's snapshot is replaced, as on S3
            content_settings=ContentSettings(content_type="application/json"),
        )


def open_blob_snapshots(url: str) -> BlobSnapshots:
    """The snapshots in the container at ``url``, e.g.
    ``https://<account>.blob.core.windows.net/data``."""
    from azure.identity import DefaultAzureCredential  # slow to import: only here
    from azure.storage.blob import ContainerClient

    return BlobSnapshots(
        ContainerClient.from_container_url(url, credential=DefaultAzureCredential())
    )

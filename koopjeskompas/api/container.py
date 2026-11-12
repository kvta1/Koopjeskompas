"""Container entry point: the same FastAPI app, served by uvicorn, for Azure Container Apps.

A container is an ordinary server, unlike a Lambda: uvicorn listens on a port and
calls the app, as ``koopjeskompas serve`` does on the laptop. So there's no adapter
like Mangum; the ``Dockerfile`` starts uvicorn with ``create_container_app``, which
builds the app once when the container starts.

Configured by environment variables, so one image runs anywhere:

- ``DEALS_CONTAINER_URL``: the Blob Storage container holding the snapshots, e.g.
  ``https://<account>.blob.core.windows.net/data``. Each chain's ``deals/<key>.json``
  is copied to local disk at startup. With no snapshot at all the app doesn't start,
  so a broken setup shows up as a failing container rather than as empty rankings.
  A new upload reaches new containers, not running ones: restart the app after a
  ``publish-deals``, or wait until it has scaled to zero and back.
- ``DATA_DIR``: without ``DEALS_CONTAINER_URL``, the deals are read from this
  directory instead (default ``/data``), e.g. the laptop's ``data/`` mounted with
  ``docker run -v``.
- ``CORS_ORIGINS``: comma-separated origins of web pages on another domain that may
  call the API, e.g. ``https://<name>.azurestaticapps.net``. Empty: none.

No keys or passwords: ``DefaultAzureCredential`` finds an identity by itself. In Azure
that's the app's managed identity, which only needs the "Storage Blob Data Reader"
role on the container; on the laptop it's your ``az login``.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from azure.core.exceptions import ResourceNotFoundError
from fastapi import FastAPI

from koopjeskompas.api.app import create_app
from koopjeskompas.api.snapshots import download_snapshots

DOWNLOAD_DIR = Path("/tmp/koopjeskompas")
DEFAULT_DATA_DIR = Path("/data")


class _Download(Protocol):
    def readall(self) -> bytes: ...


class BlobContainer(Protocol):
    """The part of the SDK's ``ContainerClient`` we use, so tests can fake it."""

    @property
    def url(self) -> str: ...

    def download_blob(self, blob: str) -> _Download: ...


@dataclass(frozen=True)
class BlobSnapshots:
    """The snapshots in a Blob Storage container: the Azure adapter for
    ``SnapshotStore`` (``lambda_handler.S3Snapshots`` is the AWS one)."""

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


def build_app(
    environ: Mapping[str, str], open_container: Callable[[str], BlobContainer]
) -> FastAPI:
    """The app as ``environ`` configures it; ``open_container`` connects to Blob
    Storage (passed in, so tests need no Azure)."""
    origins = [o.strip() for o in environ.get("CORS_ORIGINS", "").split(",")]
    origins = [o for o in origins if o]
    if url := environ.get("DEALS_CONTAINER_URL"):
        download_snapshots(BlobSnapshots(open_container(url)), DOWNLOAD_DIR)
        data_dir = DOWNLOAD_DIR
    else:
        data_dir = Path(environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return create_app(data_dir=data_dir, cors_origins=origins)


def _open_container(url: str) -> BlobContainer:
    # Imported here: only a container that downloads needs the identity libraries.
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    return ContainerClient.from_container_url(url, credential=DefaultAzureCredential())


def create_container_app() -> FastAPI:
    """What uvicorn calls (``--factory``) once, when the container starts."""
    return build_app(os.environ, _open_container)

"""Container entry point: the same FastAPI app, served by uvicorn, on any container host.

A container is an ordinary server, unlike a Lambda: uvicorn listens on a port and
calls the app, as ``koopjeskompas serve`` does on the laptop. So there's no adapter
like Mangum; the ``Dockerfile`` starts uvicorn with ``create_container_app``, which
builds the app once when the container starts.

One image runs anywhere; environment variables say where the deals are:

- ``DEALS_BUCKET``: an S3 bucket, for a container on AWS (ECS, EC2), using the
  task's or instance's role.
- ``DEALS_CONTAINER_URL``: a Blob Storage container, for Azure Container Apps, e.g.
  ``https://<account>.blob.core.windows.net/data``, using its managed identity.
- Neither: the deals are read from ``DATA_DIR`` (default ``/data``), e.g. the laptop's
  ``data/`` mounted with ``docker run -v``.

From storage, each chain's ``deals/<key>.json`` is copied to local disk at startup.
With no snapshot at all the app doesn't start, so a broken setup shows up as a failing
container rather than as empty rankings. A new upload reaches new containers, not
running ones: restart the app after a ``publish-deals``, or wait until it has scaled
to zero and back.

``CORS_ORIGINS``: comma-separated origins of web pages on another domain that may call
the API, e.g. ``https://<name>.azurestaticapps.net``. Empty: none.
"""

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from fastapi import FastAPI

from koopjeskompas.api.app import create_app
from koopjeskompas.cloud.snapshots import SnapshotStore, download_snapshots

DOWNLOAD_DIR = Path("/tmp/koopjeskompas")
DEFAULT_DATA_DIR = Path("/data")


def _s3(bucket: str) -> SnapshotStore:
    # Each cloud's code is imported only when its setting is used: an Azure container
    # never loads boto3, an AWS one never the Azure SDK.
    from koopjeskompas.cloud.aws.s3 import open_s3_snapshots

    return open_s3_snapshots(bucket)


def _blob(url: str) -> SnapshotStore:
    from koopjeskompas.cloud.azure.blob import open_blob_snapshots

    return open_blob_snapshots(url)


# Which setting names which storage, and how to open it.
STORAGE: Mapping[str, Callable[[str], SnapshotStore]] = {
    "DEALS_BUCKET": _s3,
    "DEALS_CONTAINER_URL": _blob,
}


class ConfigurationError(ValueError):
    """The environment variables contradict each other."""


def build_app(
    environ: Mapping[str, str],
    storage: Mapping[str, Callable[[str], SnapshotStore]] = STORAGE,
) -> FastAPI:
    """The app as ``environ`` configures it. ``storage`` is passed in so tests can
    swap the clouds for fakes."""
    origins = [o.strip() for o in environ.get("CORS_ORIGINS", "").split(",")]
    origins = [o for o in origins if o]

    named = [setting for setting in storage if environ.get(setting)]
    if len(named) > 1:
        raise ConfigurationError(f"set one of {' and '.join(named)}, not both")
    if named:
        (setting,) = named
        download_snapshots(storage[setting](environ[setting]), DOWNLOAD_DIR)
        data_dir = DOWNLOAD_DIR
    else:
        data_dir = Path(environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return create_app(data_dir=data_dir, cors_origins=origins)


def create_container_app() -> FastAPI:
    """What uvicorn calls (``--factory``) once, when the container starts."""
    return build_app(os.environ)

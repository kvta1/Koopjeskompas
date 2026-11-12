"""The Blob Storage adapter, with a fake container."""

from pathlib import Path

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from koopjeskompas.cloud.azure.blob import BlobSnapshots, open_blob_snapshots

CONTAINER_URL = "https://koopjes.blob.core.windows.net/data"


class FakeDownload:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def readall(self) -> bytes:
        return self.data


class FakeContainer:
    """Serves blobs from memory, like the SDK's ``ContainerClient``."""

    def __init__(self, blobs: dict[str, bytes], url: str = CONTAINER_URL) -> None:
        self.blobs = blobs
        self.url = url

    def download_blob(self, blob: str) -> FakeDownload:
        if blob not in self.blobs:
            raise ResourceNotFoundError("The specified blob does not exist.")
        return FakeDownload(self.blobs[blob])


def test_a_blob_is_copied_to_disk(tmp_path: Path) -> None:
    store = BlobSnapshots(FakeContainer({"deals/ah.json": b"[]"}))
    assert store.download("deals/ah.json", tmp_path / "ah.json")
    assert (tmp_path / "ah.json").read_bytes() == b"[]"
    assert store.location == CONTAINER_URL


def test_a_missing_blob_is_missing(tmp_path: Path) -> None:
    store = BlobSnapshots(FakeContainer({}))
    assert not store.download("deals/ah.json", tmp_path / "x")


def test_no_permission_is_an_error_not_a_missing_blob(tmp_path: Path) -> None:
    class Forbidden(FakeContainer):
        def download_blob(self, blob: str) -> FakeDownload:
            raise HttpResponseError("AuthorizationPermissionMismatch")

    with pytest.raises(HttpResponseError):
        BlobSnapshots(Forbidden({})).download("deals/ah.json", tmp_path / "x")


def test_opened_by_url_without_contacting_azure() -> None:
    # The SDK connects on the first download, not here; no network in this test.
    assert open_blob_snapshots(CONTAINER_URL).location == CONTAINER_URL

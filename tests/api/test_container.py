"""The container entry point, configured as Azure would, with Blob Storage faked."""

from datetime import date
from pathlib import Path

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from fastapi.testclient import TestClient

from koopjeskompas.api import container
from koopjeskompas.api.container import BlobSnapshots, build_app
from koopjeskompas.api.snapshots import NoSnapshotsError
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.cache import deals_path, save_deals

CONTAINER_URL = "https://koopjes.blob.core.windows.net/data"
PAGE = "https://example.azurestaticapps.net"
LEIDEN_CENTRAAL = {"lat": 52.1664, "lon": 4.4817}


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


@pytest.fixture
def snapshot(tmp_path: Path) -> bytes:
    deal = Deal(
        chain="AH",
        product_name="AH Hummus naturel",
        mechanic_string="25% korting",
        valid_from=date(2026, 11, 2),
        valid_to=date(2026, 11, 8),
    )
    path = tmp_path / "snapshot.json"
    save_deals(path, [deal])
    return path.read_bytes()


@pytest.fixture(autouse=True)
def download_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "downloaded"
    monkeypatch.setattr(container, "DOWNLOAD_DIR", directory)
    return directory


# --- Blob Storage -------------------------------------------------------------


def test_a_blob_is_copied_to_disk(snapshot: bytes, tmp_path: Path) -> None:
    store = BlobSnapshots(FakeContainer({"deals/ah.json": snapshot}))
    assert store.download("deals/ah.json", tmp_path / "ah.json")
    assert (tmp_path / "ah.json").read_bytes() == snapshot
    assert store.location == CONTAINER_URL


def test_a_missing_blob_is_missing(tmp_path: Path) -> None:
    assert not BlobSnapshots(FakeContainer({})).download(
        "deals/ah.json", tmp_path / "x"
    )


def test_no_permission_is_an_error_not_a_missing_blob(tmp_path: Path) -> None:
    class Forbidden(FakeContainer):
        def download_blob(self, blob: str) -> FakeDownload:
            raise HttpResponseError("AuthorizationPermissionMismatch")

    with pytest.raises(HttpResponseError):
        BlobSnapshots(Forbidden({})).download("deals/ah.json", tmp_path / "x")


# --- configuration ------------------------------------------------------------


def test_snapshots_come_from_the_blob_container(
    snapshot: bytes, download_dir: Path
) -> None:
    opened: list[str] = []

    def open_container(url: str) -> FakeContainer:
        opened.append(url)
        return FakeContainer({"deals/ah.json": snapshot})

    app = build_app({"DEALS_CONTAINER_URL": CONTAINER_URL}, open_container)

    assert opened == [CONTAINER_URL]
    assert deals_path(download_dir, "AH").read_bytes() == snapshot
    response = TestClient(app).post("/api/rank", json={"location": LEIDEN_CENTRAAL})
    assert response.status_code == 200


def test_an_empty_container_stops_the_app_from_starting() -> None:
    with pytest.raises(NoSnapshotsError):
        build_app({"DEALS_CONTAINER_URL": CONTAINER_URL}, lambda url: FakeContainer({}))


def test_without_a_container_url_a_mounted_directory_is_read(
    snapshot: bytes, tmp_path: Path
) -> None:
    deals_path(tmp_path / "mounted", "AH").parent.mkdir(parents=True)
    deals_path(tmp_path / "mounted", "AH").write_bytes(snapshot)

    def no_azure(url: str) -> FakeContainer:
        raise AssertionError("Blob Storage shouldn't be used")

    app = build_app({"DATA_DIR": str(tmp_path / "mounted")}, no_azure)
    response = TestClient(app).post("/api/rank", json={"location": LEIDEN_CENTRAAL})
    assert response.status_code == 200


# --- CORS -------------------------------------------------------------------


def client_with_cors(origins: str, data_dir: Path) -> TestClient:
    environ = {"DATA_DIR": str(data_dir), "CORS_ORIGINS": origins}
    return TestClient(build_app(environ, lambda url: FakeContainer({})))


def preflight(client: TestClient, origin: str) -> dict[str, str]:
    """What a browser asks before a page on ``origin`` POSTs JSON to the API."""
    response = client.options(
        "/api/rank",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-amz-content-sha256",
        },
    )
    return dict(response.headers)


def test_the_allowed_page_may_call_the_api(tmp_path: Path) -> None:
    client = client_with_cors(f" {PAGE} , https://other.example ", tmp_path)

    headers = preflight(client, PAGE)
    assert headers["access-control-allow-origin"] == PAGE
    assert "POST" in headers["access-control-allow-methods"]
    assert "x-amz-content-sha256" in headers["access-control-allow-headers"]

    health = client.get("/api/health", headers={"Origin": PAGE})
    assert health.headers["access-control-allow-origin"] == PAGE


def test_another_page_may_not(tmp_path: Path) -> None:
    client = client_with_cors(PAGE, tmp_path)
    assert "access-control-allow-origin" not in preflight(
        client, "https://evil.example"
    )


def test_no_cors_unless_configured(tmp_path: Path) -> None:
    client = client_with_cors("", tmp_path)
    health = client.get("/api/health", headers={"Origin": PAGE})
    assert "access-control-allow-origin" not in health.headers

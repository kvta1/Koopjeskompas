"""The container entry point, configured by environment variables as a host would.

Storage is faked: each test passes its own ``storage`` mapping, so no cloud is
involved. The real adapters have their own tests in ``tests/cloud/``.
"""

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from koopjeskompas.api import container
from koopjeskompas.api.container import ConfigurationError, build_app
from koopjeskompas.cloud.aws.s3 import S3Snapshots
from koopjeskompas.cloud.azure.blob import BlobSnapshots
from koopjeskompas.cloud.snapshots import NoSnapshotsError, SnapshotStore
from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.cache import deals_path, save_deals

PAGE = "https://example.azurestaticapps.net"
LEIDEN_CENTRAAL = {"lat": 52.1664, "lon": 4.4817}


class FakeStore:
    """A ``SnapshotStore`` holding snapshots in memory, by key."""

    def __init__(self, location: str, snapshots: dict[str, bytes]) -> None:
        self.location = location
        self.snapshots = snapshots

    def download(self, key: str, path: Path) -> bool:
        if key not in self.snapshots:
            return False
        path.write_bytes(self.snapshots[key])
        return True


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


def fake_storage(
    snapshots: dict[str, bytes], opened: list[str] | None = None
) -> Mapping[str, Callable[[str], SnapshotStore]]:
    """Both settings, each opening a fake store and noting what it was asked for."""

    def opener(setting: str) -> Callable[[str], SnapshotStore]:
        def open_store(value: str) -> SnapshotStore:
            if opened is not None:
                opened.append(f"{setting}={value}")
            return FakeStore(value, snapshots)

        return open_store

    return {setting: opener(setting) for setting in container.STORAGE}


# --- where the deals come from ----------------------------------------------


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("DEALS_BUCKET", "koopjeskompas-data"),  # a container on AWS
        ("DEALS_CONTAINER_URL", "https://k.blob.core.windows.net/data"),  # Azure
    ],
)
def test_snapshots_come_from_the_named_storage(
    setting: str, value: str, snapshot: bytes, download_dir: Path
) -> None:
    opened: list[str] = []
    storage = fake_storage({"deals/ah.json": snapshot}, opened)

    app = build_app({setting: value}, storage)

    assert opened == [f"{setting}={value}"]
    assert deals_path(download_dir, "AH").read_bytes() == snapshot
    response = TestClient(app).post("/api/rank", json={"location": LEIDEN_CENTRAAL})
    assert response.status_code == 200


def test_two_storages_at_once_is_a_mistake() -> None:
    environ = {"DEALS_BUCKET": "b", "DEALS_CONTAINER_URL": "https://k/data"}
    with pytest.raises(ConfigurationError, match="not both"):
        build_app(environ, fake_storage({}))


def test_empty_storage_stops_the_app_from_starting() -> None:
    with pytest.raises(NoSnapshotsError):
        build_app({"DEALS_BUCKET": "empty"}, fake_storage({}))


def test_without_storage_a_mounted_directory_is_read(
    snapshot: bytes, tmp_path: Path
) -> None:
    mounted = tmp_path / "mounted"
    deals_path(mounted, "AH").parent.mkdir(parents=True)
    deals_path(mounted, "AH").write_bytes(snapshot)
    opened: list[str] = []

    app = build_app({"DATA_DIR": str(mounted)}, fake_storage({}, opened))

    assert opened == []
    response = TestClient(app).post("/api/rank", json={"location": LEIDEN_CENTRAAL})
    assert response.status_code == 200


def test_each_setting_opens_its_clouds_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    monkeypatch.setattr(boto3, "client", lambda service, **_: object())
    s3 = container.STORAGE["DEALS_BUCKET"]("koopjeskompas-data")
    blob = container.STORAGE["DEALS_CONTAINER_URL"]("https://k.blob.core.windows.net/d")
    assert isinstance(s3, S3Snapshots)
    assert isinstance(blob, BlobSnapshots)


# --- CORS -------------------------------------------------------------------


def client_with_cors(origins: str, data_dir: Path) -> TestClient:
    environ = {"DATA_DIR": str(data_dir), "CORS_ORIGINS": origins}
    return TestClient(build_app(environ, fake_storage({})))


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

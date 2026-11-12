"""The loop shared by every cloud: each chain's snapshot, from a fake store."""

from pathlib import Path

import pytest

from koopjeskompas.cloud.snapshots import NoSnapshotsError, download_snapshots


class FakeStore:
    """A ``SnapshotStore`` holding snapshots as text, by key."""

    location = "fake://bucket"

    def __init__(self, snapshots: dict[str, str]) -> None:
        self.snapshots = snapshots
        self.asked: list[str] = []

    def download(self, key: str, path: Path) -> bool:
        self.asked.append(key)
        if key not in self.snapshots:
            return False
        path.write_text(self.snapshots[key])
        return True


def test_each_chains_snapshot_lands_where_the_app_reads_it(tmp_path: Path) -> None:
    store = FakeStore({"deals/ah.json": "[]"})
    # Only AH's snapshot is there: Jumbo and Lidl are skipped, not errors.
    assert download_snapshots(store, tmp_path) == ["AH"]
    assert (tmp_path / "deals" / "ah.json").read_text() == "[]"
    assert store.asked == ["deals/ah.json", "deals/jumbo.json", "deals/lidl.json"]


def test_no_snapshot_at_all_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(NoSnapshotsError, match="fake://bucket/deals/"):
        download_snapshots(FakeStore({}), tmp_path)

"""The S3 adapter, with a fake S3."""

from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError

from koopjeskompas.cloud.aws.s3 import S3Snapshots, open_s3_snapshots
from tests.cloud.aws.fakes import BUCKET, KEY, FakeS3, bucket_with_ah


def test_a_snapshot_in_the_bucket_is_downloaded(tmp_path: Path) -> None:
    s3 = bucket_with_ah(tmp_path)
    path = tmp_path / "ah.json"
    assert S3Snapshots(s3, BUCKET).download(KEY, path)
    assert path.exists()
    assert s3.downloads == [(BUCKET, KEY)]


def test_a_403_means_missing_for_a_role_that_cant_list(tmp_path: Path) -> None:
    s3 = bucket_with_ah(tmp_path)
    assert not S3Snapshots(s3, BUCKET).download("deals/jumbo.json", tmp_path / "j")


def test_other_s3_errors_are_not_mistaken_for_a_missing_snapshot(
    tmp_path: Path,
) -> None:
    class Throttled(FakeS3):
        def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
            error = {"Error": {"Code": "SlowDown", "Message": "Slow down"}}
            raise ClientError(error, "GetObject")  # type: ignore[arg-type]

    with pytest.raises(ClientError):
        S3Snapshots(Throttled({}), BUCKET).download(KEY, tmp_path / "ah.json")


def test_a_snapshot_is_uploaded_as_json(tmp_path: Path) -> None:
    s3 = FakeS3()
    S3Snapshots(s3, BUCKET).upload(KEY, tmp_path / "ah.json")
    assert s3.uploads == [
        {
            "file": "ah.json",
            "bucket": BUCKET,
            "key": KEY,
            "extra": {"ContentType": "application/json"},
        }
    ]


def test_opened_by_bucket_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s3 = bucket_with_ah(tmp_path)
    monkeypatch.setattr(boto3, "client", lambda service, **_: s3)
    store = open_s3_snapshots(BUCKET)
    assert store == S3Snapshots(s3, BUCKET)
    assert store.location == f"s3://{BUCKET}"

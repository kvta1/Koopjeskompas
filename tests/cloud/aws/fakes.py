"""A fake S3, shared by the S3 adapter's tests and the Lambda's."""

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from koopjeskompas.domain.models import Deal
from koopjeskompas.ingestion.cache import save_deals

BUCKET = "koopjeskompas-data"
KEY = "deals/ah.json"


class FakeS3:
    """Serves objects from local files, like ``download_file`` serves them from S3,
    and records what ``upload_file`` is asked to store."""

    def __init__(self, objects: dict[tuple[str, str], Path] | None = None) -> None:
        self.objects = objects or {}
        self.downloads: list[tuple[str, str]] = []
        self.uploads: list[dict[str, Any]] = []

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self.downloads.append((Bucket, Key))
        if (Bucket, Key) not in self.objects:
            # What S3 answers a role that may read objects but not list the bucket.
            error = {"Error": {"Code": "403", "Message": "Forbidden"}}
            raise ClientError(error, "HeadObject")  # type: ignore[arg-type]
        shutil.copyfile(self.objects[Bucket, Key], Filename)

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None:
        self.uploads.append(
            {
                "file": Path(Filename).name,
                "bucket": Bucket,
                "key": Key,
                "extra": ExtraArgs,
            }
        )


def bucket_with_ah(tmp_path: Path) -> FakeS3:
    """A bucket holding only AH's snapshot, with one deal."""
    snapshot = tmp_path / "snapshot.json"
    deal = Deal(
        chain="AH",
        product_name="AH Hummus naturel",
        mechanic_string="25% korting",
        valid_from=date(2026, 11, 2),
        valid_to=date(2026, 11, 8),
    )
    save_deals(snapshot, [deal])
    return FakeS3({(BUCKET, KEY): snapshot})

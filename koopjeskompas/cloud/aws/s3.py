"""The snapshots in an S3 bucket: the AWS adapter for ``SnapshotStore`` and
``SnapshotTarget``.

Read by the Lambda, and by a container on AWS (ECS, EC2) through ``DEALS_BUCKET``;
written by ``publish-deals``. Credentials come from the environment's role (the
Lambda's, an EC2 instance's or an ECS task's) or your ``aws login``, never from keys in
the code.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from botocore.exceptions import ClientError

# What S3 answers for a key that isn't there: 404, or 403 for a role that may read
# objects but not list the bucket, as the Lambda's (least privilege).
_MISSING = {"404", "NoSuchKey", "403", "AccessDenied"}


class S3Client(Protocol):
    """The S3 calls we make; boto3's S3 client fits it, and so does a test fake."""

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class S3Snapshots:
    s3: S3Client
    bucket: str

    @property
    def location(self) -> str:
        return f"s3://{self.bucket}"

    def download(self, key: str, path: Path) -> bool:
        try:
            self.s3.download_file(Bucket=self.bucket, Key=key, Filename=str(path))
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in _MISSING:
                return False
            raise
        return True

    def upload(self, key: str, path: Path) -> None:
        self.s3.upload_file(
            Filename=str(path),
            Bucket=self.bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/json"},
        )


def open_s3_snapshots(bucket: str, region: str | None = None) -> S3Snapshots:
    """The snapshots in ``bucket``, through boto3 and the environment's credentials.
    ``region``: None for the environment's own (the Lambda's), or the laptop's target."""
    import boto3  # here: only code that reaches S3 needs it loaded

    return S3Snapshots(boto3.client("s3", region_name=region), bucket)

"""Publishing the snapshots, with fakes for S3, CloudFormation and Blob Storage: no
cloud involved."""

import json
from pathlib import Path
from typing import Any

import boto3
import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from botocore.exceptions import (
    ClientError,
    MissingDependencyException,
    NoCredentialsError,
)

from koopjeskompas.cli import main
from koopjeskompas.cloud.aws.s3 import S3Snapshots
from koopjeskompas.cloud.azure import blob
from koopjeskompas.cloud.azure.blob import BlobSnapshots
from koopjeskompas.publish import (
    DATA_BUCKET_OUTPUT,
    PublishError,
    find_data_bucket,
    publish_deals,
    snapshots,
)
from tests.cloud.aws.fakes import FakeS3
from tests.cloud.azure.test_blob import CONTAINER_URL, FakeContainer

BUCKET = "koopjeskompas-databucket-abc123"


class FakeCloudFormation:
    """Answers describe_stacks the way CloudFormation does, for one stack."""

    def __init__(self, outputs: list[dict[str, str]]) -> None:
        self.outputs = outputs

    def describe_stacks(self, *, StackName: str) -> dict[str, Any]:
        if StackName != "Koopjeskompas":
            raise ClientError(
                {"Error": {"Code": "ValidationError", "Message": "does not exist"}},
                "DescribeStacks",
            )
        return {"Stacks": [{"StackName": StackName, "Outputs": self.outputs}]}


DEPLOYED = FakeCloudFormation(
    [
        {"OutputKey": "SiteUrl", "OutputValue": "https://d123.cloudfront.net"},
        {"OutputKey": DATA_BUCKET_OUTPUT, "OutputValue": BUCKET},
    ]
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    deals = tmp_path / "deals"
    deals.mkdir()
    for chain in ["ah", "jumbo"]:
        (deals / f"{chain}.json").write_text(json.dumps([]))
    return tmp_path


def test_the_bucket_is_read_from_the_stack_outputs() -> None:
    assert find_data_bucket(DEPLOYED, "Koopjeskompas") == BUCKET


def test_a_stack_without_the_output_says_to_deploy() -> None:
    with pytest.raises(PublishError, match="deploy"):
        find_data_bucket(FakeCloudFormation([]), "Koopjeskompas")


def test_every_chain_snapshot_is_uploaded_under_deals(data_dir: Path) -> None:
    s3 = FakeS3()
    keys = publish_deals(S3Snapshots(s3, BUCKET), snapshots(data_dir / "deals"))

    assert keys == ["deals/ah.json", "deals/jumbo.json"]
    assert s3.uploads[0] == {
        "file": "ah.json",
        "bucket": BUCKET,
        "key": "deals/ah.json",
        "extra": {"ContentType": "application/json"},
    }


def test_without_snapshots_it_says_to_fetch_first(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="fetch-deals"):
        snapshots(tmp_path / "deals")


@pytest.fixture
def fake_aws(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    s3 = FakeS3()
    clients: dict[str, Any] = {"s3": s3, "cloudformation": DEPLOYED}
    monkeypatch.setattr(boto3, "client", lambda service, **_: clients[service])
    return s3


def test_publish_deals_command(
    data_dir: Path, fake_aws: FakeS3, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(data_dir), "publish-deals"]) == 0
    assert [u["bucket"] for u in fake_aws.uploads] == [BUCKET, BUCKET]
    assert f"s3://{BUCKET}/deals/ah.json" in capsys.readouterr().out


def test_publish_deals_to_a_named_bucket(data_dir: Path, fake_aws: FakeS3) -> None:
    main(["--data-dir", str(data_dir), "publish-deals", "--bucket", "other"])
    assert {u["bucket"] for u in fake_aws.uploads} == {"other"}


def test_a_missing_stack_is_reported_without_blaming_the_login(
    data_dir: Path, fake_aws: FakeS3, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(data_dir), "publish-deals", "--stack", "Nope"]) == 1
    err = capsys.readouterr().err
    assert "does not exist" in err
    assert "aws login" not in err
    assert fake_aws.uploads == []


@pytest.mark.parametrize(
    ("error", "says_log_in"),
    [
        (NoCredentialsError(), True),
        (
            ClientError(
                {"Error": {"Code": "ExpiredToken", "Message": "expired"}}, "PutObject"
            ),
            True,
        ),
        # What happened for real: boto3 without botocore[crt] can't read the
        # credentials of `aws login`. Logging in again doesn't help with that.
        (MissingDependencyException(msg='pip install "botocore[crt]"'), False),
    ],
)
def test_only_credential_errors_suggest_logging_in(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    says_log_in: bool,
) -> None:
    def refuse(service: str, **_: Any) -> Any:
        raise error

    monkeypatch.setattr(boto3, "client", refuse)
    assert main(["--data-dir", str(data_dir), "publish-deals", "--bucket", "b"]) == 1
    assert ("aws login" in capsys.readouterr().err) is says_log_in


# --- Azure ------------------------------------------------------------------


class OpenedContainer(FakeContainer):
    """A fake container that also notes the URL it was opened with."""

    opened_with: str | None = None


@pytest.fixture
def fake_azure(monkeypatch: pytest.MonkeyPatch) -> OpenedContainer:
    container = OpenedContainer({})

    def open_fake(url: str) -> BlobSnapshots:
        container.opened_with = url
        return BlobSnapshots(container)

    monkeypatch.setattr(blob, "open_blob_snapshots", open_fake)
    return container


def test_publish_deals_to_azure(
    data_dir: Path, fake_azure: OpenedContainer, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--data-dir", str(data_dir), "publish-deals", "--cloud", "azure"]
    assert main([*argv, "--container-url", CONTAINER_URL]) == 0

    assert fake_azure.opened_with == CONTAINER_URL
    assert sorted(fake_azure.blobs) == ["deals/ah.json", "deals/jumbo.json"]
    assert fake_azure.content_types["deals/ah.json"] == "application/json"
    assert f"{CONTAINER_URL}/deals/ah.json" in capsys.readouterr().out


def test_the_container_url_can_come_from_the_environment(
    data_dir: Path, fake_azure: OpenedContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same variable the API reads, so one setting serves both.
    monkeypatch.setenv("DEALS_CONTAINER_URL", CONTAINER_URL)
    assert main(["--data-dir", str(data_dir), "publish-deals", "--cloud", "azure"]) == 0
    assert fake_azure.opened_with == CONTAINER_URL


def test_azure_without_a_container_says_where_to_find_it(
    data_dir: Path,
    fake_azure: OpenedContainer,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DEALS_CONTAINER_URL", raising=False)
    assert main(["--data-dir", str(data_dir), "publish-deals", "--cloud", "azure"]) == 1
    assert "deals_container_url" in capsys.readouterr().err
    assert fake_azure.opened_with is None


def azure_error(error_type: type[HttpResponseError], status: int) -> HttpResponseError:
    """An error as the SDK raises it, with the HTTP status Azure answered."""
    error = error_type("refused")
    error.status_code = status
    return error


@pytest.mark.parametrize(
    ("error", "hint"),
    [
        # No identity found: DefaultAzureCredential raises this before any upload.
        (azure_error(ClientAuthenticationError, 401), "az login"),
        # Signed in, but without the role that may write blobs.
        (azure_error(HttpResponseError, 403), "Storage Blob Data Contributor"),
    ],
)
def test_azure_errors_say_what_to_do(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: HttpResponseError,
    hint: str,
) -> None:
    class Refusing(FakeContainer):
        def upload_blob(self, *args: Any, **kwargs: Any) -> object:
            raise error

    monkeypatch.setattr(
        blob, "open_blob_snapshots", lambda url: BlobSnapshots(Refusing({}))
    )
    argv = ["--data-dir", str(data_dir), "publish-deals", "--cloud", "azure"]
    assert main([*argv, "--container-url", CONTAINER_URL]) == 1
    assert hint in capsys.readouterr().err

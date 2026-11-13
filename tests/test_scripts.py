"""The weekly refresh script, run for real with fake ``uv``, ``aws``, ``az`` and
``terraform`` commands.

The fakes stand first on PATH: they record how they were called and fail when told
to, so the script's decisions are tested without fetching or publishing anything.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh-deals.sh"

FAKE = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$CALLS"
case "$(basename "$0") $*" in
  "aws sts"*) exit "${AWS_EXIT:-0}" ;;
  "az account"*) exit "${AZ_EXIT:-0}" ;;
  terraform*)
    [[ "${TF_EXIT:-0}" == 0 ]] && echo "https://k.blob.core.windows.net/data"
    exit "${TF_EXIT:-0}" ;;
  *fetch-deals*) exit "${FETCH_EXIT:-0}" ;;
  *publish-deals*) exit "${PUBLISH_EXIT:-0}" ;;
esac
"""


def run(tmp_path: Path, *args: str, **exits: str) -> tuple[int, list[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ["uv", "aws", "az", "terraform"]:
        fake = bin_dir / name
        fake.write_text(FAKE)
        fake.chmod(0o755)
    calls = tmp_path / "calls"
    env = (
        os.environ
        | exits
        | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "CALLS": str(calls)}
    )
    done = subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True
    )
    called = calls.read_text().splitlines() if calls.exists() else []
    return done.returncode, called, done.stderr


def test_fetches_then_publishes(tmp_path: Path) -> None:
    code, called, _ = run(tmp_path)
    assert code == 0
    assert called == [
        "aws sts get-caller-identity",
        "uv run koopjeskompas fetch-deals",
        "uv run koopjeskompas publish-deals",
    ]


def test_not_signed_in_asks_no_supermarket(tmp_path: Path) -> None:
    code, called, err = run(tmp_path, AWS_EXIT="255")
    assert code == 1
    assert called == ["aws sts get-caller-identity"]  # no fetch-deals
    assert "aws login" in err


def test_a_failing_chain_still_publishes_the_others(tmp_path: Path) -> None:
    # fetch-deals exits 1 when any chain failed, having saved the ones that worked.
    code, called, err = run(tmp_path, FETCH_EXIT="1")
    assert code == 1
    assert called[-1] == "uv run koopjeskompas publish-deals"
    assert "Some chains failed" in err


def test_a_failed_publish_is_reported(tmp_path: Path) -> None:
    code, _, _ = run(tmp_path, PUBLISH_EXIT="1")
    assert code == 1


def test_local_only_fetches(tmp_path: Path) -> None:
    code, called, _ = run(tmp_path, "--local")
    assert code == 0
    assert called == ["uv run koopjeskompas fetch-deals"]  # no AWS at all


AZURE_URL = "https://k.blob.core.windows.net/data"


def test_azure_publishes_to_both_clouds(tmp_path: Path) -> None:
    code, called, _ = run(tmp_path, "--azure")
    assert code == 0
    assert called == [
        "aws sts get-caller-identity",
        "az account show",
        "terraform -chdir=infra-azure output -raw deals_container_url",
        "uv run koopjeskompas fetch-deals",
        "uv run koopjeskompas publish-deals",
        f"uv run koopjeskompas publish-deals --cloud azure --container-url {AZURE_URL}",
    ]


def test_not_signed_in_to_azure_asks_no_supermarket(tmp_path: Path) -> None:
    code, called, err = run(tmp_path, "--azure", AZ_EXIT="1")
    assert code == 1
    assert "uv run koopjeskompas fetch-deals" not in called
    assert "az login" in err


def test_azure_not_deployed_asks_no_supermarket(tmp_path: Path) -> None:
    code, called, err = run(tmp_path, "--azure", TF_EXIT="1")
    assert code == 1
    assert "uv run koopjeskompas fetch-deals" not in called
    assert "deploy-azure.sh" in err


def test_one_cloud_failing_still_publishes_to_the_other(tmp_path: Path) -> None:
    code, called, err = run(tmp_path, "--azure", PUBLISH_EXIT="1")
    assert code == 1
    assert called[-1].startswith("uv run koopjeskompas publish-deals --cloud azure")
    assert "Publishing failed" in err


def test_local_and_azure_contradict(tmp_path: Path) -> None:
    code, called, _ = run(tmp_path, "--local", "--azure")
    assert code == 2
    assert called == []


@pytest.mark.parametrize("script", sorted((SCRIPT.parent).glob("*.sh")))
def test_every_script_is_valid_bash(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0

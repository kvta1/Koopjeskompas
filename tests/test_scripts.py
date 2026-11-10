"""The weekly refresh script, run for real with fake ``uv`` and ``aws`` commands.

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
  *fetch-deals*) exit "${FETCH_EXIT:-0}" ;;
  *publish-deals*) exit "${PUBLISH_EXIT:-0}" ;;
esac
"""


def run(tmp_path: Path, *args: str, **exits: str) -> tuple[int, list[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ["uv", "aws"]:
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


@pytest.mark.parametrize("script", sorted((SCRIPT.parent).glob("*.sh")))
def test_every_script_is_valid_bash(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0

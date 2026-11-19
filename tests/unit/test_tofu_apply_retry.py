"""`tofu apply` is retried on a network error, and only on one (#796).

The script runs for real against a stand-in `tofu` on PATH that fails a set
number of times with a chosen message, counting its calls in a file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "tofu-apply-retry.sh"

_FAKE_TOFU = """#!/usr/bin/env bash
count_file="$(dirname "$0")/calls"
calls=$(( $(cat "$count_file" 2>/dev/null || echo 0) + 1 ))
echo "$calls" > "$count_file"
echo "args: $*" > "$(dirname "$0")/args"
if [ "$calls" -le {fails} ]; then
  echo "Error: {message}"
  exit 1
fi
echo "Apply complete! Resources: 1 added, 0 changed, 0 destroyed."
"""

NETWORK = (
    "[FATAL] error checking bucket existence: Get "
    '"https://fsn1.your-objectstorage.com/b/?location=": '
    "net/http: timeout awaiting response headers"
)
CONFIG = 'Reference to undeclared input variable "domain"'


def _run(
    tmp_path: Path, *, fails: int, message: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tofu = bin_dir / "tofu"
    tofu.write_text(_FAKE_TOFU.replace("{fails}", str(fails)).replace("{message}", message))
    tofu.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TOFU_APPLY_RETRY_DELAY_S": "0",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "-var-file=config.tfvars", "-auto-approve"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, bin_dir


def _calls(bin_dir: Path) -> int:
    return int((bin_dir / "calls").read_text())


def test_a_clean_apply_runs_once_and_passes_the_arguments(tmp_path: Path) -> None:
    result, bin_dir = _run(tmp_path, fails=0, message="")
    assert result.returncode == 0, result.stdout
    assert _calls(bin_dir) == 1
    assert (
        bin_dir / "args"
    ).read_text().strip() == "args: apply -var-file=config.tfvars -auto-approve"
    assert "Apply complete!" in result.stdout, "the output still reaches the log"


def test_a_network_error_is_retried_and_the_apply_succeeds(tmp_path: Path) -> None:
    result, bin_dir = _run(tmp_path, fails=2, message=NETWORK)
    assert result.returncode == 0, result.stdout
    assert _calls(bin_dir) == 3
    assert "attempt 1 of 3" in result.stdout
    assert "attempt 2 of 3" in result.stdout


def test_a_network_error_every_time_fails_after_three_attempts(tmp_path: Path) -> None:
    result, bin_dir = _run(tmp_path, fails=99, message=NETWORK)
    assert result.returncode == 1
    assert _calls(bin_dir) == 3
    assert "in all 3 attempts" in result.stdout


def test_a_configuration_error_fails_at_once(tmp_path: Path) -> None:
    result, bin_dir = _run(tmp_path, fails=99, message=CONFIG)
    assert result.returncode == 1
    assert _calls(bin_dir) == 1
    assert "not on a network error; not retrying" in result.stdout


@pytest.mark.parametrize(
    "message",
    [
        "dial tcp 1.2.3.4:443: i/o timeout",
        "read tcp: connection reset by peer",
        "unexpected EOF",
        "context deadline exceeded (Client.Timeout exceeded while awaiting headers)",
        "hcloud: 503 Service Unavailable",
        "api error: 502 Bad Gateway",
        "S3 operation failed; StatusCode: 504",
    ],
)
def test_these_count_as_network_errors(tmp_path: Path, message: str) -> None:
    result, bin_dir = _run(tmp_path, fails=1, message=message)
    assert result.returncode == 0, result.stdout
    assert _calls(bin_dir) == 2


@pytest.mark.parametrize(
    "message",
    [
        "server type cx43 is unavailable in location hel1 (resource_unavailable)",
        "403 Forbidden: Authentication error",
        "invalid input in field 'name'",
    ],
)
def test_these_do_not(tmp_path: Path, message: str) -> None:
    result, bin_dir = _run(tmp_path, fails=1, message=message)
    assert result.returncode == 1
    assert _calls(bin_dir) == 1


def test_both_lifecycle_workflows_apply_through_the_script() -> None:
    workflows = REPO_ROOT / ".github" / "workflows"
    for name in ("spin-up.yml", "setup-control-plane.yaml"):
        text = (workflows / name).read_text()
        assert "tofu-apply-retry.sh" in text, f"{name} applies without the retry"
        bare = [
            line.strip() for line in text.splitlines() if line.strip().startswith("tofu apply ")
        ]
        assert not bare, f"{name} still runs a bare apply: {bare}"


@pytest.mark.parametrize(
    "message",
    [
        "Failed to save state: timeout awaiting response headers",
        "Failed to persist state to backend; net/http: timeout awaiting response headers",
        "OpenTofu has saved the state to errored.tfstate (i/o timeout)",
    ],
)
def test_a_state_that_was_not_saved_is_never_retried(tmp_path: Path, message: str) -> None:
    """Even with a network error in the text: the next apply would act on stale state."""
    result, bin_dir = _run(tmp_path, fails=99, message=message)
    assert result.returncode == 1
    assert _calls(bin_dir) == 1
    assert "could not save its state" in result.stdout

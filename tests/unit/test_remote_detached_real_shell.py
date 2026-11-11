"""The detached runner's shell, executed for real.

tests/unit/test_remote_detached.py checks the Python side against a model of
the server. That model cannot tell whether the launcher, the job wrapper and
the poll are correct shell. These tests run them: a stand-in `ssh` on PATH
ignores the host and hands the command to `sh -c`, so everything the runner
sends is executed on this machine, with the job directory under a temp dir.

They need `setsid` and `sha256sum`, which the server and the CI runners have
and macOS does not; there they are skipped.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_deploy import _remote

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("setsid") or not shutil.which("sha256sum"),
    reason="needs Linux with setsid and sha256sum, as the server has",
)

FAKE_SSH = """#!/bin/sh
# ssh <host> <command>: run the command here, stdin passed through.
shift
exec sh -c "$1"
"""


@pytest.fixture
def local_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(FAKE_SSH)
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    root = tmp_path / "jobs"
    monkeypatch.setattr(_remote, "_DETACHED_ROOT", str(root))
    return root


def run(script: str, *, merge_stderr: bool = True) -> subprocess.CompletedProcess[str]:
    return _remote.ssh_run_script(
        script, detached=True, poll_interval_s=0.1, merge_stderr=merge_stderr
    )


def test_a_real_script_runs_and_its_output_and_status_come_back(local_server: Path) -> None:
    result = run('echo "→ one"\nsleep 0.5\necho "→ two"\n')
    assert result.returncode == 0
    assert result.stdout == "→ one\n→ two\n"


def test_the_job_directory_is_gone_afterwards(local_server: Path) -> None:
    run("echo done\n")
    assert list(local_server.glob("*")) == []


def test_a_failing_script_reports_its_own_exit_status(local_server: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run('echo "before"\nexit 7\n')
    assert caught.value.returncode == 7
    assert caught.value.output == "before\n"


def test_stderr_is_merged_by_default_and_separate_on_request(local_server: Path) -> None:
    merged = run("echo out\necho err >&2\n")
    assert merged.stdout == "out\nerr\n"
    separate = run("echo out\necho err >&2\n", merge_stderr=False)
    assert separate.stdout == "out\n"
    assert separate.stderr == "err\n"


def test_the_script_file_is_unlinked_while_the_script_runs(local_server: Path) -> None:
    # The script lists the job directories: its own file must not be there,
    # because it can carry secret values.
    result = run(f"ls -1 {local_server}/*/\n")
    assert "script" not in result.stdout.split()
    assert "out" in result.stdout.split()


def test_a_multi_line_script_with_quotes_and_dollars_arrives_intact(local_server: Path) -> None:
    script = (
        "X='a $b \"c\"'\nprintf '%s\\n' \"$X\"\nfor i in 1 2 3; do printf '%s' \"$i\"; done\necho\n"
    )
    assert run(script).stdout == 'a $b "c"\n123\n'


def test_a_job_killed_without_a_status_is_reported_not_passed(local_server: Path) -> None:
    # Kill the wrapper that would have written the status, then the script.
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run('echo "started"\nkill -9 "$PPID"\nkill -9 "$$"\n')
    assert "without leaving an exit status" in (caught.value.output or "")
    assert (caught.value.output or "").startswith("started\n")


def test_a_script_outlives_the_command_that_started_it(local_server: Path) -> None:
    # The launcher returns at once; the work happens after it has exited.
    result = run("sleep 1\necho late\n")
    assert result.stdout == "late\n"

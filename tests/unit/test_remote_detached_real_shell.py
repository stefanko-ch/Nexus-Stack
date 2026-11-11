"""The detached runner's shell, executed for real.

tests/unit/test_remote_detached.py checks the Python side against a model of
the server. That model cannot tell whether the launcher, the job wrapper and
the poll are correct shell. These tests run them: a stand-in `ssh` on PATH
ignores the host and hands the command to `sh -c`, so everything the runner
sends is executed on this machine, with the job directory under a temp dir.

They need `setsid`, which the server and the CI runners have and macOS does
not; there they are skipped.
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
    sys.platform != "linux" or not shutil.which("setsid"),
    reason="needs Linux with setsid, as the server has",
)

FAKE_SSH = """#!/bin/sh
# ssh <host> <command>: run the command here, stdin passed through.
shift
exec sh -c "$1"
"""

# The same stand-in, except that a launch is delivered twice at the same
# moment: what a retry racing a launch whose answer was lost looks like.
FAKE_SSH_RACING_LAUNCH = """#!/bin/sh
shift
case "$1" in
  *"nexus-detached launch"*)
    upload=$(mktemp)
    cat > "$upload"
    sh -c "$1" < "$upload" &
    first=$!
    sh -c "$1" < "$upload"
    second_status=$?
    wait "$first"
    first_status=$?
    rm -f "$upload"
    [ "$first_status" -eq 0 ] && [ "$second_status" -eq 0 ]
    ;;
  *) exec sh -c "$1" ;;
esac
"""

# A launch delivered a second time after the first one has returned.
FAKE_SSH_REPEATED_LAUNCH = """#!/bin/sh
shift
case "$1" in
  *"nexus-detached launch"*)
    upload=$(mktemp)
    cat > "$upload"
    sh -c "$1" < "$upload" || exit $?
    sh -c "$1" < "$upload"
    status=$?
    rm -f "$upload"
    exit "$status"
    ;;
  *) exec sh -c "$1" ;;
esac
"""

# The upload is cut short, and the command still sees a clean end of input:
# what a session that drops during the upload leaves on the server.
FAKE_SSH_TRUNCATED_UPLOAD = """#!/bin/sh
shift
case "$1" in
  *"nexus-detached launch"*) head -c 12 | sh -c "$1" ;;
  *) exec sh -c "$1" ;;
esac
"""


def _install_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    ssh = bin_dir / "ssh"
    ssh.write_text(body)
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    root = tmp_path / "jobs"
    monkeypatch.setattr(_remote, "_DETACHED_ROOT", str(root))
    return root


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


def test_two_launches_at_once_run_the_script_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _install_ssh(tmp_path, monkeypatch, FAKE_SSH_RACING_LAUNCH)
    counter = tmp_path / "ran"
    result = run(f'echo x >> {counter}\necho "ran"\n')
    assert result.stdout == "ran\n"
    assert counter.read_text() == "x\n", "the script ran exactly once"
    assert list(root.glob("*")) == [], "and neither attempt left a script file behind"


def test_a_second_launch_after_the_script_started_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A launch whose answer was lost is sent again once the job is running.
    root = _install_ssh(tmp_path, monkeypatch, FAKE_SSH_REPEATED_LAUNCH)
    counter = tmp_path / "ran"
    result = run(f'echo x >> {counter}\nsleep 1\necho "first"\n')
    assert result.stdout == "first\n"
    assert counter.read_text() == "x\n", "the script ran exactly once"
    assert list(root.glob("*")) == []


def test_a_lock_without_a_pid_stops_reading_as_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A job that died between taking the lock and writing its pid leaves
    # neither a process nor a status. It must not be polled forever.
    root = _install_ssh(tmp_path, monkeypatch, FAKE_SSH)
    monkeypatch.setattr("nexus_deploy._remote.secrets.token_hex", lambda _n: "deadbeefdeadbeef")
    monkeypatch.setattr(_remote, "_DETACHED_STARTUP_GRACE_S", 1)
    (root / "deadbeefdeadbeef" / "lock").mkdir(parents=True)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run("echo never\n")
    assert "without leaving an exit status" in (caught.value.output or "")


def test_a_truncated_upload_starts_nothing_and_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _install_ssh(tmp_path, monkeypatch, FAKE_SSH_TRUNCATED_UPLOAD)
    counter = tmp_path / "ran"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run(f'echo x >> {counter}\necho "this line is past the cut"\n')
    assert "upload incomplete" in (caught.value.output or "")
    assert not counter.exists(), "no part of a truncated script ran"
    assert [p.name for p in root.rglob("script.*")] == [], "and the partial upload is removed"

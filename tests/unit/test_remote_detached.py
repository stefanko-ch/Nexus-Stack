"""A long remote script survives a dropped SSH session.

`ssh nexus bash -s` ties a script to the session that started it. Twice in the
field that session dropped while the server kept working: during an image
build in compose-up (#972) and, 75 seconds into a spin-up, during the R2
restore. The pipeline aborted with rc=255, the phases after it never ran, and
the stack was left half set up.

`detached=True` starts the script on the server under `setsid nohup`, with
its output and exit status written to files there, and polls for the status
over short SSH calls. A call that fails with 255 is one lost poll, not a
failed script.

The tests replace `subprocess.run` with a small model of the server: a job
directory, a script that takes a number of polls to finish, and a list of
calls on which the transport drops.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from nexus_deploy import _remote, compose_runner
from nexus_deploy.s3_restore import restore_from_s3, snapshot_to_s3
from nexus_deploy.ssh import SSHClient

TRANSPORT_DROP = 255


class FakeServer:
    """Stands in for `ssh <host> <command>`: the launcher, the poll, the fetch, the cleanup."""

    def __init__(
        self,
        *,
        polls_until_done: int = 2,
        exit_status: int = 0,
        output: str = "→ step one\n→ step two\n",
        drop_on_calls: tuple[int, ...] = (),
        vanish_after_start: bool = False,
        truncate_upload: bool = False,
        lose_answer_on_calls: tuple[int, ...] = (),
        poll_says: str | None = None,
        fetch_status: int = 0,
        call_cost_s: float = 0.0,
    ) -> None:
        self.polls_until_done = polls_until_done
        self.exit_status = exit_status
        self.output = output
        self.drop_on_calls = set(drop_on_calls)
        self.vanish_after_start = vanish_after_start
        self.truncate_upload = truncate_upload
        # Calls the server handles in full, but whose answer never arrives.
        self.lose_answer_on_calls = set(lose_answer_on_calls)
        self.poll_says = poll_says
        self.fetch_status = fetch_status
        # What each call costs on the clock, to model calls that hang.
        self.call_cost_s = call_cost_s
        self.now = 0.0
        self.calls: list[list[str]] = []
        self.received_script: str | None = None
        self.starts = 0
        self.polls = 0
        self.cleaned = False
        self.job_dir: str | None = None

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        assert argv[0] == "ssh", argv
        command = argv[2]
        call_number = len(self.calls)
        self.now += self.call_cost_s
        if call_number in self.drop_on_calls:
            return self._result(argv, kwargs, TRANSPORT_DROP, "client_loop: send disconnect\n")
        if call_number in self.lose_answer_on_calls:
            self._handle(argv, command, kwargs)
            return self._result(argv, kwargs, TRANSPORT_DROP, "client_loop: send disconnect\n")
        return self._handle(argv, command, kwargs)

    def _handle(
        self, argv: list[str], command: str, kwargs: dict[str, Any]
    ) -> subprocess.CompletedProcess[str]:

        if "nexus-detached launch" in command:
            return self._launch(argv, command, kwargs)
        if "nexus-detached poll" in command:
            return self._poll(argv, kwargs)
        if "nexus-detached fetch" in command:
            stream = "err" if command.rstrip().endswith("/err") else "out"
            text = self.output if stream == "out" else ""
            if self.fetch_status != 0:
                return self._result(argv, kwargs, self.fetch_status, "cat: No such file\n")
            return self._result(argv, kwargs, 0, text)
        if "nexus-detached cleanup" in command:
            self.cleaned = True
            return self._result(argv, kwargs, 0, "")
        raise AssertionError(f"unexpected remote command: {command}")

    def _launch(
        self, argv: list[str], command: str, kwargs: dict[str, Any]
    ) -> subprocess.CompletedProcess[str]:
        script = kwargs.get("input") or ""
        declared = re.search(r"-ne (\d+) \]", command)
        assert declared, "the launcher must check the size of the upload"
        directory = re.search(r"(/run/nexus-deploy/[0-9a-f]+)", command)
        assert directory, "the launcher must name a job directory under /run/nexus-deploy"
        self.job_dir = directory.group(1)
        if self.truncate_upload:
            script = script[: len(script) // 2]
        if len(script.encode()) != int(declared.group(1)):
            # What the size check does on the server: refuse, start nothing.
            return self._result(argv, kwargs, 1, "script: upload incomplete, nothing started\n")
        if self.starts == 0:
            self.received_script = script
        self.starts = 1  # the marker makes a second launch a no-op
        return self._result(argv, kwargs, 0, "")

    def _poll(self, argv: list[str], kwargs: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        self.polls += 1
        if self.poll_says is not None:
            return self._result(argv, kwargs, 0, self.poll_says)
        if self.vanish_after_start:
            return self._result(argv, kwargs, 0, "GONE\n")
        if self.polls >= self.polls_until_done:
            return self._result(argv, kwargs, 0, f"DONE {self.exit_status}\n")
        return self._result(argv, kwargs, 0, "RUNNING\n")

    @staticmethod
    def _result(
        argv: list[str], kwargs: dict[str, Any], code: int, text: str
    ) -> subprocess.CompletedProcess[str]:
        if code != 0 and kwargs.get("check"):
            raise subprocess.CalledProcessError(code, argv, output=text)
        return subprocess.CompletedProcess(argv, code, stdout=text, stderr=None)


def run_detached(
    monkeypatch: pytest.MonkeyPatch, server: FakeServer, script: str = "echo hi\n", **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", server)

    def sleep(seconds: float) -> None:
        server.now += seconds

    return _remote.ssh_run_script(
        script, detached=True, _sleep=sleep, _clock=lambda: server.now, **kwargs
    )


# ---- the ordinary case --------------------------------------------------------


def test_it_returns_the_script_output_and_exit_status(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(output="→ restore: done\n")
    result = run_detached(monkeypatch, server, "do-the-restore\n")
    assert result.returncode == 0
    assert result.stdout == "→ restore: done\n"
    assert server.received_script == "do-the-restore\n"


def test_the_script_travels_on_stdin_never_in_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer()
    run_detached(monkeypatch, server, "export TOKEN=s3cr3t-value\n")
    for argv in server.calls:
        assert "s3cr3t-value" not in " ".join(argv)


def test_the_job_directory_is_removed_afterwards(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer()
    run_detached(monkeypatch, server)
    assert server.cleaned


def test_a_failing_script_raises_with_its_own_exit_status(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(exit_status=3, output="✗ rclone failed\n")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server)
    assert caught.value.returncode == 3
    assert caught.value.output == "✗ rclone failed\n"
    assert server.cleaned, "a failed job is cleaned up too"


def test_check_false_returns_the_failure_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer(exit_status=3, output="✗ failed\n")
    result = run_detached(monkeypatch, server, check=False)
    assert result.returncode == 3
    assert result.stdout == "✗ failed\n"


# ---- the reason this exists: dropped sessions ---------------------------------


def test_a_dropped_poll_is_not_a_failed_script(monkeypatch: pytest.MonkeyPatch) -> None:
    # launch is call 1; calls 2 and 3 are polls that drop; the script still finishes.
    server = FakeServer(polls_until_done=2, drop_on_calls=(2, 3))
    result = run_detached(monkeypatch, server)
    assert result.returncode == 0
    assert result.stdout == "→ step one\n→ step two\n"


def test_a_dropped_launch_is_retried_and_the_script_starts_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer(drop_on_calls=(1,))
    result = run_detached(monkeypatch, server)
    assert result.returncode == 0
    assert server.starts == 1


def test_a_dropped_fetch_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1 launch, 2 poll (RUNNING), 3 poll (DONE), 4 fetch drops, 5 fetch.
    server = FakeServer(polls_until_done=2, drop_on_calls=(4,))
    result = run_detached(monkeypatch, server)
    assert result.stdout == "→ step one\n→ step two\n"


def test_a_server_that_stays_unreachable_ends_in_a_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer(polls_until_done=10_000, drop_on_calls=tuple(range(2, 400)))
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server, max_unreachable_s=60.0, poll_interval_s=5.0)
    assert caught.value.returncode == TRANSPORT_DROP
    assert len(server.calls) < 40, "it gives up after the unreachable budget, not never"


def test_a_launch_whose_answer_is_lost_does_not_start_the_script_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The server took the script and started it; the client saw 255 and asks again.
    server = FakeServer(lose_answer_on_calls=(1,))
    result = run_detached(monkeypatch, server, "the-one-script\n")
    assert result.returncode == 0
    assert server.starts == 1
    assert server.received_script == "the-one-script\n"


def test_calls_that_hang_count_against_the_unreachable_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every call costs two minutes and fails. Ten minutes of that is the limit,
    # not ten minutes of sleeping between calls.
    server = FakeServer(drop_on_calls=tuple(range(1, 400)), call_cost_s=120.0)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server, max_unreachable_s=600.0, poll_interval_s=5.0)
    assert caught.value.returncode == TRANSPORT_DROP
    # Five two-minute calls are ten minutes; the first one counts.
    assert len(server.calls) == 5


def test_the_timeout_bounds_a_script_that_never_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(polls_until_done=10_000)
    with pytest.raises(subprocess.TimeoutExpired):
        run_detached(monkeypatch, server, timeout=60.0, poll_interval_s=5.0)
    assert len(server.calls) < 20


def test_the_timeout_bounds_launch_retries_too(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(drop_on_calls=tuple(range(1, 400)))
    with pytest.raises(subprocess.TimeoutExpired):
        run_detached(
            monkeypatch, server, timeout=30.0, poll_interval_s=5.0, max_unreachable_s=10_000.0
        )
    assert server.starts == 0


# ---- states that must not be read as success -----------------------------------


def test_a_job_that_vanished_is_an_error_not_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # The server rebooted, or /run was cleared: no status file and no process.
    server = FakeServer(vanish_after_start=True)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server)
    assert caught.value.returncode != 0
    assert "without leaving an exit status" in (caught.value.output or "")


def test_a_truncated_upload_is_refused_and_nothing_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    # A session that drops during the upload ends `cat` with a short file and status 0.
    server = FakeServer(truncate_upload=True)
    with pytest.raises(subprocess.CalledProcessError):
        run_detached(monkeypatch, server)
    assert server.starts == 0
    assert server.received_script is None


def test_a_poll_the_server_answers_with_nonsense_is_an_error_not_a_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reached, but not DONE, RUNNING or GONE. Polling on would never end.
    server = FakeServer(poll_says="sh: 1: stat: not found\n")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server)
    assert "could not read the state" in (caught.value.output or "")
    assert len(server.calls) < 5


def test_output_that_cannot_be_read_is_an_error_and_the_job_directory_stays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The script finished with 0, but callers parse its output for their result.
    server = FakeServer(fetch_status=1)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_detached(monkeypatch, server)
    assert "could not be read" in (caught.value.output or "")
    assert not server.cleaned, "left on the server for inspection"


def test_without_detached_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen["argv"] = argv
        seen["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr=None)

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    result = _remote.ssh_run_script("echo hi\n")
    assert seen["argv"] == ["ssh", "nexus", "bash", "-s"]
    assert seen["input"] == "echo hi\n"
    assert result.stdout == "ok\n"


# ---- the steps that run detached ----------------------------------------------
#
# Three remote steps run for minutes and have each lost their session in the
# field. These pin that they are the ones sent detached; a step moved back to
# an attached session would fail here, not on a class's spin-up.


def test_the_ssh_client_passes_detached_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(script: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs, script=script)
        return subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr=None)

    monkeypatch.setattr("nexus_deploy.ssh._remote.ssh_run_script", fake)
    SSHClient("stack-host").run_script("echo hi\n", check=False, detached=True)
    assert seen["detached"] is True
    assert seen["host"] == "stack-host"
    assert seen["check"] is False
    assert seen["script"] == "echo hi\n"


def test_compose_up_runs_detached_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(script: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(["ssh"], 0, stdout="RESULT started=1 failed=0\n")

    monkeypatch.setattr("nexus_deploy.compose_runner._remote.ssh_run_script", fake)
    compose_runner.run_compose_up(["jupyter"])
    assert seen.get("detached") is True


def _persistence_env() -> dict[str, str]:
    return {
        "NEXUS_S3_PERSISTENCE": "true",
        "PERSISTENCE_S3_ENDPOINT": "https://example.r2.cloudflarestorage.com",
        "PERSISTENCE_S3_REGION": "auto",
        "PERSISTENCE_S3_BUCKET": "nexus-example-persistence",
        "R2_ACCESS_KEY_ID": "key",
        "R2_SECRET_ACCESS_KEY": "secret",
        "PERSISTENCE_STACK_SLUG": "nexus-stack",
        "PERSISTENCE_TEMPLATE_VERSION": "v1.2.3",
    }


def _recording_ssh(stdout: str) -> Any:
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        ["ssh"], 0, stdout=stdout, stderr=None
    )
    return ssh


def test_the_r2_restore_runs_detached() -> None:
    ssh = _recording_ssh("fresh-start: no snapshot in S3, leaving local state empty\n")
    restore_from_s3(ssh, env=_persistence_env())
    assert ssh.run_script.call_args.kwargs.get("detached") is True


def test_the_teardown_snapshot_runs_detached() -> None:
    ssh = _recording_ssh("snapshot complete\n")
    snapshot_to_s3(
        ssh,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        env=_persistence_env(),
        timestamp_factory=lambda: "20260511T120000Z",
    )
    assert ssh.run_script.call_args.kwargs.get("detached") is True

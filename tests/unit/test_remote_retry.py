"""Retrying a dropped SSH connection (#972) for operations safe to repeat.

`_remote._retry_transport` reruns a call that failed with a transport
status and nothing else. These tests pin which statuses count, how many
attempts there are, and that the opt-in on `ssh_run_script` and its use by
the stack-sync cleanup stay wired.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from nexus_deploy import _remote, stack_sync


def _flaky(statuses: list[int]) -> tuple[list[int], Any]:
    """A call that fails with each status in turn, then succeeds."""
    seen: list[int] = []

    def call() -> subprocess.CompletedProcess[str]:
        if len(seen) < len(statuses):
            seen.append(statuses[len(seen)])
            raise subprocess.CalledProcessError(seen[-1], ["ssh"], output="", stderr="dropped")
        seen.append(0)
        return subprocess.CompletedProcess(["ssh"], 0, "ok", "")

    return seen, call


def test_a_transport_failure_is_retried_until_it_works() -> None:
    seen, call = _flaky([255, 255])
    result = _remote._retry_transport(call, retries=2, transport_codes=frozenset({255}), label="t")
    assert result.stdout == "ok"
    assert seen == [255, 255, 0]


def test_the_last_transport_failure_is_raised() -> None:
    seen, call = _flaky([255, 255, 255])
    with pytest.raises(subprocess.CalledProcessError) as caught:
        _remote._retry_transport(call, retries=2, transport_codes=frozenset({255}), label="t")
    assert caught.value.returncode == 255
    assert seen == [255, 255, 255]


def test_any_other_status_is_raised_at_once() -> None:
    seen, call = _flaky([1])
    with pytest.raises(subprocess.CalledProcessError) as caught:
        _remote._retry_transport(call, retries=2, transport_codes=frozenset({255}), label="t")
    assert caught.value.returncode == 1
    assert seen == [1]


def test_no_retries_means_one_attempt() -> None:
    seen, call = _flaky([255])
    with pytest.raises(subprocess.CalledProcessError):
        _remote._retry_transport(call, retries=0, transport_codes=frozenset({255}), label="t")
    assert seen == [255]


@pytest.mark.parametrize("status", [10, 12, 30, 35, 255])
def test_rsync_transport_statuses_are_retried(status: int) -> None:
    seen, call = _flaky([status])
    _remote._retry_transport(
        call, retries=1, transport_codes=_remote._RSYNC_TRANSPORT_CODES, label="t"
    )
    assert seen == [status, 0]


@pytest.mark.parametrize("status", [1, 2, 3, 11, 23, 24])
def test_rsync_failures_that_are_not_transport_are_not(status: int) -> None:
    """23 partial transfer and 11 file I/O are real errors, not a drop."""
    seen, call = _flaky([status])
    with pytest.raises(subprocess.CalledProcessError):
        _remote._retry_transport(
            call, retries=2, transport_codes=_remote._RSYNC_TRANSPORT_CODES, label="t"
        )
    assert seen == [status]


def test_ssh_run_script_retries_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[list[str]] = []

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        attempts.append(args)
        if len(attempts) == 1:
            raise subprocess.CalledProcessError(255, args)
        return subprocess.CompletedProcess(args, 0, "done", "")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    assert _remote.ssh_run_script("true", transport_retries=1).stdout == "done"
    assert len(attempts) == 2

    attempts.clear()
    with pytest.raises(subprocess.CalledProcessError):
        _remote.ssh_run_script("true")
    assert len(attempts) == 1, "the default stays one attempt"


def test_the_stack_sync_cleanup_asks_for_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(script: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(["ssh"], 0, "RESULT stopped=0 removed=0 failed=0\n", "")

    monkeypatch.setattr("nexus_deploy.stack_sync._remote.ssh_run_script", fake)
    stack_sync.cleanup_disabled_stacks(["spark"])
    assert seen.get("transport_retries", 0) >= 1

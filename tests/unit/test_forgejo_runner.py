"""Tests for the server half of the Forgejo runner registration.

The bulk of these guard one property: the 40-hex secret must never
become a process argument, on either side of the SSH connection. That
is not style — this repository is public and its CI logs are readable
by anyone.
"""

from __future__ import annotations

import dataclasses
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest

from nexus_deploy.forgejo_runner import (
    DEFAULT_RUNNER_LABELS,
    RegisterResult,
    render_register_script,
    run_register,
)

SECRET = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


@dataclass
class FakeCompleted:
    returncode: int
    stdout: str = ""


class FakeSSH:
    """Records what run_script was handed, and with which argv."""

    def __init__(self, returncode: int = 0, raises: Exception | None = None) -> None:
        self.returncode = returncode
        self.raises = raises
        self.scripts: list[str] = []
        self.kwargs: list[dict[str, Any]] = []

    def run_script(self, script: str, **kwargs: Any) -> FakeCompleted:
        if self.raises is not None:
            raise self.raises
        self.scripts.append(script)
        self.kwargs.append(kwargs)
        return FakeCompleted(returncode=self.returncode)


# ---------------------------------------------------------------------------
# Secret containment
# ---------------------------------------------------------------------------


def test_secret_is_piped_from_a_builtin_not_passed_as_a_flag() -> None:
    """--secret <value> would leave the secret in the remote ps table."""
    script = render_register_script(secret=SECRET, name="nexus-runner")

    # Forgejo declares secret-stdin as a StringFlag, so the bare flag
    # is rejected with "flag needs an argument" and the runner never
    # registers. The value is discarded by the implementation — only
    # its presence routes the read to stdin — but it must be there.
    assert "--secret-stdin=1" in script
    # The bare --secret flag must not appear. Guard against the exact
    # regression: someone "simplifying" the printf pipe away.
    assert "--secret " not in script
    assert f"--secret {SECRET}" not in script
    assert "printf '%s'" in script


def test_secret_appears_exactly_once_and_shell_quoted() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner")
    assert script.count(SECRET) == 1
    assert shlex.quote(SECRET) in script


def test_run_register_never_puts_the_secret_in_argv() -> None:
    """The script travels on stdin; argv is only ever ssh + bash -s.

    FakeSSH stands in for SSHClient.run_script, whose contract is
    exactly that. This asserts we call it rather than .run().
    """
    ssh = FakeSSH()
    result = run_register(ssh, secret=SECRET)  # type: ignore[arg-type]

    assert result.status == "registered"
    assert len(ssh.scripts) == 1
    assert SECRET in ssh.scripts[0]
    # check=False so a non-zero exit becomes a RegisterResult rather
    # than a CalledProcessError whose .cmd could be logged.
    assert ssh.kwargs[0]["check"] is False


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "tooshort",
        "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678",  # uppercase
        "a1b2c3d4e5f60718293a4b5c6d7e8f901234567",  # 39
        "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789",  # 41
        "g1b2c3d4e5f60718293a4b5c6d7e8f9012345678",  # non-hex
    ],
)
def test_malformed_secret_is_refused_before_any_ssh(bad: str) -> None:
    ssh = FakeSSH()
    result = run_register(ssh, secret=bad)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert ssh.scripts == []


def test_failure_detail_names_a_category_not_the_value() -> None:
    """A rejected secret is still a secret — the error must not echo it.

    The project rule is `type(exc).__name__` rather than `str(exc)` in
    error output, so the detail carries the category and the field set,
    not the exception message and never the value.
    """
    bad = "deadbeef" * 4  # 32 chars: right alphabet, wrong length
    result = run_register(FakeSSH(), secret=bad)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert bad not in result.detail
    assert "ValueError" in result.detail


@pytest.mark.parametrize("bad", ["", "has space", "-leading", "a" * 64, "semi;colon"])
def test_invalid_runner_name_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid runner name"):
        render_register_script(secret=SECRET, name=bad)


@pytest.mark.parametrize("bad", ["a/b/c", "has space", "/leading"])
def test_invalid_scope_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid runner scope"):
        render_register_script(secret=SECRET, name="nexus-runner", scope=bad)


def test_scope_owner_repo_is_accepted() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner", scope="admin/workspace")
    assert "--scope" in script
    assert shlex.quote("admin/workspace") in script


def test_no_scope_means_no_scope_flag() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner")
    assert "--scope" not in script


# ---------------------------------------------------------------------------
# Exit-code dispatch
# ---------------------------------------------------------------------------


def test_missing_container_is_skipped_not_failed() -> None:
    """Exit 3 means Forgejo isn't running — not that anything broke."""
    result = run_register(FakeSSH(returncode=3), secret=SECRET)  # type: ignore[arg-type]

    assert result.status == "skipped"
    assert "not running" in result.detail


def test_nonzero_exit_is_failed_and_reports_the_code() -> None:
    result = run_register(FakeSSH(returncode=1), secret=SECRET)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert "1" in result.detail


def test_transport_error_is_failed_without_leaking_the_exception_text() -> None:
    """TimeoutExpired.cmd can carry argv; report only the type."""
    ssh = FakeSSH(raises=subprocess.TimeoutExpired(cmd=["ssh", "h", "bash", "-s"], timeout=1))
    result = run_register(ssh, secret=SECRET)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert result.detail == "transport (TimeoutExpired)"


def test_result_is_frozen() -> None:
    result = RegisterResult(status="registered", detail="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.detail = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The rendered bash must actually be bash
# ---------------------------------------------------------------------------


def test_rendered_script_parses() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner", scope="admin")
    proc = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_rendered_script_is_strict_mode() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner")
    assert script.startswith("set -euo pipefail")


def test_container_name_is_quoted_into_the_script() -> None:
    script = render_register_script(secret=SECRET, name="nexus-runner", container="forgejo")
    assert (
        "CONTAINER='forgejo'" in script
        or 'CONTAINER="forgejo"' in script
        or "CONTAINER=forgejo" in script
    )


# ---------------------------------------------------------------------------
# Labels — the difference between a runner that works and one that idles
# ---------------------------------------------------------------------------


def test_registration_declares_the_labels() -> None:
    """A record created without `--labels` has none, and the server
    matches `runs-on:` against the record — not against whatever the
    daemon later reads from its own config. The first live deploy showed
    exactly that: connected, idle, Labels column empty, and every job
    would have queued forever.
    """
    script = render_register_script(secret=SECRET, name="nexus-runner")

    assert "--labels" in script
    for label in DEFAULT_RUNNER_LABELS:
        assert label in script


def test_github_style_labels_are_present_so_copied_workflows_resolve() -> None:
    """`runs-on: ubuntu-latest` is what a workflow copied from GitHub
    says. Without the alias it matches nothing and hangs."""
    names = {label.split(":", 1)[0] for label in DEFAULT_RUNNER_LABELS}

    assert "docker" in names
    assert "ubuntu-latest" in names


def test_runner_config_labels_match_the_registration_labels() -> None:
    """The two lists must not drift.

    The server stores what registration declares; the daemon reads
    `runner-config.yml`. If they disagree, the mismatch is silent — the
    runner shows up healthy and jobs either never dispatch or dispatch
    to a label the daemon does not honour.
    """
    from pathlib import Path

    import yaml

    config = yaml.safe_load(Path("stacks/forgejo-runner/runner-config.yml").read_text())

    assert tuple(config["runner"]["labels"]) == DEFAULT_RUNNER_LABELS


@pytest.mark.parametrize(
    "bad",
    ["nocolon", ":leading", "has space:docker://x", "-dash:docker://x", ""],
)
def test_malformed_labels_are_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid runner label"):
        render_register_script(secret=SECRET, name="nexus-runner", labels=(bad,))


def test_no_labels_means_no_labels_flag() -> None:
    """An empty tuple is a deliberate "leave the record alone", not a
    reason to emit a bare flag the CLI would reject."""
    script = render_register_script(secret=SECRET, name="nexus-runner", labels=())

    assert "--labels" not in script

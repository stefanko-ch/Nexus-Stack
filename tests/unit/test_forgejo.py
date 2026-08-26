"""Tests for Forgejo account provisioning.

Two properties carry most of the weight here:

* Generated passwords must survive shell quoting intact — a password
  with a space or a quote must not become two arguments or break the
  script.
* The exit-code dispatch must keep "Forgejo is not enabled" separate
  from "the Docker daemon is down". Collapsing those hides an outage
  behind a harmless-looking `skipped`.
"""

from __future__ import annotations

import dataclasses
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest

from nexus_deploy.forgejo import (
    EXIT_DB_SYNC_FAILED,
    EXIT_NO_CONTAINER,
    EXIT_NOT_READY,
    Account,
    ConfigureResult,
    render_configure_script,
    render_ready_preamble,
    run_configure,
)

ADMIN = Account(username="admin", password="s3cret", email="admin@example.com", admin=True)
USER = Account(username="student", password="other", email="student@example.com")


@dataclass
class FakeCompleted:
    returncode: int
    stdout: str = ""


class FakeSSH:
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


def _executable_lines(script: str) -> list[str]:
    return [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_rendered_script_parses() -> None:
    script = render_configure_script((ADMIN, USER))
    proc = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    "password",
    ["with space", "quote'inside", 'double"quote', "semi;colon", "dollar$sign", "back`tick`"],
)
def test_shell_hostile_passwords_survive_quoting(password: str) -> None:
    """Generated passwords are `special=false` today, but nothing in
    the renderer should depend on that."""
    account = dataclasses.replace(ADMIN, password=password)
    script = render_configure_script((account,))

    assert shlex.quote(password) in script
    proc = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_admin_flag_only_on_the_admin_account() -> None:
    script = render_configure_script((ADMIN, USER))
    calls = [ln for ln in script.splitlines() if ln.startswith("ensure_account ")]

    assert len(calls) == 2
    assert calls[0].endswith("--admin")
    assert not calls[1].endswith("--admin")


def test_account_lookup_is_column_exact_not_substring() -> None:
    """A plain grep would match the username inside another user's
    email. The awk column pick is what prevents that."""
    script = render_configure_script((ADMIN,))
    assert "awk 'NR > 1 { print $2 }'" in script
    assert "grep -qxF" in script


def test_existing_account_gets_its_password_synced_not_a_failed_create() -> None:
    """Idempotency is the repair path after a credential rotation."""
    script = render_configure_script((ADMIN,))
    assert "forgejo admin user change-password" in script
    assert "forgejo admin user create" in script


def test_container_name_is_shell_quoted() -> None:
    hostile = "forgejo;rm -rf /"
    script = render_configure_script((ADMIN,), container=hostile)
    assert f"CONTAINER={shlex.quote(hostile)}" in script
    assert "CONTAINER=forgejo;rm" not in script


def test_empty_account_tuple_is_refused() -> None:
    with pytest.raises(ValueError, match="no accounts"):
        render_configure_script(())


@pytest.mark.parametrize("bad", ["", "-leading", "has space", "a" * 64, "semi;colon"])
def test_invalid_username_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid username"):
        render_configure_script((dataclasses.replace(ADMIN, username=bad),))


@pytest.mark.parametrize("bad", ["", "no-at-sign", "two@@at.com", "spaces @x.com"])
def test_invalid_email_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid email"):
        render_configure_script((dataclasses.replace(ADMIN, email=bad),))


def test_empty_password_raises() -> None:
    with pytest.raises(ValueError, match="empty password"):
        render_configure_script((dataclasses.replace(ADMIN, password=""),))


# ---------------------------------------------------------------------------
# The readiness preamble
# ---------------------------------------------------------------------------


def test_preamble_captures_docker_ps_instead_of_piping_it() -> None:
    """Regression guard. `docker ps | grep -qx` under pipefail makes a
    daemon outage and an absent container indistinguishable, so an
    outage would be reported as the harmless `skipped`.
    """
    script = render_ready_preamble()
    executable = _executable_lines(script)

    assert any("RUNNING=$(docker ps" in ln for ln in executable)
    assert not [ln for ln in executable if "docker ps --format" in ln and "| grep" in ln]
    assert any("docker ps failed" in ln for ln in executable)


def test_preamble_polls_health_before_declaring_ready() -> None:
    """`docker ps` says the process exists, not that migrations are
    done — an admin call in that window fails."""
    script = render_ready_preamble()
    assert "/api/healthz" in script
    assert f"exit {EXIT_NOT_READY}" in script


def test_preamble_distinguishes_absent_from_broken() -> None:
    script = render_ready_preamble()
    assert f"exit {EXIT_NO_CONTAINER}" in script
    assert "exit 1" in script  # docker ps itself failed


# ---------------------------------------------------------------------------
# Outcome dispatch
# ---------------------------------------------------------------------------


def test_success_reports_the_account_names() -> None:
    ssh = FakeSSH()
    result = run_configure(ssh, (ADMIN, USER))  # type: ignore[arg-type]

    assert result.status == "configured"
    assert "admin" in result.detail
    assert "student" in result.detail
    assert ssh.kwargs[0]["check"] is False


def test_password_never_reaches_local_argv() -> None:
    """run_script feeds the script on stdin; the caller must not use
    .run(), whose argv would carry the whole command."""
    ssh = FakeSSH()
    run_configure(ssh, (ADMIN,))  # type: ignore[arg-type]

    assert len(ssh.scripts) == 1
    assert ADMIN.password in ssh.scripts[0]


def test_missing_container_is_skipped() -> None:
    result = run_configure(FakeSSH(returncode=EXIT_NO_CONTAINER), (ADMIN,))  # type: ignore[arg-type]
    assert result.status == "skipped"


def test_unhealthy_forgejo_is_failed_not_skipped() -> None:
    result = run_configure(FakeSSH(returncode=EXIT_NOT_READY), (ADMIN,))  # type: ignore[arg-type]
    assert result.status == "failed"
    assert "healthy" in result.detail


def test_docker_ps_failure_is_failed_not_skipped() -> None:
    """Exit 1 from the preamble means the daemon is unreachable."""
    result = run_configure(FakeSSH(returncode=1), (ADMIN,))  # type: ignore[arg-type]
    assert result.status == "failed"


def test_validation_error_reports_a_category_not_the_password() -> None:
    bad = dataclasses.replace(ADMIN, username="has space", password="topsecret")
    ssh = FakeSSH()
    result = run_configure(ssh, (bad,))  # type: ignore[arg-type]

    assert result.status == "failed"
    assert "topsecret" not in result.detail
    assert "ValueError" in result.detail
    assert ssh.scripts == []


def test_transport_error_reports_only_the_type() -> None:
    ssh = FakeSSH(raises=subprocess.TimeoutExpired(cmd=["ssh", "h", "bash", "-s"], timeout=1))
    result = run_configure(ssh, (ADMIN,))  # type: ignore[arg-type]

    assert result.detail == "transport (TimeoutExpired)"


def test_result_is_frozen() -> None:
    result = ConfigureResult(status="configured", detail="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.detail = "y"  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "trailing\n"])
def test_password_with_a_newline_is_refused(bad: str) -> None:
    """The password crosses into the container through `read -r`, which
    stops at the first newline. Accepting one would set a password
    nobody could reproduce."""
    with pytest.raises(ValueError, match="newline"):
        render_configure_script((dataclasses.replace(ADMIN, password=bad),))


def test_password_reaches_the_container_on_stdin_not_in_docker_argv() -> None:
    """`--password "$p"` out here would land in docker's argv on the
    HOST, visible to any local `ps`. The project standard is to pipe it
    in and expand it only inside the container — see the argv-vs-stdin
    note in services.py."""
    script = render_configure_script((ADMIN,))
    executable = _executable_lines(script)

    assert any("printf '%s' \"$password\" | docker exec -i" in ln for ln in executable)
    # The host-side docker exec must not carry the password variable.
    docker_lines = [ln for ln in executable if "docker exec" in ln]
    assert not [ln for ln in docker_lines if "--password" in ln]


# ---------------------------------------------------------------------------
# Database password sync — the rebuild-cycle failure
# ---------------------------------------------------------------------------


def test_db_password_sync_runs_before_the_health_poll() -> None:
    """Ordering is the whole point.

    `POSTGRES_PASSWORD` is read only when Postgres initialises an empty
    data directory. Forgejo's lives on a restored bind mount, so after a
    rebuild teardown the database carries the previous generation's
    password while `tofu destroy` has handed Forgejo a new one. A forge
    that cannot reach its database never reports healthy — so polling
    first would time out on exactly the condition this repairs.
    """
    script = render_configure_script((ADMIN,), db_password="s3cret")
    executable = _executable_lines(script)

    def pos(needle: str) -> int:
        return next(i for i, ln in enumerate(executable) if needle in ln)

    assert pos("docker ps") < pos("ALTER USER") < pos("/api/healthz")


def test_db_password_sync_is_omitted_when_no_password_is_given() -> None:
    """Callers without one still get a working configure script."""
    script = render_configure_script((ADMIN,))
    assert "ALTER USER" not in script


@pytest.mark.parametrize("password", ["with space", "quote'inside", "back\\slash"])
def test_db_password_is_sql_escaped(password: str) -> None:
    """The value lands inside a single-quoted SQL literal. A quote would
    end the literal; a backslash must be doubled before the quote is,
    or a password containing both breaks the escape."""
    import subprocess

    script = render_configure_script((ADMIN,), db_password=password)

    assert subprocess.run(["bash", "-n", "-c", script], capture_output=True).returncode == 0
    assert "ALTER USER" in script


def test_db_sync_failure_is_reported_distinctly() -> None:
    """Its own exit code, so "the database refused the password" does
    not read as "Forgejo is slow to start"."""
    result = run_configure(FakeSSH(returncode=EXIT_DB_SYNC_FAILED), (ADMIN,))  # type: ignore[arg-type]

    assert result.status == "failed"
    assert "database password" in result.detail


def test_empty_db_password_is_refused_by_the_renderer() -> None:
    from nexus_deploy.forgejo import render_db_password_sync

    with pytest.raises(ValueError, match="empty password"):
        render_db_password_sync("")


def test_db_sync_targets_the_role_the_compose_declares() -> None:
    """A mismatch here is silent: the ALTER succeeds against the wrong
    role and Forgejo still cannot log in."""
    from pathlib import Path

    import yaml

    from nexus_deploy.forgejo import render_db_password_sync

    compose = yaml.safe_load(Path("stacks/forgejo/docker-compose.yml").read_text())
    env = compose["services"]["forgejo-db"]["environment"]
    script = render_db_password_sync("pw")

    assert env["POSTGRES_USER"] in script
    assert env["POSTGRES_DB"] in script

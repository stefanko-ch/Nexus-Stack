"""Unit tests for :mod:`nexus_deploy.forgejo`.

Ported wholesale from the Gitea client's suite when Forgejo took over
the internal forge role. The clusters worth keeping intact are the
column-exact CLI parsing (guards the dot-in-name bug from #464), the
SQL escaping, mint_token's idempotency, and the assertion that an
Authorization header never reaches argv.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
import responses

from nexus_deploy.config import NexusConfig
from nexus_deploy.forgejo import (
    EXIT_NO_CONTAINER,
    EXIT_NOT_READY,
    CreateRepoResult,
    CreateUserResult,
    ForgejoCli,
    ForgejoClient,
    ForgejoError,
    ForgejoResult,
    MirrorResult,
    OAuthAppResult,
    _basename_no_git,
    _compute_restart_services,
    _escape_sql_string_literal,
    _parse_admin_list_for_user,
    _render_db_pw_sync_script,
    _sanitize_user_for_fork_name,
    _validate_path_segment,
    render_ready_preamble,
    run_configure_forgejo,
    run_mirror_setup,
    run_woodpecker_oauth_setup,
)

BASE_URL = "http://localhost:3300"
ADMIN = "admin"
ADMIN_PASSWORD = "p@ss-w0rd!"


def _make_config(**overrides: Any) -> NexusConfig:
    defaults: dict[str, Any] = {
        "admin_username": ADMIN,
        "forgejo_admin_password": ADMIN_PASSWORD,
        "forgejo_db_password": "db-secret",
    }
    defaults.update(overrides)
    return NexusConfig.from_secrets_json(json.dumps(defaults))


def _make_ssh(stdouts: list[str | tuple[int, str]] | None = None) -> MagicMock:
    """Build a MagicMock SSH that returns the given stdouts in order.

    Each stdout entry is either a string (rc=0) or (rc, stdout).
    Once exhausted, returns rc=0 with empty stdout.
    """
    queue: list[tuple[int, str]] = []
    for entry in stdouts or []:
        if isinstance(entry, tuple):
            queue.append(entry)
        else:
            queue.append((0, entry))

    def run_script(
        _script: str, *, check: bool = False, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if queue:
            rc, out = queue.pop(0)
        else:
            rc, out = 0, ""
        return subprocess.CompletedProcess(args=["ssh"], returncode=rc, stdout=out, stderr="")

    ssh = MagicMock()
    ssh.run_script.side_effect = run_script
    return ssh


# ---------------------------------------------------------------------------
# R5 — path safety regex (CRITICAL — directory-traversal class)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "admin",
        "stefan.koch",  # dotted username — Forgejo allows
        "user_42",
        "a-b-c",
        "Stefan",
    ],
)
def test_round_5_path_safety_accepts_valid(value: str) -> None:
    _validate_path_segment(value, kind="username")  # no raise


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        "..",  # traversal
        "../etc/passwd",
        "user/admin",  # slash
        "user;rm -rf",  # shell meta
        "user`whoami`",
        "user$VAR",
        "user with space",
        "user'quote",
        'user"quote',
        "user\nnewline",
        "user@host",  # @ not allowed (emails go elsewhere)
    ],
)
def test_round_5_path_safety_rejects_unsafe(value: str) -> None:
    with pytest.raises(ForgejoError, match="unsafe"):
        _validate_path_segment(value, kind="username")


# ---------------------------------------------------------------------------
# R1 — column-exact admin-list parser (PR #464 bug class)
# ---------------------------------------------------------------------------


_ADMIN_LIST_FIXTURE = (
    "ID    Username       Email                          FullName\n"
    "1     admin          admin@example.com              Admin\n"
    "2     stefan.koch    stefan.koch@hslu.ch            Stefan\n"
)


def test_round_1_column_exact_match_finds_user() -> None:
    exists, email = _parse_admin_list_for_user(_ADMIN_LIST_FIXTURE, "stefan.koch")
    assert exists is True
    assert email == "stefan.koch@hslu.ch"


def test_round_1_column_exact_does_not_substring_match_email_column() -> None:
    """The PR #464 bug: substring-grep matched 'koch' in admin's email column.

    With column-exact awk equivalent, a username 'koch' must NOT
    match 'stefan.koch' (column 2) and must NOT match 'stefan.koch@hslu.ch'
    (column 3, even though it contains the substring).
    """
    exists, _ = _parse_admin_list_for_user(_ADMIN_LIST_FIXTURE, "koch")
    assert exists is False


def test_round_1_column_exact_does_not_substring_match_other_username() -> None:
    """'admi' must not match 'admin'."""
    exists, _ = _parse_admin_list_for_user(_ADMIN_LIST_FIXTURE, "admi")
    assert exists is False


def test_parse_empty_list_returns_false() -> None:
    assert _parse_admin_list_for_user("", "admin") == (False, None)


def test_parse_only_header_returns_false() -> None:
    assert _parse_admin_list_for_user("ID Username Email\n", "admin") == (False, None)


def test_parse_handles_short_lines_gracefully() -> None:
    """Malformed lines (whitespace-only, <2 columns) must not crash the parser.

    Line shapes:
    - ``  `` (whitespace only) → split() = [] → skipped
    - ``5 someuser`` (2 cols, no email) → matches by column 2,
      email returned as None
    """
    text = "ID Username Email\n  \n5 someuser\n"
    exists, email = _parse_admin_list_for_user(text, "someuser")
    assert exists is True
    # email column missing → None
    assert email is None


# ---------------------------------------------------------------------------
# SQL escape
# ---------------------------------------------------------------------------


def test_sql_escape_handles_backslash_first() -> None:
    """Backslash MUST be doubled BEFORE single-quote — order matters."""
    assert _escape_sql_string_literal("a\\b") == "a\\\\b"
    assert _escape_sql_string_literal("a'b") == "a''b"
    # Combination: \' should NOT become \\\\\\' (which would close+open) —
    # it should become \\\\\'\' i.e. backslash doubled then quote doubled.
    # Result: a\\\\\'\'b   (4 chars source → "a", "\\\\", "''", "b")
    assert _escape_sql_string_literal("a\\'b") == "a\\\\''b"


def test_sql_escape_passthrough_safe_chars() -> None:
    assert _escape_sql_string_literal("simple-pw_42") == "simple-pw_42"


# ---------------------------------------------------------------------------
# DB sync render + R3 retry loop
# ---------------------------------------------------------------------------


def test_render_db_sync_script_contains_set_euo_pipefail() -> None:
    script = _render_db_pw_sync_script("escaped", attempts=3, interval_s=1.0)
    assert script.splitlines()[0] == "set -euo pipefail"


def test_render_db_sync_script_uses_peer_auth() -> None:
    """No -W, no PGPASSWORD — peer auth via -U nexus-forgejo inside container."""
    script = _render_db_pw_sync_script("xx", attempts=3, interval_s=1.0)
    assert "-U nexus-forgejo" in script
    assert "PGPASSWORD" not in script
    assert " -W " not in script


def test_render_db_sync_script_parses_as_valid_bash() -> None:
    """``bash -n`` must accept the rendered script (R1 defence-in-depth).

    Static-text tests caught the Modul-2.0 multi-line skip bug only
    because we also exec'd bash. For the DB-sync script the surface
    is small enough that ``bash -n`` (parse-only) is sufficient.
    """
    script = _render_db_pw_sync_script("p''q\\\\quoted", attempts=15, interval_s=2.0)
    result = subprocess.run(
        ["bash", "-n"], input=script, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


def test_render_db_sync_script_shlex_protects_against_password_with_quotes() -> None:
    """The SQL string MUST be shlex-quoted for the bash command.

    A password containing a single quote (post-SQL-escape: ``''``)
    must not break out of bash quoting. shlex.quote wraps the whole
    SQL string in single quotes and escapes any internal single
    quote as ``'\\''`` — so the literal ``''`` is transformed by
    shlex but the bash-quoted form remains a single argument.

    Verification: the rendered script must NOT contain an unbalanced
    quoting pattern like ``'p''q'`` (which bash would parse as
    ``'p' '' 'q'`` — three separate args, breaking psql's ``-c``).
    """
    escaped = _escape_sql_string_literal("p'q")  # → "p''q"
    script = _render_db_pw_sync_script(escaped, attempts=3, interval_s=1.0)
    # Should contain the SHLEX-escaped form, not the raw '' literal.
    # shlex.quote of a string with single quotes uses '"'"' (or '\'') to
    # escape, so the unsafe `'p''q'` form must NOT appear.
    assert "'p''q'" not in script
    # Must contain the unique substrings once shlex unwraps it.
    assert "p" in script
    assert "q" in script


def test_round_3_db_sync_succeeds_after_retries() -> None:
    """rc=0 + RESULT line on first or later attempt → True."""
    ssh = _make_ssh([(0, "RESULT db_pw=synced\n")])
    cli = ForgejoCli(ssh)
    assert cli.sync_db_password("secret", attempts=3, interval_s=0.01) is True
    ssh.run_script.assert_called_once()


def test_round_3_db_sync_fails_after_all_retries() -> None:
    """rc=1 after exhausting attempts → False, no exception."""
    ssh = _make_ssh([(1, "RESULT db_pw=failed\n")])
    cli = ForgejoCli(ssh)
    assert cli.sync_db_password("secret", attempts=3, interval_s=0.01) is False


def test_db_sync_skips_when_password_empty() -> None:
    """Empty password → no ssh call, returns False."""
    ssh = _make_ssh()
    cli = ForgejoCli(ssh)
    assert cli.sync_db_password("", attempts=3, interval_s=0.01) is False
    ssh.run_script.assert_not_called()


def test_db_sync_password_never_in_argv_only_in_script_stdin() -> None:
    """R7 / defence-in-depth — password must reach SSH via run_script
    (stdin), not via run (argv). Verify by asserting `run` is never called.
    """
    ssh = _make_ssh([(0, "RESULT db_pw=synced\n")])
    cli = ForgejoCli(ssh)
    cli.sync_db_password("supersecret-do-not-leak", attempts=2, interval_s=0.01)
    # MagicMock.run is NOT called
    ssh.run.assert_not_called()
    # The script (which contains the password) was passed as the first
    # positional arg to run_script.
    call_script = ssh.run_script.call_args[0][0]
    assert "supersecret-do-not-leak" in call_script


# ---------------------------------------------------------------------------
# ForgejoCli — admin list + create + sync
# ---------------------------------------------------------------------------


def test_list_admin_users_returns_stdout_on_success() -> None:
    ssh = _make_ssh([(0, _ADMIN_LIST_FIXTURE)])
    assert ForgejoCli(ssh).list_admin_users() == _ADMIN_LIST_FIXTURE


def test_list_admin_users_returns_empty_on_ssh_failure() -> None:
    """Non-zero rc → empty string (caller routes to CREATE branch)."""
    ssh = _make_ssh([(1, "boom\n")])
    assert ForgejoCli(ssh).list_admin_users() == ""


def test_create_admin_returns_created_on_success_keyword() -> None:
    ssh = _make_ssh([(0, "New user 'admin' has been created\n")])
    result = ForgejoCli(ssh).create_admin("admin", "pw", "a@b.c")
    assert result.status == "created"


def test_create_admin_returns_already_exists_on_collision() -> None:
    ssh = _make_ssh([(1, "user already exists\n")])
    result = ForgejoCli(ssh).create_admin("admin", "pw", "a@b.c")
    assert result.status == "already_exists"


def test_create_admin_returns_failed_on_other_error() -> None:
    ssh = _make_ssh([(1, "Some other validation error\n")])
    result = ForgejoCli(ssh).create_admin("admin", "pw", "a@b.c")
    assert result.status == "failed"
    assert "Some other validation error" in result.detail


def test_create_admin_path_safety() -> None:
    ssh = _make_ssh([(0, "")])
    with pytest.raises(ForgejoError, match="unsafe"):
        ForgejoCli(ssh).create_admin("ad;min", "pw", "a@b.c")
    ssh.run_script.assert_not_called()


def test_sync_password_returns_synced_on_rc_zero() -> None:
    ssh = _make_ssh([(0, "")])
    assert ForgejoCli(ssh).sync_password("admin", "newpw").status == "synced"


def test_sync_password_returns_failed_on_rc_nonzero() -> None:
    ssh = _make_ssh([(1, "user not found")])
    result = ForgejoCli(ssh).sync_password("admin", "newpw")
    assert result.status == "failed"


def test_sync_password_uses_run_script_not_run() -> None:
    """R7 — password is in the rendered script, fed via stdin."""
    ssh = _make_ssh([(0, "")])
    ForgejoCli(ssh).sync_password("admin", "leakable-pw")
    ssh.run.assert_not_called()
    assert "leakable-pw" in ssh.run_script.call_args[0][0]


# ---------------------------------------------------------------------------
# ForgejoClient (REST) — basic-auth + token-auth
# ---------------------------------------------------------------------------


def _client(token: str | None = None) -> ForgejoClient:
    base = ForgejoClient(BASE_URL, admin_username=ADMIN, admin_password=ADMIN_PASSWORD)
    return base.with_token(token) if token else base


def test_client_rejects_empty_admin_username() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ForgejoClient(BASE_URL, admin_username="", admin_password="pw")


def test_client_rejects_empty_admin_password() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ForgejoClient(BASE_URL, admin_username="admin", admin_password="")


def test_client_rejects_unsafe_admin_username() -> None:
    with pytest.raises(ForgejoError, match="unsafe"):
        ForgejoClient(BASE_URL, admin_username="adm;in", admin_password="pw")


def test_with_token_rejects_empty_token() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _client().with_token("")


@responses.activate
def test_wait_ready_returns_true_on_200() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)
    assert _client().wait_ready(timeout_s=1.0, interval_s=0.05) is True


@responses.activate
def test_wait_ready_times_out() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=503)
    assert _client().wait_ready(timeout_s=0.2, interval_s=0.05) is False


# ---------------------------------------------------------------------------
# R2 — legacy email-collision PATCH
# ---------------------------------------------------------------------------


@responses.activate
def test_round_2_patch_user_email_returns_true_on_200() -> None:
    responses.add(
        responses.PATCH,
        f"{BASE_URL}/api/v1/admin/users/admin",
        status=200,
        json={"id": 1},
    )
    assert _client().patch_user_email("admin", "new@e.com", login_name="admin") is True
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body == {"email": "new@e.com", "source_id": 0, "login_name": "admin"}


@responses.activate
def test_round_2_patch_user_email_includes_required_full_body() -> None:
    """Schema requires source_id + login_name even for email-only update."""
    responses.add(responses.PATCH, f"{BASE_URL}/api/v1/admin/users/admin", status=200)
    _client().patch_user_email("admin", "x@y.z", login_name="admin")
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert "source_id" in body
    assert "login_name" in body


@responses.activate
def test_patch_user_email_returns_false_on_4xx() -> None:
    responses.add(responses.PATCH, f"{BASE_URL}/api/v1/admin/users/admin", status=403)
    assert _client().patch_user_email("admin", "x@y.z", login_name="admin") is False


def test_patch_user_email_path_safety() -> None:
    with pytest.raises(ForgejoError, match="unsafe"):
        _client().patch_user_email("admi;n", "x@y.z", login_name="admin")


# ---------------------------------------------------------------------------
# R4 — token create / retry-via-delete
# ---------------------------------------------------------------------------


def test_round_4_mint_token_returns_sha1_on_success() -> None:
    """Happy path: CLI returns "Access token was successfully created: <40-hex>"."""
    ssh = _make_ssh(
        [
            (0, ""),  # psql DELETE best-effort (rc=0 fine)
            (
                0,
                "Access token was successfully created: aebafa8bbcff4e5e7edde8dc89571df698648e7d\n",
            ),
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 == "aebafa8bbcff4e5e7edde8dc89571df698648e7d"
    assert err == ""


def test_round_4_mint_token_idempotent_delete_first() -> None:
    """Token already exists → CLI delete succeeds → CLI generate succeeds.

    The delete-then-create pattern is preserved via the unconditional
    delete in mint_token. The rendered delete script
    ends in ``|| true``, so ``ssh.run_script`` always sees rc=0
    regardless of whether the inner docker-exec found a token to
    delete — both states route to the same generate call.
    """
    ssh = _make_ssh(
        [
            # Both branches of the delete (token existed / didn't exist)
            # surface as rc=0 due to the script's `|| true` suffix.
            (0, ""),
            (
                0,
                "Access token was successfully created: 0000000000000000000000000000000000000001\n",
            ),
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 == "0000000000000000000000000000000000000001"
    assert err == ""
    # Both delete + generate were called.
    assert ssh.run_script.call_count == 2
    # First call is the psql DELETE script. The SQL is shlex-quoted
    # for bash, so we assert on substrings that survive that quoting:
    # the unquoted SQL keywords (DELETE FROM, WHERE, AND uid, lower)
    # plus the literal name + username values (which appear inside
    # shlex's `'"'"'` quote-escape but the inner characters survive).
    delete_script = ssh.run_script.call_args_list[0][0][0]
    assert "DELETE FROM access_token" in delete_script
    assert "nexus-automation" in delete_script
    assert "WHERE lower_name" in delete_script
    assert "admin" in delete_script
    # Must NOT swallow stderr — `|| true` and `2>/dev/null` were
    # removed in the round-4 fix so a psql failure surfaces in
    # delete_result.stdout for inclusion in token_error.
    assert "|| true" not in delete_script
    assert "2>/dev/null" not in delete_script
    # Must NOT use the non-existent forgejo CLI subcommand
    # (PR #520 round-3 production bug — `forgejo admin user
    # delete-access-token` is hallucinated; psql DELETE is the
    # bulletproof replacement).
    assert "delete-access-token" not in delete_script


def test_mint_token_diagnostic_prepends_prior_delete_failure() -> None:
    """When psql DELETE fails AND generate fails, the diagnostic
    must include BOTH errors — the delete failure prepended to the
    generate failure. Without this, a name-collision failure on
    generate looks unexplainable when the cause is actually that
    the delete didn't run (forgejo-db not ready, transient docker
    error, etc.). Round-4 follow-up to the diagnostic field.
    """
    ssh = _make_ssh(
        [
            (
                1,
                'psql: error: connection to server at "forgejo-db" failed\n',
            ),  # psql delete fails (DB not ready)
            (
                1,
                "Command error: access token name has been used already\n",
            ),  # generate then collides
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 is None
    # Must include both diagnostics, prior delete prepended.
    assert "prior delete rc=1" in err
    assert "connection to server" in err
    assert "CLI rc=1" in err
    assert "name has been used already" in err
    # Format: `prior delete ... | CLI ...`
    assert err.index("prior delete") < err.index("CLI rc=1")


def test_mint_token_drops_delete_diagnostic_on_generate_success() -> None:
    """If delete fails (rc=1) but generate succeeds, the delete
    diagnostic is irrelevant and must NOT pollute the success
    return value. Returns (sha1, "").
    """
    ssh = _make_ssh(
        [
            (1, "psql: connection failed\n"),  # delete fails
            (
                0,
                "Access token was successfully created: " + "f" * 40 + "\n",
            ),  # generate succeeds anyway (e.g. token didn't exist)
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 == "f" * 40
    assert err == ""


def test_mint_token_returns_diagnostic_on_cli_failure() -> None:
    """Generate fails (non-zero rc) → returns (None, diagnostic) — no crash.

    Regression test for the post-#519 silent-fail bug class: previously
    a ForgejoError was caught silently with ``token = None`` and no stderr
    diagnostic, making the spin-up failure undebuggable. Now the
    diagnostic is captured and surfaced via stderr by the CLI handler.
    """
    ssh = _make_ssh(
        [
            (0, ""),  # delete OK
            (1, "User does not exist [name: admin]\n"),  # generate fails
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 is None
    assert "rc=1" in err
    assert "User does not exist" in err


def test_mint_token_returns_diagnostic_on_unparseable_output() -> None:
    """rc=0 but no sha1 in output → still surfaces a diagnostic."""
    ssh = _make_ssh(
        [
            (0, ""),
            (0, "weird unexpected success output\n"),  # no 40-hex
        ]
    )
    sha1, err = ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    assert sha1 is None
    assert "no sha1" in err.lower()


def test_mint_token_path_safety_on_username() -> None:
    ssh = _make_ssh()
    with pytest.raises(ForgejoError, match="unsafe"):
        ForgejoCli(ssh).mint_token("admin;rm -rf /", "nexus-automation")
    ssh.run_script.assert_not_called()


def test_mint_token_path_safety_on_token_name() -> None:
    ssh = _make_ssh()
    with pytest.raises(ForgejoError, match="unsafe"):
        ForgejoCli(ssh).mint_token("admin", "evil; name")
    ssh.run_script.assert_not_called()


def test_mint_token_uses_run_script_not_run() -> None:
    """R7 — peer-auth CLI commands feed via stdin to ssh.run_script,
    NOT argv. No password is involved (peer auth), so the secrecy
    surface is the username + token-name, both of which are
    already non-secret values per the path-safety contract.
    """
    ssh = _make_ssh(
        [
            (0, ""),
            (0, "Access token was successfully created: " + "f" * 40 + "\n"),
        ]
    )
    ForgejoCli(ssh).mint_token("admin", "nexus-automation")
    # Never use ssh.run (argv form)
    ssh.run.assert_not_called()


def test_mint_token_supports_custom_scopes() -> None:
    """Default scopes='all' is preserved, but caller can pass alternatives."""
    ssh = _make_ssh(
        [
            (0, ""),
            (0, "Access token was successfully created: " + "a" * 40 + "\n"),
        ]
    )
    ForgejoCli(ssh).mint_token("admin", "nexus-automation", scopes="write:repository")
    # Inspect the rendered generate script — last call to run_script
    last_script = ssh.run_script.call_args[0][0]
    assert "write:repository" in last_script


# ---------------------------------------------------------------------------
# R7 — token never in argv / URL, only Authorization header
# ---------------------------------------------------------------------------


@responses.activate
def test_round_7_token_in_authorization_header_not_argv_or_url() -> None:
    """After ``with_token``, every request carries
    ``Authorization: token <sha>`` and the token MUST NOT appear in
    the URL or in the request body.
    """
    secret_token = "do-not-leak-this-token-anywhere-please"
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/repos",
        status=201,
        json={"id": 1},
    )
    client = _client(token=secret_token)
    client.create_repo("nexus-test-forgejo", description="Hello")

    call = responses.calls[0]
    # URL: token NOT present
    assert secret_token not in (call.request.url or "")
    # Body: token NOT present
    raw_body = call.request.body
    if isinstance(raw_body, bytes):
        body_text = raw_body.decode("utf-8")
    elif isinstance(raw_body, str):
        body_text = raw_body
    else:
        body_text = ""
    assert secret_token not in body_text
    # Authorization header: token IS present in `token <sha>` form
    auth = call.request.headers.get("Authorization", "")
    assert auth == f"token {secret_token}"


@responses.activate
def test_round_7_token_not_in_basic_auth_after_with_token() -> None:
    """After ``with_token``, the basic-auth credentials MUST be gone."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/foo", status=200)
    client = _client(token="some-token")
    client.repo_exists("admin", "foo")
    auth_header = responses.calls[0].request.headers.get("Authorization", "")
    # Must NOT be Basic ... (would be base64 of admin:password)
    assert auth_header.startswith("token ")


# ---------------------------------------------------------------------------
# R6 — repo create 409 → patch_repo_private fallback
# ---------------------------------------------------------------------------


@responses.activate
def test_create_repo_returns_created_on_201() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=201, json={"id": 1})
    result = _client(token="t").create_repo("nexus-test", description="x")
    assert result.status == "created"


@responses.activate
def test_round_6_create_repo_409_returns_already_exists() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=409)
    result = _client(token="t").create_repo("nexus-test")
    assert result.status == "already_exists"


@responses.activate
def test_round_6_create_repo_422_already_exists_returns_already_exists() -> None:
    """Some Forgejo modes return 422 with 'already exists' body."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/repos",
        status=422,
        json={"message": "repository already exists"},
    )
    result = _client(token="t").create_repo("nexus-test")
    assert result.status == "already_exists"


@responses.activate
def test_create_repo_422_validation_returns_failed() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/repos",
        status=422,
        json={"message": "invalid name"},
    )
    result = _client(token="t").create_repo("nexus-test")
    assert result.status == "failed"


@responses.activate
def test_round_6_patch_repo_private_idempotent_204_or_200() -> None:
    """Used after 409 to ensure the existing repo is private."""
    responses.add(
        responses.PATCH,
        f"{BASE_URL}/api/v1/repos/admin/nexus-test",
        status=200,
    )
    assert _client(token="t").patch_repo_private("admin", "nexus-test", private=True)
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body == {"private": True}


# ---------------------------------------------------------------------------
# Collaborator add — idempotent
# ---------------------------------------------------------------------------


@responses.activate
def test_add_collaborator_returns_true_on_204() -> None:
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/nexus-test/collaborators/user",
        status=204,
    )
    assert _client(token="t").add_collaborator("admin", "nexus-test", "user")


@responses.activate
def test_add_collaborator_returns_true_on_422_already_collaborator() -> None:
    """Idempotent: 422 ('already a collaborator') counted as success."""
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/nexus-test/collaborators/user",
        status=422,
    )
    assert _client(token="t").add_collaborator("admin", "nexus-test", "user")


@responses.activate
def test_add_collaborator_returns_false_on_403() -> None:
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/nexus-test/collaborators/user",
        status=403,
    )
    assert _client(token="t").add_collaborator("admin", "nexus-test", "user") is False


def test_add_collaborator_path_safety() -> None:
    with pytest.raises(ForgejoError, match="unsafe"):
        _client(token="t").add_collaborator("admin", "nexus-test", "user;rm")


# ---------------------------------------------------------------------------
# repo_exists
# ---------------------------------------------------------------------------


@responses.activate
def test_repo_exists_200() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/a/b", status=200)
    assert _client(token="t").repo_exists("a", "b") is True


@responses.activate
def test_repo_exists_404() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/a/b", status=404)
    assert _client(token="t").repo_exists("a", "b") is False


@responses.activate
def test_repo_exists_500_raises() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/a/b", status=500)
    with pytest.raises(ForgejoError):
        _client(token="t").repo_exists("a", "b")


# ---------------------------------------------------------------------------
# RESTART_SERVICES intersection
# ---------------------------------------------------------------------------


def test_compute_restart_services_preserves_order() -> None:
    """Output order must be the canonical order (jupyter, marimo, code-server, ...)."""
    enabled = ["redpanda", "code-server", "jupyter", "marimo"]
    assert _compute_restart_services(enabled) == ("jupyter", "marimo", "code-server")


def test_compute_restart_services_empty_when_none_enabled() -> None:
    assert _compute_restart_services(["postgres", "redis"]) == ()


def test_compute_restart_services_empty_input() -> None:
    assert _compute_restart_services([]) == ()


# ---------------------------------------------------------------------------
# Top-level orchestrator — happy path + key branches
# ---------------------------------------------------------------------------


@responses.activate
def test_run_configure_forgejo_full_happy_path_admin_already_exists() -> None:
    """Admin exists, password sync, token mint via CLI, repo+collaborator add."""
    # Healthcheck OK
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)
    # Repo create
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=201, json={"id": 1})
    # Collaborator add
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/nexus-foo/collaborators/stefan.koch",
        status=204,
    )

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),  # DB pw sync
            (0, _ADMIN_LIST_FIXTURE),  # admin user list
            (0, ""),  # admin sync_password
            (0, _ADMIN_LIST_FIXTURE),  # user list (same fixture, has stefan.koch)
            (0, ""),  # user sync_password
            (0, ""),  # token: psql DELETE (best-effort)
            (0, f"Access token was successfully created: {'a' * 40}\n"),  # token: generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="admin@example.com",
        forgejo_user_email="stefan.koch@hslu.ch",
        forgejo_user_password="userpw",
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=False,
        enabled_services=["jupyter", "marimo"],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.is_success is True
    assert result.token == "a" * 40
    assert result.db_pw_synced is True
    assert result.admin.status == "synced"
    assert result.user is not None
    assert result.user.status == "synced"
    assert result.repo is not None
    assert result.repo.status == "created"
    assert result.collaborator_added is True
    assert result.restart_services == ("jupyter", "marimo")


@responses.activate
def test_run_configure_forgejo_admin_does_not_exist_creates() -> None:
    """Empty admin list → CREATE branch."""
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=201, json={"id": 1})

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),
            (0, "ID Username Email\n"),  # empty list
            (0, "New user 'admin' has been created\n"),  # create_admin
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'b' * 40}\n"),  # token: generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="admin@example.com",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=False,
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.admin.status == "created"
    assert result.user is None  # FORGEJO_USER_EMAIL was None
    assert result.token == "b" * 40


@responses.activate
def test_create_admin_already_exists_falls_back_to_sync_password() -> None:
    """Defence in depth: if list_admin_users returns empty (false negative —
    e.g. transient ssh+docker exec failure), CREATE runs and may report
    "already exists" from Forgejo. Without a follow-up sync, the admin
    password drift stays and the subsequent REST token mint 401s.
    The orchestrator now falls back to sync_password automatically.

    Regression test for Copilot round 1.
    """
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),
            (0, ""),  # admin list — empty (false negative)
            (0, "user already exists\n"),  # create_admin → already_exists
            (0, ""),  # FALLBACK: sync_password runs and succeeds
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'c' * 40}\n"),  # token: generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=True,  # skip repo to keep test focused
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    # Final admin status must be "synced" (not "already_exists") —
    # the fallback ran and the result was overwritten.
    assert result.admin.status == "synced"
    # 6 ssh.run_script calls: db_sync, list, create, sync_password (fallback),
    # psql DELETE (best-effort token cleanup), generate-access-token
    assert ssh.run_script.call_count == 6


@responses.activate
def test_create_user_already_exists_falls_back_to_sync_password() -> None:
    """Same fallback as admin — protects against the false-negative
    list path for the regular user (Copilot round 1).
    """
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),
            (0, _ADMIN_LIST_FIXTURE),  # admin exists
            (0, ""),  # admin sync_password
            (0, ""),  # user list — empty (false negative)
            (0, "user already exists\n"),  # create_user → already_exists
            (0, ""),  # FALLBACK: sync_password
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'d' * 40}\n"),  # generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email="stefan.koch@hslu.ch",
        forgejo_user_password="userpw",
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=True,
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.user is not None
    assert result.user.status == "synced"


@responses.activate
def test_round_2_legacy_email_collision_triggers_patch() -> None:
    """Admin row's email == FORGEJO_USER_EMAIL → PATCH fires before sync."""
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)
    # The PATCH call we want to verify
    responses.add(
        responses.PATCH,
        f"{BASE_URL}/api/v1/admin/users/admin",
        status=200,
    )
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=201, json={"id": 1})
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/nexus-foo/collaborators/stefan.koch",
        status=204,
    )

    # admin's email column == FORGEJO_USER_EMAIL == "stefan.koch@hslu.ch"
    legacy_admin_list = "ID Username Email FullName\n1 admin stefan.koch@hslu.ch Admin\n"
    ssh = _make_ssh(
        [
            (0, ""),  # DB pw sync (not interesting here)
            (0, legacy_admin_list),  # admin list — collision
            (0, ""),  # admin sync_password
            (0, "ID Username Email\n"),  # user list — empty
            (0, "New user 'stefan.koch' has been created\n"),  # create_user
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'e' * 40}\n"),  # generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="admin@new-domain.com",
        forgejo_user_email="stefan.koch@hslu.ch",
        forgejo_user_password="userpw",
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=False,
        enabled_services=["jupyter"],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.is_success is True
    # Verify a PATCH was made with the new admin email
    patch_calls = [c for c in responses.calls if c.request.method == "PATCH"]
    assert len(patch_calls) == 1
    body = json.loads(patch_calls[0].request.body)  # type: ignore[arg-type]
    assert body["email"] == "admin@new-domain.com"


@responses.activate
def test_round_6_repo_already_exists_falls_back_to_patch_private() -> None:
    """409 on POST → PATCH /repos/<o>/<n> with private=True."""
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)
    # Repo create returns 409
    responses.add(responses.POST, f"{BASE_URL}/api/v1/user/repos", status=409)
    # PATCH private fallback
    responses.add(
        responses.PATCH,
        f"{BASE_URL}/api/v1/repos/admin/nexus-foo",
        status=200,
    )

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),
            (0, _ADMIN_LIST_FIXTURE),
            (0, ""),  # admin sync_password
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'1' * 40}\n"),  # generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=False,
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.repo is not None
    assert result.repo.status == "already_exists"
    # Verify PATCH was issued to set private=true
    patch_calls = [c for c in responses.calls if c.request.method == "PATCH"]
    assert len(patch_calls) == 1
    body = json.loads(patch_calls[0].request.body)  # type: ignore[arg-type]
    assert body["private"] is True


@responses.activate
def test_run_configure_forgejo_mirror_mode_skips_repo_and_collaborator() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)

    ssh = _make_ssh(
        [
            (0, ""),  # db_pw_sync
            (0, _ADMIN_LIST_FIXTURE),  # admin list
            (0, ""),  # admin sync_password
            (0, ""),  # token: psql DELETE
            (0, f"Access token was successfully created: {'2' * 40}\n"),  # generate
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=True,  # ← mirror mode
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.repo is None
    assert result.collaborator_added is False
    # No POST to /api/v1/user/repos was made
    repo_calls = [c for c in responses.calls if "/user/repos" in (c.request.url or "")]
    assert len(repo_calls) == 0


@responses.activate
def test_run_configure_forgejo_not_ready_returns_failed_admin() -> None:
    """Health endpoint never 200 → admin.status=='failed', no token.

    Uses a non-default admin_username so the regression test catches
    the Copilot-round-2 finding: the early-return path on health-check
    timeout previously hardcoded ``name="admin"`` even when the
    operator configured a different admin username.
    """
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=503)

    ssh = _make_ssh([(0, "RESULT db_pw=synced\n")])

    result = run_configure_forgejo(
        _make_config(admin_username="custom-admin-name"),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="custom-admin-name",
        is_mirror_mode=False,
        enabled_services=["jupyter"],
        ready_timeout_s=0.2,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )

    assert result.is_success is False
    assert result.admin.status == "failed"
    # Round-2 regression: name must be the configured admin_username,
    # not the literal "admin".
    assert result.admin.name == "custom-admin-name"
    assert result.token is None
    assert result.restart_services == ("jupyter",)


@responses.activate
def test_run_configure_forgejo_token_mint_failure_returns_failure() -> None:
    """Token CLI fails (rc=1) → token=None, is_success=False, token_error populated."""
    responses.add(responses.GET, f"{BASE_URL}/api/healthz", status=200)

    ssh = _make_ssh(
        [
            (0, "RESULT db_pw=synced\n"),
            (0, _ADMIN_LIST_FIXTURE),
            (0, ""),  # admin sync_password
            (0, ""),  # token: psql DELETE (best-effort)
            (1, "User does not exist [name: admin]\n"),  # token: generate fails
        ]
    )

    result = run_configure_forgejo(
        _make_config(),
        base_url=BASE_URL,
        ssh=ssh,
        admin_email="a@b.c",
        forgejo_user_email=None,
        forgejo_user_password=None,
        repo_name="nexus-foo",
        forgejo_repo_owner="admin",
        is_mirror_mode=False,
        enabled_services=[],
        ready_timeout_s=1.0,
        db_sync_attempts=1,
        db_sync_interval_s=0.01,
    )
    assert result.token is None
    assert result.is_success is False
    # Diagnostic must be populated so CLI handler can emit it to stderr —
    # the post-#519 silent-fail bug class.
    assert "rc=1" in result.token_error
    assert "User does not exist" in result.token_error


# ---------------------------------------------------------------------------
# is_success on ForgejoResult
# ---------------------------------------------------------------------------


def test_is_success_true_on_clean_path() -> None:
    r = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=CreateUserResult(name="stefan", status="created"),
        token="t",
        token_error="",
        repo=CreateRepoResult(name="nexus-foo", status="created"),
        collaborator_added=True,
        restart_services=("jupyter",),
    )
    assert r.is_success is True


def test_is_success_false_when_admin_failed() -> None:
    r = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="failed"),
        user=None,
        token="t",
        token_error="",
        repo=None,
        collaborator_added=False,
        restart_services=(),
    )
    assert r.is_success is False


def test_is_success_false_when_token_missing() -> None:
    r = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=None,
        token=None,
        token_error="CLI rc=1: simulated failure",
        repo=None,
        collaborator_added=False,
        restart_services=(),
    )
    assert r.is_success is False


def test_is_success_false_when_user_failed() -> None:
    r = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=CreateUserResult(name="stefan", status="failed"),
        token="t",
        token_error="",
        repo=None,
        collaborator_added=False,
        restart_services=(),
    )
    assert r.is_success is False


def test_is_success_false_when_repo_failed() -> None:
    r = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=None,
        token="t",
        token_error="",
        repo=CreateRepoResult(name="nexus-foo", status="failed"),
        collaborator_added=False,
        restart_services=(),
    )
    assert r.is_success is False


# ---------------------------------------------------------------------------
# R8 — CLI stdout emits eval-able FORGEJO_TOKEN= AND RESTART_SERVICES=
# ---------------------------------------------------------------------------


def test_round_8_cli_emits_eval_able_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Happy-path stdout must contain BOTH eval-able lines and use shlex.quote."""
    fake_result = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=CreateUserResult(name="stefan", status="created"),
        token="abc123def-token",
        token_error="",
        repo=CreateRepoResult(name="nexus-foo", status="created"),
        collaborator_added=True,
        restart_services=("jupyter", "marimo"),
    )

    def fake_run(*_args: Any, **_kwargs: Any) -> ForgejoResult:
        return fake_result

    monkeypatch.setattr("nexus_deploy.__main__.run_configure_forgejo", fake_run)
    monkeypatch.setattr(
        "sys.stdin.read",
        lambda: json.dumps(
            {
                "admin_username": "admin",
                "forgejo_admin_password": "x",
            }
        ),
    )
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setenv("ENABLED_SERVICES", "jupyter,marimo")

    # Mock the SSH context-manager + port_forward so we don't actually ssh
    fake_ssh = MagicMock()
    fake_ssh.__enter__ = MagicMock(return_value=fake_ssh)
    fake_ssh.__exit__ = MagicMock(return_value=None)
    fake_pf_cm = MagicMock()
    fake_pf_cm.__enter__ = MagicMock(return_value=12345)
    fake_pf_cm.__exit__ = MagicMock(return_value=None)
    fake_ssh.port_forward = MagicMock(return_value=fake_pf_cm)
    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda host: fake_ssh)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 0

    captured = capsys.readouterr()
    out = captured.out
    # Both eval-able lines present
    assert re.search(r"^FORGEJO_TOKEN=.*abc123def-token", out, re.M)
    assert re.search(r"^RESTART_SERVICES=", out, re.M)
    # Token-line uses shlex-quoted form
    token_line = next(line for line in out.splitlines() if line.startswith("FORGEJO_TOKEN="))
    # Must be safely eval-able by bash; for a 40-hex-like value, no quotes
    # is acceptable; we only require the token substring is present.
    assert "abc123def-token" in token_line
    # Verify RESTART_SERVICES= encodes the comma-list
    rs_line = next(line for line in out.splitlines() if line.startswith("RESTART_SERVICES="))
    assert "jupyter,marimo" in rs_line


def test_round_8_cli_omits_token_line_when_token_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Token=None → only RESTART_SERVICES= on stdout, NO FORGEJO_TOKEN= line.

    the caller must not see a stale token from a previous deploy
    leaking via empty-string assignment.
    """
    fake_result = ForgejoResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="synced"),
        user=None,
        token=None,
        token_error="CLI rc=1: simulated production failure",
        repo=None,
        collaborator_added=False,
        restart_services=("jupyter",),
    )

    monkeypatch.setattr("nexus_deploy.__main__.run_configure_forgejo", lambda *a, **k: fake_result)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"forgejo_admin_password": "x"}')
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setenv("ENABLED_SERVICES", "jupyter")

    fake_ssh = MagicMock()
    fake_ssh.__enter__ = MagicMock(return_value=fake_ssh)
    fake_ssh.__exit__ = MagicMock(return_value=None)
    fake_pf = MagicMock()
    fake_pf.__enter__ = MagicMock(return_value=12345)
    fake_pf.__exit__ = MagicMock(return_value=None)
    fake_ssh.port_forward = MagicMock(return_value=fake_pf)
    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda host: fake_ssh)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 1  # is_success=False (token is None)

    captured = capsys.readouterr()
    out = captured.out
    err = captured.err
    assert "FORGEJO_TOKEN=" not in out
    assert re.search(r"^RESTART_SERVICES=", out, re.M)
    # Diagnostic must reach stderr — post-#519 fix that closed the
    # "silent token-mint failure" debugging blind spot.
    assert "token: NOT minted" in err
    assert "CLI rc=1: simulated production failure" in err


# ---------------------------------------------------------------------------
# OAuth2 application management (Woodpecker integration)
# ---------------------------------------------------------------------------


@responses.activate
def test_list_oauth_apps_returns_array() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": 1, "name": "Woodpecker CI"}, {"id": 2, "name": "other"}],
    )
    apps = _client(token="t").list_oauth_apps()
    assert len(apps) == 2
    assert apps[0]["name"] == "Woodpecker CI"


@responses.activate
def test_list_oauth_apps_returns_empty_on_no_apps() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[],
    )
    assert _client(token="t").list_oauth_apps() == []


@responses.activate
def test_list_oauth_apps_raises_on_500() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=500,
    )
    with pytest.raises(ForgejoError, match="HTTP 500"):
        _client(token="t").list_oauth_apps()


@responses.activate
def test_delete_oauth_app_204_returns_true() -> None:
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=204,
    )
    assert _client(token="t").delete_oauth_app(42) is True


@responses.activate
def test_delete_oauth_app_404_returns_true() -> None:
    """Idempotent — 404 (already gone) treated as success."""
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/99",
        status=404,
    )
    assert _client(token="t").delete_oauth_app(99) is True


@responses.activate
def test_delete_oauth_app_403_returns_false() -> None:
    """Definitive non-success: Forgejo KNOWS the app still exists."""
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=403,
    )
    assert _client(token="t").delete_oauth_app(42) is False


@responses.activate
def test_delete_oauth_app_raises_on_transport_error() -> None:
    """Transport error → server state UNKNOWN → raise (not False).

    Copilot R4: distinguishes the definitive 403 (server state known)
    from transport ambiguity (server state unknown) so the caller
    can route different diagnostics + different abort severity.
    """
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        body=requests.ConnectionError("simulated connection reset"),
    )
    with pytest.raises(ForgejoError, match="transport"):
        _client(token="t").delete_oauth_app(42)


def test_delete_oauth_app_rejects_invalid_id() -> None:
    with pytest.raises(ForgejoError, match="invalid app_id"):
        _client(token="t").delete_oauth_app(0)
    with pytest.raises(ForgejoError, match="invalid app_id"):
        _client(token="t").delete_oauth_app(-1)


@responses.activate
def test_create_oauth_app_returns_credentials_on_201() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={
            "id": 1,
            "name": "Woodpecker CI",
            "client_id": "client-123",
            "client_secret": "secret-456",
        },
    )
    result = _client(token="t").create_oauth_app(
        "Woodpecker CI", ["https://woodpecker.example.com/authorize"]
    )
    assert result.name == "Woodpecker CI"
    assert result.client_id == "client-123"
    assert result.client_secret == "secret-456"


@responses.activate
def test_create_oauth_app_raises_on_missing_client_id() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_secret": "secret-456"},  # client_id missing
    )
    with pytest.raises(ForgejoError, match="client_id"):
        _client(token="t").create_oauth_app("Woodpecker CI", ["https://x"])


@responses.activate
def test_create_oauth_app_raises_on_missing_client_secret() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "client-123"},  # client_secret missing
    )
    with pytest.raises(ForgejoError, match="client_secret"):
        _client(token="t").create_oauth_app("Woodpecker CI", ["https://x"])


@responses.activate
def test_create_oauth_app_raises_on_4xx() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=422,
        json={"message": "redirect URIs invalid"},
    )
    with pytest.raises(ForgejoError, match="HTTP 422"):
        _client(token="t").create_oauth_app("Woodpecker CI", ["not-a-url"])


@responses.activate
def test_create_oauth_app_sends_full_body() -> None:
    """Verifies the POST body shape includes name + redirect_uris + confidential."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "c", "client_secret": "s"},
    )
    _client(token="t").create_oauth_app(
        "Woodpecker CI",
        ["https://woodpecker.foo.com/authorize"],
        confidential_client=True,
    )
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body == {
        "name": "Woodpecker CI",
        "redirect_uris": ["https://woodpecker.foo.com/authorize"],
        "confidential_client": True,
    }


# ---------------------------------------------------------------------------
# run_woodpecker_oauth_setup orchestrator
# ---------------------------------------------------------------------------


@responses.activate
def test_woodpecker_oauth_happy_path_creates_fresh_app() -> None:
    """No existing apps → POST creates new → returns OAuthAppResult."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[],
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "fresh-id", "client_secret": "fresh-secret"},
    )
    result, err, _rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert err == ""
    assert result is not None
    assert result.client_id == "fresh-id"
    assert result.client_secret == "fresh-secret"


@responses.activate
def test_woodpecker_oauth_idempotent_deletes_existing_then_creates() -> None:
    """Existing "Woodpecker CI" → DELETE → fresh POST → fresh secret.

    Critical because Forgejo has no rotate-secret API: re-deploying
    must surface a NEW client_secret (the old one is likely stale
    in Woodpecker's persisted state) by deleting + recreating.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[
            {"id": 1, "name": "other-app"},
            {"id": 42, "name": "Woodpecker CI"},
        ],
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=204,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "new-id", "client_secret": "new-secret"},
    )
    result, err, _rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert err == ""
    assert result is not None
    assert result.client_id == "new-id"
    # Verify the call sequence: GET → DELETE → POST
    assert [c.request.method for c in responses.calls] == ["GET", "DELETE", "POST"]


@responses.activate
@responses.activate
def test_woodpecker_oauth_rotation_started_when_create_fails_after_delete() -> None:
    """Half-complete rotation: existing app deleted, create then fails.

    The orchestrator must signal ``rotation_started=True`` so the CLI
    handler can route to rc=2 (abort) instead of rc=1 (warn). Without
    this distinction, the caller would warn-and-continue with stale
    creds in Woodpecker's .env while Forgejo has already invalidated
    the live OAuth pair — login outage. (Copilot R2)
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": 42, "name": "Woodpecker CI"}],
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=204,  # delete OK
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=503,  # create fails AFTER delete
    )
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "create_oauth_app" in err
    assert rotation_started is True


@responses.activate
def test_woodpecker_oauth_no_rotation_when_list_fails() -> None:
    """list_oauth_apps fails → no delete attempted → rotation_started=False.

    Pairs with the test above: the False signal lets the CLI handler
    safely warn-and-continue (Forgejo state untouched, Woodpecker keeps
    running with the previous spin-up's still-valid credentials).
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=503,
    )
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "list_oauth_apps" in err
    assert rotation_started is False


@responses.activate
def test_woodpecker_oauth_no_rotation_when_create_fails_with_no_existing_app() -> None:
    """No existing "Woodpecker CI" → no delete → create fails.

    First-deploy edge case: list returns empty (or no Woodpecker CI
    entry), create fails. Nothing was rotated — safe to warn.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": 1, "name": "other-app"}],
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=503,
    )
    _, _, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert rotation_started is False


@responses.activate
def test_list_oauth_apps_raises_on_non_array_shape() -> None:
    """200 with object body must raise (not silently coerce to []).

    Without this, an intermediate proxy returning an error envelope
    (or a Forgejo schema change) would skip the rotation-delete and
    let the create pile up duplicate apps. (Copilot R2)
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json={"error": "not actually an array"},
    )
    with pytest.raises(ForgejoError, match="not a JSON array"):
        _client(token="t").list_oauth_apps()


@responses.activate
def test_woodpecker_oauth_aborts_on_delete_transport_error() -> None:
    """Connection reset / timeout during DELETE → server state ambiguous
    → conservatively mark rotation_started=True so CLI exits rc=2.

    Copilot R3 finding: when ``requests`` raises ConnectionError or
    Timeout on the DELETE, Forgejo may have actually processed the
    request before the response was lost. Treating the transport
    error as a pre-rotation failure (rotation_started=False, rc=1)
    would let the caller continue with a possibly-invalidated
    OAuth pair active in Woodpecker's .env.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": 42, "name": "Woodpecker CI"}],
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        body=requests.ConnectionError("simulated connection reset"),
    )
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    # Round-4 refinement: transport-error path now uses different
    # diagnostic wording from the definitive-403 path.
    assert "transport" in err
    assert "ambiguous" in err
    assert rotation_started is True


@responses.activate
def test_woodpecker_oauth_aborts_on_non_integer_id() -> None:
    """Defensive: list entry with name='Woodpecker CI' but a non-int
    id (None, string, etc.) must abort instead of silently skipping
    the delete and proceeding to create — that would produce a
    duplicate.

    Copilot R6: very narrow defensive check (Forgejo API contract
    guarantees integer ids), but keeps the rotation invariant
    intact under malformed-list-entry conditions.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": "not-an-int", "name": "Woodpecker CI"}],
    )
    # No DELETE or POST mock — neither must be issued.
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "non-integer id" in err
    assert "rotation NOT started" in err
    assert rotation_started is False
    # Only the GET happened; no DELETE / POST issued.
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


@responses.activate
def test_delete_oauth_app_5xx_raises_as_ambiguous() -> None:
    """5xx response: server-side failure that may have happened
    after the DELETE was applied → server state UNKNOWN → raise.

    Copilot R5: previously 5xx was bucketed with 4xx as "definitive
    non-success", which silently treated a server-side error
    occurring AFTER the DELETE was applied as 'rotation NOT
    started'. That would leave Woodpecker on Forgejo-invalidated
    creds. 5xx now raises ForgejoError with 'state ambiguous'.
    """
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=503,
    )
    with pytest.raises(ForgejoError, match="state ambiguous"):
        _client(token="t").delete_oauth_app(42)


@responses.activate
def test_woodpecker_oauth_preserves_rotation_state_across_loop_iterations() -> None:
    """Multi-app loop: first delete succeeds, second delete rejected →
    rotation_started must remain True (the first delete already
    happened; if we returned False the CLI would warn-and-continue
    while Forgejo has already invalidated the prior app's creds).

    Copilot R5: the False-return path used to discard the
    accumulated loop progress unconditionally.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[
            {"id": 1, "name": "Woodpecker CI"},
            {"id": 2, "name": "Woodpecker CI"},
        ],
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/1",
        status=204,  # first delete succeeds
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/2",
        status=403,  # second delete rejected
    )
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "rejected by Forgejo" in err
    # Critical: rotation_started must be True because the first
    # delete already invalidated app id=1's creds.
    assert rotation_started is True
    # And the diagnostic should reflect the partial state.
    assert "partially started" in err


def test_cli_woodpecker_oauth_surfaces_forgejo_error_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ForgejoError from path-safety violation must surface verbatim,
    not get collapsed to 'unexpected error (ForgejoError)'.

    Copilot R5: the catch-all `except Exception` previously hid
    the actionable 'unsafe admin_username: ...' detail.
    """
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    monkeypatch.setenv("ADMIN_USERNAME", "admin;rm -rf /")
    _setup_fake_ssh(monkeypatch)

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 2
    err = capsys.readouterr().err
    # Actionable detail visible — not 'unexpected error (ForgejoError)'
    assert "unsafe admin_username" in err
    assert "unexpected error" not in err


@responses.activate
def test_woodpecker_oauth_aborts_on_definitive_delete_rejection() -> None:
    """Definitive 403/5xx delete rejection: rotation_started=False
    (Forgejo KNOWS the app still exists), but still aborts the create
    to avoid duplicates.

    Copilot R4 refinement: distinguishes a definitive 403 (server
    state known: app still alive) from a transport timeout (server
    state unknown). The 403 path returns rotation_started=False so
    the caller can warn-and-continue with the existing OAuth pair
    (still consistent with Forgejo since the delete didn't run); the
    timeout path returns rotation_started=True forcing rc=2 abort.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[{"id": 42, "name": "Woodpecker CI"}],
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/user/applications/oauth2/42",
        status=403,  # operator revoked admin's permission, e.g.
    )
    # No POST mock — must NOT be called.
    result, err, rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "rejected by Forgejo" in err
    assert "rotation NOT started" in err
    # Definitive 403 → server state KNOWN → rotation NOT started
    # → CLI rc=1 (warn-and-continue): existing .env + Forgejo state
    # are still in sync.
    assert rotation_started is False
    # POST must NOT have been issued
    assert all(c.request.method != "POST" for c in responses.calls)


@responses.activate
def test_woodpecker_oauth_redirect_uri_built_from_domain() -> None:
    """The redirect URI must be `https://woodpecker.<domain>/authorize`."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[],
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "c", "client_secret": "s"},
    )
    run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="nexus-stack.ch",
        forgejo_token="tok",
        admin_username="admin",
    )
    body = json.loads(responses.calls[1].request.body)  # type: ignore[arg-type]
    assert body["redirect_uris"] == ["https://woodpecker.nexus-stack.ch/authorize"]


@responses.activate
def test_woodpecker_oauth_returns_diagnostic_on_list_failure() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=503,
    )
    result, err, _rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "list_oauth_apps" in err
    assert "503" in err


@responses.activate
def test_woodpecker_oauth_returns_diagnostic_on_create_failure() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[],
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=422,
    )
    result, err, _rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert result is None
    assert "create_oauth_app" in err


def test_woodpecker_oauth_rejects_empty_token() -> None:
    """Empty FORGEJO_TOKEN → no API call, return diagnostic immediately."""
    result, err, _rotation_started = run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="",
        admin_username="admin",
    )
    assert result is None
    assert "FORGEJO_TOKEN is empty" in err


def test_woodpecker_oauth_rejects_unsafe_admin_username() -> None:
    """Path-safety on admin_username (defence in depth)."""
    with pytest.raises(ForgejoError, match="unsafe"):
        run_woodpecker_oauth_setup(
            base_url=BASE_URL,
            domain="example.com",
            forgejo_token="tok",
            admin_username="admin;rm -rf /",
        )


@responses.activate
def test_woodpecker_oauth_token_in_authorization_header_not_argv() -> None:
    """R7 — token bearer auth lives in Authorization header only."""
    secret_token = "do-not-leak-this-token"
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=200,
        json=[],
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        status=201,
        json={"client_id": "c", "client_secret": "s"},
    )
    run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token=secret_token,
        admin_username="admin",
    )
    for call in responses.calls:
        # Token must NOT be in URL or body
        assert secret_token not in (call.request.url or "")
        body = call.request.body or b""
        body_text = body.decode("utf-8") if isinstance(body, bytes) else body
        assert secret_token not in body_text
        # Token IS in the Authorization header in `token <sha>` form
        assert call.request.headers.get("Authorization") == f"token {secret_token}"


# ---------------------------------------------------------------------------
# CLI handler for `forgejo woodpecker-oauth`
# ---------------------------------------------------------------------------


def test_cli_woodpecker_oauth_unknown_args_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_woodpecker_oauth_missing_env_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DOMAIN", raising=False)
    monkeypatch.delenv("FORGEJO_TOKEN", raising=False)
    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DOMAIN" in err
    assert "FORGEJO_TOKEN" in err


def _setup_fake_ssh(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake_ssh = MagicMock()
    fake_ssh.__enter__ = MagicMock(return_value=fake_ssh)
    fake_ssh.__exit__ = MagicMock(return_value=None)
    fake_pf = MagicMock()
    fake_pf.__enter__ = MagicMock(return_value=12345)
    fake_pf.__exit__ = MagicMock(return_value=None)
    fake_ssh.port_forward = MagicMock(return_value=fake_pf)
    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda host: fake_ssh)
    return fake_ssh


def test_cli_woodpecker_oauth_emits_eval_able_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    _setup_fake_ssh(monkeypatch)

    fake_result = OAuthAppResult(
        name="Woodpecker CI", client_id="client-abc", client_secret="secret-xyz"
    )
    monkeypatch.setattr(
        "nexus_deploy.__main__.run_woodpecker_oauth_setup",
        lambda **kwargs: (fake_result, "", True),
    )

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WOODPECKER_FORGEJO_CLIENT=client-abc" in out
    assert "WOODPECKER_FORGEJO_SECRET=secret-xyz" in out


def test_cli_woodpecker_oauth_returns_rc_1_on_failure_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    _setup_fake_ssh(monkeypatch)

    monkeypatch.setattr(
        "nexus_deploy.__main__.run_woodpecker_oauth_setup",
        lambda **kwargs: (None, "list_oauth_apps: HTTP 503", False),
    )

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 1
    captured = capsys.readouterr()
    # No eval-able stdout on failure — the caller's existing .env values
    # stay untouched.
    assert "WOODPECKER_FORGEJO_CLIENT" not in captured.out
    assert "WOODPECKER_FORGEJO_SECRET" not in captured.out
    # Diagnostic on stderr
    assert "NOT created" in captured.err
    assert "list_oauth_apps: HTTP 503" in captured.err
    # No rotation half-complete warning (rotation_started=False)
    assert "rotation half-complete" not in captured.err


def test_cli_woodpecker_oauth_returns_rc_2_on_rotation_half_complete(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rotation started + create failed → rc=2 (abort), with diagnostic.

    the caller treats rc=2 as red-abort; rc=1 as yellow-warn-continue.
    A half-complete rotation (Forgejo has invalidated the old creds,
    Python couldn't issue new ones) MUST abort or Woodpecker keeps
    running with stale creds and 401s on every login. (Copilot R2)
    """
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    _setup_fake_ssh(monkeypatch)

    monkeypatch.setattr(
        "nexus_deploy.__main__.run_woodpecker_oauth_setup",
        lambda **kwargs: (None, "create_oauth_app: HTTP 503", True),  # rotation_started=True
    )

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "NOT created" in err
    assert "rotation half-complete" in err
    assert "Woodpecker login outage" in err


def test_cli_woodpecker_oauth_eval_handoff_safe_with_shell_meta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pin the shlex.quote contract: client_id/secret containing shell
    metacharacters must be safely quoted in stdout so the caller's
    ``eval`` doesn't execute them. Without shlex.quote a value like
    ``foo;rm -rf /`` would run a command on eval. (Copilot R2)

    Today Forgejo always returns hex-only OAuth values, but a future
    Forgejo version (or a forked deployment with different ID rules)
    could surface arbitrary strings — the shlex.quote layer is the
    contract that survives those.
    """
    import subprocess

    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    _setup_fake_ssh(monkeypatch)

    # Adversarial values: every shell-metachar that would break out
    # of an unquoted assignment.
    adversarial_id = "id;echo PWNED-id"
    adversarial_secret = "secret$(touch /tmp/pwned)"

    fake_result = OAuthAppResult(
        name="Woodpecker CI",
        client_id=adversarial_id,
        client_secret=adversarial_secret,
    )
    monkeypatch.setattr(
        "nexus_deploy.__main__.run_woodpecker_oauth_setup",
        lambda **kwargs: (fake_result, "", True),
    )

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 0
    out = capsys.readouterr().out

    # Pin: bash -c "eval $stdout" must NOT execute the embedded
    # commands. We assert the post-eval values match the originals.
    bash_script = (
        f"{out}\n"
        'printf "%s\\n" "$WOODPECKER_FORGEJO_CLIENT"\n'
        'printf "%s\\n" "$WOODPECKER_FORGEJO_SECRET"\n'
    )
    result = subprocess.run(
        ["bash", "-c", bash_script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == adversarial_id
    assert lines[1] == adversarial_secret
    # And critically: nothing got executed. If the eval had parsed
    # the values as commands, the embedded ``;echo PWNED-id`` would
    # have produced an extra stdout line of its own (the output of
    # the ``echo`` command) BEFORE our printf lines. With shlex.quote,
    # the assignments are atomic and only our two printf lines
    # appear — exactly 2 lines total. (Round-3 fix: the previous form
    # ``"PWNED-id" not in result.stdout`` was wrong because the
    # literal data byte-string contains "PWNED-id" verbatim. The
    # length check distinguishes data round-trip from command
    # execution. The earlier ``... if False else True`` was a
    # no-op assertion — Copilot caught the typo.)
    assert len(lines) == 2
    # The ID line should be the literal adversarial_id, NOT "id"
    # alone (which is what `id;echo PWNED-id` would produce on
    # unquoted eval).
    assert lines[0] != "id"


def test_cli_woodpecker_oauth_ssh_tunnel_failure_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")

    from nexus_deploy.ssh import SSHError

    class _BoomSSH:
        def __init__(self, _host: str) -> None: ...
        def __enter__(self) -> _BoomSSH:
            return self

        def __exit__(self, *_: Any) -> None: ...
        def port_forward(self, *_a: Any, **_k: Any) -> Any:
            raise SSHError("ssh tunnel boom")

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _BoomSSH)

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "ssh tunnel" in captured.err
    assert "WOODPECKER_FORGEJO_CLIENT" not in captured.out


def test_cli_woodpecker_oauth_unexpected_exception_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "tok")
    _setup_fake_ssh(monkeypatch)

    secret_in_msg = "secret-in-exception-XYZZY"

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError(secret_in_msg)

    monkeypatch.setattr("nexus_deploy.__main__.run_woodpecker_oauth_setup", boom)

    from nexus_deploy.__main__ import _forgejo_woodpecker_oauth

    rc = _forgejo_woodpecker_oauth([])
    assert rc == 2
    err = capsys.readouterr().err
    # Type name only — message body MUST NOT leak.
    assert "RuntimeError" in err
    assert secret_in_msg not in err


# ---------------------------------------------------------------------------
# Mirror-mode helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo.git", "repo"),
        ("https://github.com/owner/repo", "repo"),
        ("https://github.com/owner/Bsc_EDS_GIS_FS2026.git", "Bsc_EDS_GIS_FS2026"),
        ("https://forgejo.foo.com/o/r.git/", "r"),  # trailing slash stripped
    ],
)
def test_basename_no_git(url: str, expected: str) -> None:
    assert _basename_no_git(url) == expected


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ("admin", "admin"),
        ("stefan.koch", "stefan_koch"),
        ("user-with-dash", "user_with_dash"),
        ("user.with.dots-and-dashes", "user_with_dots_and_dashes"),
        ("UPPER_lower", "UPPER_lower"),  # underscore is alphanumeric-safe-ish in regex
    ],
)
def test_sanitize_user_for_fork_name(user: str, expected: str) -> None:
    assert _sanitize_user_for_fork_name(user) == expected


# ---------------------------------------------------------------------------
# ForgejoClient mirror REST methods
# ---------------------------------------------------------------------------


@responses.activate
def test_get_user_id_returns_int_on_200() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 42, "login": "admin"},
    )
    assert _client(token="t").get_user_id("admin") == 42


@responses.activate
def test_get_user_id_returns_none_on_404() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=404)
    assert _client(token="t").get_user_id("admin") is None


@responses.activate
def test_get_user_id_raises_on_5xx() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=500)
    with pytest.raises(ForgejoError, match="HTTP 500"):
        _client(token="t").get_user_id("admin")


@responses.activate
def test_get_user_id_raises_on_200_with_missing_id() -> None:
    """200 + payload without integer 'id' (proxy mangling, schema
    drift) must raise — NOT silently return None. Without this, the
    caller would treat it as a genuine 404 and the CLI would print
    the misleading 'admin user not found in Forgejo'. (Copilot R5)
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"login": "admin"},  # id missing
    )
    with pytest.raises(ForgejoError, match="missing integer 'id'"):
        _client(token="t").get_user_id("admin")


@responses.activate
def test_get_user_id_raises_on_200_with_non_int_id() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": "not-an-int", "login": "admin"},
    )
    with pytest.raises(ForgejoError, match="missing integer 'id'"):
        _client(token="t").get_user_id("admin")


@responses.activate
def test_migrate_mirror_returns_created_on_201() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10, "name": "mirror-readonly-x"},
    )
    result = _client(token="t").migrate_mirror(
        "mirror-readonly-x", "https://github.com/o/x.git", 1, "ghp_xxx"
    )
    assert result.status == "created"
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body["clone_addr"] == "https://github.com/o/x.git"
    assert body["repo_name"] == "mirror-readonly-x"
    assert body["mirror"] is True
    assert body["mirror_interval"] == "10m0s"
    assert body["uid"] == 1
    # GitHub PAT travels in body, never in URL/headers
    assert body["auth_token"] == "ghp_xxx"
    assert "ghp_xxx" not in (responses.calls[0].request.url or "")


@responses.activate
def test_migrate_mirror_409_returns_already_exists() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/repos/migrate", status=409)
    result = _client(token="t").migrate_mirror("mirror-readonly-x", "https://x.git", 1, "ghp")
    assert result.status == "already_exists"


@responses.activate
def test_migrate_mirror_422_already_exists_returns_already_exists() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=422,
        json={"message": "repository already exists"},
    )
    result = _client(token="t").migrate_mirror("mirror-readonly-x", "https://x.git", 1, "ghp")
    assert result.status == "already_exists"


@responses.activate
def test_migrate_mirror_5xx_returns_failed() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/repos/migrate", status=503)
    result = _client(token="t").migrate_mirror("mirror-readonly-x", "https://x.git", 1, "ghp")
    assert result.status == "failed"
    assert "503" in result.detail


@responses.activate
def test_trigger_mirror_sync_200_returns_true() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-x/mirror-sync",
        status=200,
    )
    assert _client(token="t").trigger_mirror_sync("admin", "mirror-readonly-x")


@responses.activate
def test_trigger_mirror_sync_returns_false_on_non_200() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-x/mirror-sync",
        status=403,
    )
    assert not _client(token="t").trigger_mirror_sync("admin", "mirror-readonly-x")


@responses.activate
def test_merge_upstream_returns_status_string() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/user/fork/merge-upstream",
        status=200,
    )
    rc = _client(token="t").merge_upstream("user", "fork", "main")
    assert rc == "200"
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body == {"branch": "main"}


@responses.activate
def test_merge_upstream_409_already_up_to_date() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/user/fork/merge-upstream",
        status=409,
    )
    assert _client(token="t").merge_upstream("user", "fork", "main") == "409"


@responses.activate
def test_merge_upstream_handles_non_main_branch() -> None:
    """merge-upstream supports any branch — `master`-default upstreams
    were broken when the caller hardcoded `main`. Verify the body
    branch is whatever caller passes.
    """
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/user/fork/merge-upstream",
        status=200,
    )
    _client(token="t").merge_upstream("user", "fork", "master")
    body = json.loads(responses.calls[0].request.body)  # type: ignore[arg-type]
    assert body["branch"] == "master"


@responses.activate
def test_create_user_token_uses_basic_auth_not_bearer() -> None:
    """Admin creating a token on behalf of a user MUST use basic-auth.

    Token-bearer auth would only let admin act on its own user
    (Forgejo constraint). Regression test pins this contract: the
    request must carry an Authorization: Basic ... header, not
    a token header.
    """
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "abc-user-token"},
    )
    sha1 = _client().create_user_token(
        "stefan",
        "nexus-workspace-fork",
        ["all"],
        admin_username="admin",
        admin_password="admin-pw",
    )
    assert sha1 == "abc-user-token"
    auth_header = responses.calls[0].request.headers.get("Authorization", "")
    assert auth_header.startswith("Basic ")
    # NOT a token-bearer
    assert not auth_header.startswith("token ")


@responses.activate
def test_create_user_token_retries_via_delete_on_first_failure() -> None:
    """On first 4xx (token name conflict), delete + retry once."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=409,
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "fresh-token"},
    )
    sha1 = _client().create_user_token(
        "stefan",
        "nexus-workspace-fork",
        ["all"],
        admin_username="admin",
        admin_password="admin-pw",
    )
    assert sha1 == "fresh-token"
    assert [c.request.method for c in responses.calls] == ["POST", "DELETE", "POST"]


@responses.activate
def test_create_user_token_returns_none_on_persistent_failure() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    sha1 = _client().create_user_token(
        "stefan",
        "nexus-workspace-fork",
        ["all"],
        admin_username="admin",
        admin_password="admin-pw",
    )
    assert sha1 is None


@responses.activate
def test_fork_repo_as_user_uses_user_token_not_admin_token() -> None:
    """Fork POST must use the USER's bearer token so the fork lands in
    the user's namespace, not admin's. Regression test pins the auth.
    """
    user_token = "user-bearer-do-not-leak"
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-x/forks",
        status=202,
    )
    rc = _client(token="ADMIN-TOKEN-WRONG").fork_repo_as_user(
        "admin", "mirror-readonly-x", "x_stefan", user_token=user_token
    )
    assert rc == "202"
    auth = responses.calls[0].request.headers.get("Authorization", "")
    # User token in header, NOT admin token
    assert auth == f"token {user_token}"
    assert "ADMIN-TOKEN-WRONG" not in auth


# ---------------------------------------------------------------------------
# run_mirror_setup orchestrator
# ---------------------------------------------------------------------------


@responses.activate
def test_run_mirror_setup_happy_path_with_user() -> None:
    """One mirror, one user → mirror created, fork created, collab added,
    fork synced via mirror-sync + merge-upstream.
    """
    # admin UID lookup
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    # Idempotent existence check (mirror does not exist yet)
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo",
        status=404,
    )
    # migrate POST
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10},
    )
    # user-token mint (basic-auth)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    # fork POST (user's bearer)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
    )
    # cleanup user-token
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    # collaborator add
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # mirror-sync
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    # merge-upstream (fork)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=200,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,  # don't poll in tests
    )
    assert result.is_success is True
    assert result.admin_uid == 1
    assert len(result.mirrors) == 1
    assert result.mirrors[0].status == "created"
    assert result.fork is not None
    assert result.fork.owner == "stefan"
    assert result.fork.name == "myrepo_stefan"
    assert result.fork.status == "created"
    assert result.collaborator_added_count == 1
    assert result.fork_synced is True


@responses.activate
def test_run_mirror_setup_sync_detail_landed() -> None:
    """When the mirror HEAD changes during the polling window, the
    sync_detail surfaces the SHA transition and that merge_upstream
    was called — this is the new diagnostic that makes 'why didn't
    the fork pick up upstream commits' observable in PhaseResult."""
    # Admin UID + mirror migrate
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    responses.add(
        responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo", status=404
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 42, "name": "mirror-readonly-myrepo"},
    )
    # User-token + fork
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
        json={"id": 99},
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # First branch-HEAD lookup (before sync): old SHA.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=200,
        json={"commit": {"id": "old1234567890abcdef"}},
    )
    # trigger_mirror_sync → 200
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    # Second branch-HEAD lookup (poll iteration 1): NEW SHA — sync landed.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=200,
        json={"commit": {"id": "new9876543210fedcba"}},
    )
    # merge_upstream → 200
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=200,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="main",
        # 30s poll budget is fine — the loop returns on first successful
        # SHA-change observation, not the full 30s.
        mirror_sync_poll_seconds=30.0,
        mirror_sync_poll_interval_seconds=0.0,
    )
    assert result.fork_synced is True
    assert "mirror synced" in result.sync_detail
    assert "old12345" in result.sync_detail
    assert "new98765" in result.sync_detail
    assert "merge_upstream=200" in result.sync_detail


@responses.activate
def test_run_mirror_setup_sync_detail_unchanged() -> None:
    """When the mirror HEAD doesn't move within the poll window
    (upstream genuinely unchanged, OR Forgejo's fetch wedged), the
    detail says so + still calls merge_upstream so the operator
    sees the 409 'already up to date' case explicitly."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    responses.add(
        responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo", status=404
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 42},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
        json={"id": 99},
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # branch HEAD never changes across all poll iterations.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=200,
        json={"commit": {"id": "stable000000000abc"}},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=409,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="main",
        # Tiny budget so the test doesn't actually wait — guaranteed
        # to expire after one no-change observation.
        mirror_sync_poll_seconds=0.1,
        mirror_sync_poll_interval_seconds=0.0,
    )
    assert "mirror HEAD unchanged" in result.sync_detail
    assert "merge_upstream=409" in result.sync_detail


@responses.activate
def test_run_mirror_setup_sync_lands_even_when_pre_snapshot_failed() -> None:
    """Edge case (PR #589 review): if the pre-sync HEAD lookup returns
    None (transient 404 / transport), but the polling loop later
    observes a real after_sha, we should still call merge_upstream —
    a transient pre-snapshot failure shouldn't leave the fork stale
    when the mirror actually did update."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo",
        status=404,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 42},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
        json={"id": 99},
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # Pre-sync HEAD lookup: 404 -> before_sha=None.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=404,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    # Poll iteration: HEAD resolvable now -> after_sha != None != before_sha
    # -> landed=True. Must still call merge_upstream.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=200,
        json={"commit": {"id": "actuallyhere1234567"}},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=200,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="main",
        mirror_sync_poll_seconds=30.0,
        mirror_sync_poll_interval_seconds=0.0,
    )
    assert "mirror synced" in result.sync_detail
    assert "unknown" in result.sync_detail
    assert "actually" in result.sync_detail
    assert "merge_upstream=200" in result.sync_detail


@responses.activate
def test_run_mirror_setup_sync_branch_with_slash_does_not_raise() -> None:
    """Regression (PR #589 review): get_branch_head_sha must accept
    branch names containing '/' (e.g. 'feat/foo'). Previously
    _validate_path_segment rejected them before the GET was sent,
    raising ForgejoError. Fix: URL-encode the branch segment."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo",
        status=404,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 42},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
        json={"id": 99},
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # URL-encoded branch in the GET path: 'feat/foo' -> 'feat%2Ffoo'.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/feat%2Ffoo",
        status=200,
        json={"commit": {"id": "samesha000000abcdef"}},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=409,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="feat/foo",
        mirror_sync_poll_seconds=0.1,
        mirror_sync_poll_interval_seconds=0.0,
    )
    # No ForgejoError raised => success. Sync didn't land (same SHA),
    # but the slash-branch didn't blow up.
    assert result.is_success is True
    assert "mirror HEAD unchanged" in result.sync_detail


@responses.activate
def test_run_mirror_setup_idempotent_skips_existing_mirror() -> None:
    """Mirror already exists → skip migrate, still do fork+collab+sync."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    # existence check returns 200 — skip migrate
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=409,  # fork already exists too
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=409,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert result.is_success is True
    assert result.mirrors[0].status == "already_exists"
    assert result.fork is not None
    assert result.fork.status == "already_exists"
    # POST migrate must NOT have been issued (idempotent skip).
    assert all(c.request.url != f"{BASE_URL}/api/v1/repos/migrate" for c in responses.calls)


@responses.activate
def test_run_mirror_setup_trigger_fail_still_attempts_merge_upstream() -> None:
    """Regression (PR #589 review round 2): when trigger_mirror_sync
    returns non-200 (e.g. token rejected, repo state), the orchestrator
    must STILL attempt merge_upstream — the mirror may already be ahead
    of the fork from Forgejo's periodic cron-tick or from the initial
    migrate that ran a few seconds ago. Skipping merge would regress
    the legacy bash's best-effort behavior."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo",
        status=404,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 42},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/forks",
        status=202,
        json={"id": 99},
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/collaborators/stefan",
        status=204,
    )
    # Pre-sync HEAD lookup (doesn't matter for this test, returns 200).
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/branches/main",
        status=200,
        json={"commit": {"id": "anysha000000000000"}},
    )
    # trigger_mirror_sync FAILS (e.g. 403 because GH_MIRROR_TOKEN lost
    # access to the upstream repo).
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-myrepo/mirror-sync",
        status=403,
    )
    # merge_upstream MUST still be called against the current mirror HEAD.
    # The mirror could already be ahead from the periodic cron-tick or the
    # initial migrate's fetch; merge_upstream surfaces that with 200.
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream",
        status=200,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/myrepo.git"],
        gh_mirror_token="ghp_xxx",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    # sync_detail must record both the trigger-failure AND the merge attempt.
    assert "trigger_mirror_sync returned non-200" in result.sync_detail
    assert "merge_upstream against current mirror HEAD: 200" in result.sync_detail
    # merge_upstream actually got hit.
    assert any(
        c.request.url == f"{BASE_URL}/api/v1/repos/stefan/myrepo_stefan/merge-upstream"
        for c in responses.calls
    )


@responses.activate
def test_run_mirror_setup_no_user_skips_fork() -> None:
    """forgejo_user_username=None → mirror+collab branches skipped where
    user-dependent. fork=None.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-x",
        status=404,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10},
    )
    # No fork mocks, no collab mock — should not be called.

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username=None,
        gh_mirror_repos=["https://github.com/o/x.git"],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert result.is_success is True
    assert result.fork is None
    assert result.collaborator_added_count == 0
    assert result.fork_synced is False


@responses.activate
def test_run_mirror_setup_returns_no_admin_uid_early() -> None:
    """Admin UID lookup 404 → return early with admin_uid=None and
    is_success=False (CLI rc=1).
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=404)
    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/x.git"],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert result.admin_uid is None
    assert result.mirrors == ()
    assert result.fork is None
    assert result.is_success is False


@responses.activate
def test_run_mirror_setup_fork_only_first_iteration() -> None:
    """Multi-mirror: fork only happens on the first successful mirror
    even when later iterations also succeed (matches the legacy
    FORKED_WORKSPACE flag scoped to first iteration).
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    # Two mirrors, both new
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1", status=404)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "tok"},
    )
    # Fork the FIRST one
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1/forks",
        status=202,
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    # First-iteration collab + sync
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1/collaborators/stefan",
        status=204,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1/mirror-sync",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/r1_stefan/merge-upstream",
        status=200,
    )
    # Second iteration: mirror still gets created + collab, but no fork
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2", status=404)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 11},
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2/collaborators/stefan",
        status=204,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=[
            "https://github.com/o/r1.git",
            "https://github.com/o/r2.git",
        ],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert result.is_success is True
    assert len(result.mirrors) == 2
    assert all(m.status == "created" for m in result.mirrors)
    # Only ONE fork (from the first mirror)
    assert result.fork is not None
    assert result.fork.name == "r1_stefan"
    # Both mirrors got the collaborator
    assert result.collaborator_added_count == 2
    # No fork POST against r2
    fork_calls = [c for c in responses.calls if "/forks" in (c.request.url or "")]
    assert len(fork_calls) == 1
    assert "mirror-readonly-r1" in (fork_calls[0].request.url or "")


@responses.activate
def test_run_mirror_setup_fork_retries_on_next_iteration_after_transient_failure() -> None:
    """Multi-mirror loop: first fork attempt fails (transient
    user-token mint glitch), second iteration retries the fork
    against the next mirror and succeeds. Final result shows the
    successful fork — not the earlier transient failure.

    Mirrors the legacy bash's FORKED_WORKSPACE flag semantics:
    only set on HTTP 202/409 success, so failure leaves the flag
    unset and later iterations get another attempt. (Copilot R3)
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    # First mirror: created OK
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1", status=404)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/repos/migrate", status=201, json={"id": 10})
    # First user-token mint: persistent failure (initial + delete + retry)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    # First-iteration collab still happens
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r1/collaborators/stefan",
        status=204,
    )
    # Second mirror: created OK
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2", status=404)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/repos/migrate", status=201, json={"id": 11})
    # Second iteration: user-token mint succeeds this time
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/users/stefan/tokens",
        status=201,
        json={"sha1": "user-tok"},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2/forks",
        status=202,
    )
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2/collaborators/stefan",
        status=204,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r2/mirror-sync",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/stefan/r2_stefan/merge-upstream",
        status=200,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=[
            "https://github.com/o/r1.git",
            "https://github.com/o/r2.git",
        ],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    # Final fork is the SECOND mirror's successful fork, NOT the
    # first iteration's transient failure.
    assert result.fork is not None
    assert result.fork.status == "created"
    assert result.fork.name == "r2_stefan"
    assert result.is_success is True
    assert result.collaborator_added_count == 2


@responses.activate
def test_run_mirror_setup_surfaces_last_fork_failure_when_every_attempt_fails() -> None:
    """Multi-mirror loop where every fork attempt fails — final
    result surfaces the LAST attempt's diagnostic in
    ``fork.status="failed"`` so the operator can debug. Without
    this, fork=None would be ambiguous with the no-user-configured
    branch. (Copilot R3)
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/users/admin", status=200, json={"id": 1})
    # Both mirrors create OK; both fork attempts fail (user-token
    # mint persistent fail).
    for repo in ("r1", "r2"):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-{repo}",
            status=404,
        )
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/v1/repos/migrate",
            status=201,
            json={"id": 10},
        )
        responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
        responses.add(
            responses.DELETE,
            f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
            status=204,
        )
        responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
        responses.add(
            responses.PUT,
            f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-{repo}/collaborators/stefan",
            status=204,
        )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=[
            "https://github.com/o/r1.git",
            "https://github.com/o/r2.git",
        ],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    # fork=last_fork_failure (the second iteration's attempt) so the
    # operator sees a diagnostic — not None.
    assert result.fork is not None
    assert result.fork.status == "failed"
    assert result.fork.name == "r2_stefan"
    assert "user token" in result.fork.detail
    assert result.is_success is False


@responses.activate
def test_run_mirror_setup_unsafe_basename_marks_failed_and_continues() -> None:
    """A repo URL whose basename contains shell-meta chars (e.g.
    ``?`` or ``;``) derives an unsafe ``mirror_name``. Without the
    pre-validation guard, ``_validate_path_segment`` inside
    ``repo_exists`` / ``migrate_mirror`` would raise ForgejoError out
    of the loop → CLI rc=2 (hard abort) — defeating the per-mirror
    failed-result intent. (Copilot R1)

    Now: bad mirror_name → MirrorResult(failed) + continue, the
    second mirror still gets processed.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    # Second mirror succeeds normally.
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-good", status=404)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/repos/migrate", status=201, json={"id": 10})

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username=None,
        gh_mirror_repos=[
            # Basename "repo?evil" contains '?' — unsafe in path
            # segment, must NOT propagate as a raised exception.
            "https://github.com/o/repo?evil.git",
            "https://github.com/o/good.git",
        ],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    # Loop did NOT abort — both URLs got processed.
    assert len(result.mirrors) == 2
    assert result.mirrors[0].status == "failed"
    assert "path validation" in result.mirrors[0].detail
    assert result.mirrors[1].status == "created"


@responses.activate
def test_run_mirror_setup_partial_failure_continues_loop() -> None:
    """One failed mirror in a multi-mirror loop doesn't abort —
    is_success becomes False but other mirrors still get processed.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    # First mirror fails
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-bad", status=404)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=503,
    )
    # Second mirror succeeds
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-good", status=404)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10},
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username=None,  # no fork to keep test focused
        gh_mirror_repos=[
            "https://github.com/o/bad.git",
            "https://github.com/o/good.git",
        ],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert len(result.mirrors) == 2
    assert result.mirrors[0].status == "failed"
    assert result.mirrors[1].status == "created"
    assert result.is_success is False  # because one mirror failed


@responses.activate
def test_run_mirror_setup_user_token_failure_marks_fork_failed() -> None:
    """user-token mint persistently fails → fork status='failed', no
    fork POST attempted.
    """
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/users/admin",
        status=200,
        json={"id": 1},
    )
    responses.add(responses.GET, f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r", status=404)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/repos/migrate",
        status=201,
        json={"id": 10},
    )
    # Both user-token POST attempts fail (initial + post-delete retry)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/api/v1/users/stefan/tokens/nexus-workspace-fork",
        status=204,
    )
    responses.add(responses.POST, f"{BASE_URL}/api/v1/users/stefan/tokens", status=500)
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/repos/admin/mirror-readonly-r/collaborators/stefan",
        status=204,
    )

    result = run_mirror_setup(
        base_url=BASE_URL,
        admin_username="admin",
        admin_password="admin-pw",
        forgejo_token="admin-tok",
        forgejo_user_username="stefan",
        gh_mirror_repos=["https://github.com/o/r.git"],
        gh_mirror_token="ghp",
        workspace_branch="main",
        mirror_sync_poll_seconds=0.0,
    )
    assert result.fork is not None
    assert result.fork.status == "failed"
    assert "user token" in result.fork.detail
    assert result.is_success is False
    # Collab still attempted
    assert result.collaborator_added_count == 1
    # No fork POST issued
    fork_calls = [c for c in responses.calls if "/forks" in (c.request.url or "")]
    assert len(fork_calls) == 0


# ---------------------------------------------------------------------------
# CLI handler for `forgejo mirror-setup`
# ---------------------------------------------------------------------------


def test_cli_mirror_setup_unknown_args_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_mirror_setup_missing_env_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mirrors-only mode (no FORGEJO_USER_USERNAME) → FORGEJO_ADMIN_PASS
    is NOT in the required list (Copilot R6). Only the unconditional
    three are required.
    """
    for var in (
        "FORGEJO_ADMIN_PASS",
        "FORGEJO_TOKEN",
        "GH_MIRROR_REPOS",
        "GH_MIRROR_TOKEN",
        "FORGEJO_USER_USERNAME",
    ):
        monkeypatch.delenv(var, raising=False)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "FORGEJO_TOKEN" in err
    assert "GH_MIRROR_REPOS" in err
    assert "GH_MIRROR_TOKEN" in err
    # Mirrors-only mode: FORGEJO_ADMIN_PASS is conditional, NOT in
    # the missing list when FORGEJO_USER_USERNAME is unset.
    assert "FORGEJO_ADMIN_PASS" not in err


def test_cli_mirror_setup_admin_pass_required_when_user_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fork mode (FORGEJO_USER_USERNAME set) → FORGEJO_ADMIN_PASS
    becomes required because the temp user-token mint inside the
    fork flow uses admin basic-auth. (Copilot R6)
    """
    monkeypatch.setenv("FORGEJO_USER_USERNAME", "stefan")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")
    monkeypatch.delenv("FORGEJO_ADMIN_PASS", raising=False)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "FORGEJO_ADMIN_PASS" in err
    assert "when FORGEJO_USER_USERNAME is set" in err


def test_cli_mirror_setup_empty_repos_csv_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", " , ,")  # only whitespace + commas
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 2
    assert "no repo URLs" in capsys.readouterr().err


def test_cli_mirror_setup_emits_fork_name_and_owner_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Happy path stdout: FORK_NAME=<name> + FORGEJO_REPO_OWNER=<user>
    eval-able. Required by the caller's seed_workspace_files post-eval.
    """
    from nexus_deploy.forgejo import ForkResult, MirrorSetupResult

    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")
    monkeypatch.setenv("FORGEJO_USER_USERNAME", "stefan")
    _setup_fake_ssh(monkeypatch)

    fake_result = MirrorSetupResult(
        admin_uid=42,
        admin_uid_error="",
        mirrors=(MirrorResult(name="m", status="created"),),
        fork=ForkResult(name="myrepo_stefan", owner="stefan", status="created"),
        collaborator_added_count=1,
        fork_synced=True,
    )
    monkeypatch.setattr("nexus_deploy.__main__.run_mirror_setup", lambda **kwargs: fake_result)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FORK_NAME='myrepo_stefan'" in out or "FORK_NAME=myrepo_stefan" in out
    assert "FORGEJO_REPO_OWNER='stefan'" in out or "FORGEJO_REPO_OWNER=stefan" in out


def test_cli_mirror_setup_omits_stdout_when_no_fork(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No fork (no user, or fork failed) → empty stdout. the caller's
    seed wrapper falls back to its existing $REPO_NAME / $FORGEJO_REPO_OWNER.
    """
    from nexus_deploy.forgejo import MirrorSetupResult

    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")
    monkeypatch.delenv("FORGEJO_USER_USERNAME", raising=False)
    _setup_fake_ssh(monkeypatch)

    fake_result = MirrorSetupResult(
        admin_uid=42,
        admin_uid_error="",
        mirrors=(MirrorResult(name="m", status="created"),),
        fork=None,
        collaborator_added_count=0,
        fork_synced=False,
    )
    monkeypatch.setattr("nexus_deploy.__main__.run_mirror_setup", lambda **kwargs: fake_result)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FORK_NAME" not in out
    assert "FORGEJO_REPO_OWNER" not in out


def test_cli_mirror_setup_admin_uid_none_404_returns_rc_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """admin user genuinely doesn't exist (404 → admin_uid=None,
    admin_uid_error="" empty) → rc=1 with "admin user not found".
    """
    from nexus_deploy.forgejo import MirrorSetupResult

    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")
    _setup_fake_ssh(monkeypatch)

    fake_result = MirrorSetupResult(
        admin_uid=None,
        admin_uid_error="",  # genuine 404
        mirrors=(),
        fork=None,
        collaborator_added_count=0,
        fork_synced=False,
    )
    monkeypatch.setattr("nexus_deploy.__main__.run_mirror_setup", lambda **kwargs: fake_result)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "admin user not found in Forgejo" in err
    # Must NOT use the misleading "lookup failed" wording reserved
    # for the auth/transport/5xx branch.
    assert "lookup failed" not in err


def test_cli_mirror_setup_admin_uid_lookup_failure_surfaces_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Auth/transport/5xx during get_user_id → admin_uid_error
    populated → CLI surfaces the real cause (e.g. "HTTP 503")
    instead of the misleading "user not found". (Copilot R4)
    """
    from nexus_deploy.forgejo import MirrorSetupResult

    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")
    _setup_fake_ssh(monkeypatch)

    fake_result = MirrorSetupResult(
        admin_uid=None,
        admin_uid_error="get_user_id HTTP 503",
        mirrors=(),
        fork=None,
        collaborator_added_count=0,
        fork_synced=False,
    )
    monkeypatch.setattr("nexus_deploy.__main__.run_mirror_setup", lambda **kwargs: fake_result)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "admin UID lookup failed" in err
    assert "HTTP 503" in err
    # Must NOT use the "user not found" wording reserved for the
    # genuine 404 branch.
    assert "not found in Forgejo" not in err


def test_cli_mirror_setup_ssh_tunnel_failure_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGEJO_ADMIN_PASS", "x")
    monkeypatch.setenv("FORGEJO_TOKEN", "x")
    monkeypatch.setenv("GH_MIRROR_REPOS", "https://x.git")
    monkeypatch.setenv("GH_MIRROR_TOKEN", "x")

    from nexus_deploy.ssh import SSHError

    class _BoomSSH:
        def __init__(self, _host: str) -> None: ...
        def __enter__(self) -> _BoomSSH:
            return self

        def __exit__(self, *_: Any) -> None: ...
        def port_forward(self, *_a: Any, **_k: Any) -> Any:
            raise SSHError("ssh tunnel boom")

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _BoomSSH)

    from nexus_deploy.__main__ import _forgejo_mirror_setup

    rc = _forgejo_mirror_setup([])
    assert rc == 2
    assert "ssh tunnel" in capsys.readouterr().err


def test_cli_dispatcher_routes_mirror_setup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["nexus_deploy", "forgejo", "mirror-setup", "--bogus"])
    from nexus_deploy.__main__ import main

    rc = main()
    assert rc == 2
    assert "mirror-setup" in capsys.readouterr().err


def test_cli_dispatcher_routes_woodpecker_oauth(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["nexus_deploy", "forgejo", "woodpecker-oauth", "--bogus"])
    from nexus_deploy.__main__ import main

    rc = main()
    assert rc == 2
    assert "woodpecker-oauth" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# CLI argument validation — rc=2 on bad inputs
# ---------------------------------------------------------------------------


def test_cli_unknown_args_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_missing_required_env_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("REPO_NAME", raising=False)
    monkeypatch.delenv("FORGEJO_REPO_OWNER", raising=False)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ADMIN_EMAIL" in err
    assert "REPO_NAME" in err
    assert "FORGEJO_REPO_OWNER" in err


def test_cli_missing_admin_pass_returns_rc_1_with_empty_restart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No forgejo_admin_password → rc=1 (yellow), still emits empty RESTART_SERVICES."""
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "RESTART_SERVICES=" in out
    assert "FORGEJO_TOKEN=" not in out


def test_cli_bad_secrets_json_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setattr("sys.stdin.read", lambda: "not-json")

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 2


def test_cli_ssh_tunnel_failure_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SSHError during port_forward → rc=2, NO token in stdout."""
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setattr("sys.stdin.read", lambda: '{"forgejo_admin_password": "x"}')

    from nexus_deploy.ssh import SSHError

    class _BoomSSH:
        def __init__(self, _host: str) -> None: ...
        def __enter__(self) -> _BoomSSH:
            return self

        def __exit__(self, *_: Any) -> None: ...
        def port_forward(self, *_a: Any, **_k: Any) -> Any:
            raise SSHError("ssh tunnel boom")

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _BoomSSH)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "ssh tunnel" in captured.err
    assert "FORGEJO_TOKEN=" not in captured.out


def test_cli_unexpected_exception_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Generic exception caught and reroutes Python's default rc=1 to rc=2."""
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setattr("sys.stdin.read", lambda: '{"forgejo_admin_password": "x"}')

    fake_ssh = MagicMock()
    fake_ssh.__enter__ = MagicMock(return_value=fake_ssh)
    fake_ssh.__exit__ = MagicMock(return_value=None)
    fake_pf = MagicMock()
    fake_pf.__enter__ = MagicMock(return_value=12345)
    fake_pf.__exit__ = MagicMock(return_value=None)
    fake_ssh.port_forward = MagicMock(return_value=fake_pf)
    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda host: fake_ssh)

    secret_in_message = "do-not-leak-secret-XYZZY"

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(secret_in_message)

    monkeypatch.setattr("nexus_deploy.__main__.run_configure_forgejo", boom)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 2
    err = capsys.readouterr().err
    # Type name only, never str(exc) — the exception's message MUST NOT leak
    assert "RuntimeError" in err
    assert secret_in_message not in err


def test_cli_transport_failure_returns_rc_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CalledProcessError from ssh/rsync → rc=2."""
    monkeypatch.setenv("ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("REPO_NAME", "nexus-foo")
    monkeypatch.setenv("FORGEJO_REPO_OWNER", "admin")
    monkeypatch.setattr("sys.stdin.read", lambda: '{"forgejo_admin_password": "x"}')

    fake_ssh = MagicMock()
    fake_ssh.__enter__ = MagicMock(return_value=fake_ssh)
    fake_ssh.__exit__ = MagicMock(return_value=None)
    fake_pf = MagicMock()
    fake_pf.__enter__ = MagicMock(return_value=12345)
    fake_pf.__exit__ = MagicMock(return_value=None)
    fake_ssh.port_forward = MagicMock(return_value=fake_pf)
    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda host: fake_ssh)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise subprocess.CalledProcessError(255, ["ssh", "secret-arg"])

    monkeypatch.setattr("nexus_deploy.__main__.run_configure_forgejo", boom)

    from nexus_deploy.__main__ import _forgejo_configure

    rc = _forgejo_configure([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "transport failure" in err
    assert "secret-arg" not in err  # exc.cmd MUST NOT leak


def test_cli_dispatcher_routes_forgejo_configure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m nexus_deploy forgejo configure` reaches the handler."""
    monkeypatch.setattr(sys, "argv", ["nexus_deploy", "forgejo", "configure", "--bogus"])

    from nexus_deploy.__main__ import main

    rc = main()
    assert rc == 2  # --bogus rejected
    assert "forgejo configure" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# SUBDOMAIN_SEPARATOR — Issue #540 (woodpecker oauth redirect_uri)
# ---------------------------------------------------------------------------


@responses.activate
def test_woodpecker_oauth_default_separator_dot_form_redirect_uri() -> None:
    """Default separator='.' produces ``https://woodpecker.<domain>/authorize``
    — byte-identical to pre-#540 contract."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/user/applications/oauth2", status=200, json=[])
    captured: dict[str, object] = {}

    def _capture(request: Any) -> tuple[int, dict[str, str], str]:
        body = json.loads(request.body or "{}")
        captured["redirect_uris"] = body.get("redirect_uris")
        return (
            201,
            {},
            json.dumps({"client_id": "id", "client_secret": "sec"}),
        )

    responses.add_callback(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        callback=_capture,
    )
    run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="example.com",
        forgejo_token="tok",
        admin_username="admin",
    )
    assert captured["redirect_uris"] == ["https://woodpecker.example.com/authorize"]


@responses.activate
def test_woodpecker_oauth_dash_separator_yields_flat_redirect_uri() -> None:
    """Multi-tenant fork with separator='-' produces a flat-subdomain
    redirect URI matching the DNS Tofu provisions for that tenant."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/user/applications/oauth2", status=200, json=[])
    captured: dict[str, object] = {}

    def _capture(request: Any) -> tuple[int, dict[str, str], str]:
        body = json.loads(request.body or "{}")
        captured["redirect_uris"] = body.get("redirect_uris")
        return (
            201,
            {},
            json.dumps({"client_id": "id", "client_secret": "sec"}),
        )

    responses.add_callback(
        responses.POST,
        f"{BASE_URL}/api/v1/user/applications/oauth2",
        callback=_capture,
    )
    run_woodpecker_oauth_setup(
        base_url=BASE_URL,
        domain="user1.example.com",
        forgejo_token="tok",
        admin_username="admin",
        subdomain_separator="-",
    )
    assert captured["redirect_uris"] == ["https://woodpecker-user1.example.com/authorize"]


def _executable_lines(script: str) -> list[str]:
    return [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]


# ---------------------------------------------------------------------------
# render_ready_preamble — kept from the #676 module, which forgejo_runner
# also imports. The account-provisioning helpers it used to sit beside
# were superseded by run_configure_forgejo and removed with it.
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

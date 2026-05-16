"""Gitea admin/user/repo configuration + Woodpecker OAuth + mirror setup.

Canonical Gitea surface for the deploy pipeline. Three end-to-end
runners:

* :func:`run_configure_gitea` — DB-password sync, admin user lifecycle
  (create or sync, with legacy email-collision PATCH for stacks
  deployed pre-v0.51.9), regular user lifecycle, API token creation
  with retry-via-delete on conflict, workspace repo creation with
  private-PATCH fallback, collaborator add.
* :func:`run_woodpecker_oauth_setup` — provisions the OAuth2 app
  Woodpecker CI uses to authenticate against Gitea, returns
  client-id + client-secret for the Woodpecker .env writer.
* :func:`run_mirror_setup` — handles ``GH_MIRROR_REPOS`` mirror mode:
  per-mirror migrate + per-user fork.

Two transports, used deliberately:

- **CLI via ssh.run_script** for admin/user CRUD (list, create,
  change-password). Inside the gitea container the ``gitea admin user``
  CLI authenticates via peer auth (``-u git``) and DOES NOT need a
  working REST password — which matters because the whole point of
  the SYNC step is to make basic-auth work after persistent-volume
  password drift. Using REST for these would chicken-egg.
- **REST via port-forward + requests** for token, email PATCH, repo
  CRUD, collaborator add. By the time the token is minted, the admin
  password has already been synced via CLI, so basic-auth works.

R7 (token-not-in-LOCAL-argv): all REST calls use ``requests`` with
``auth=(user, pw)`` or ``headers={"Authorization": f"token {tok}"}``
— credentials live in the Authorization header, never in argv on
the deploy host (no shell-out for these calls).

What we DON'T claim — for the SSH/CLI paths, secrets DO transit
the remote container's argv for the brief duration of the docker-
exec call: ``gitea admin user create --password '<pw>'`` and
``psql -c "ALTER USER ... PASSWORD '<pw>'"`` are visible in
``ps -ef`` inside the relevant container while running. We feed
the rendered bash via ``ssh.run_script`` (stdin, not argv) so the
secret never lands in:
  - LOCAL ``ps`` on the deploy host
  - LOCAL CI logs (workflow argv-echoes the bash invocation only)
  - ``CalledProcessError.cmd`` / ``TimeoutExpired.cmd`` exception
    payloads

Tightening further (e.g. piping the password into ``gitea admin user
create`` via stdin or ``--password-stdin``) is upstream-tooling-dependent.

R5 (path safety): all user/repo path segments are validated against
``^[a-zA-Z0-9._-]+$`` before URL interpolation OR shell-quoting.
Username/repo-name with shell metacharacters are rejected up front.
"""

from __future__ import annotations

import re
import shlex
import time
import urllib.parse
from dataclasses import dataclass
from typing import Literal

import requests

from nexus_deploy.config import NexusConfig, service_host
from nexus_deploy.ssh import SSHClient

_CONNECT_TIMEOUT_S: float = 3.0
_READ_TIMEOUT_S: float = 15.0
_HTTP_TIMEOUT: tuple[float, float] = (_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)

_PATH_SAFE_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9._-]+$")

# Services that have Git integration (clone the workspace repo on start).
# Order matters for stable RESTART_SERVICES output → CLI emits the list
# in this order, intersected with `enabled_services`.
_GIT_INTEGRATED_SERVICES: tuple[str, ...] = (
    "jupyter",
    "marimo",
    "code-server",
    "meltano",
    "prefect",
)


def _http_timeout_for_deadline(deadline: float) -> tuple[float, float]:
    """Build a (connect, read) tuple clamped to time remaining.

    Same pattern as kestra.py — keeps ``wait_ready(timeout_s=0.05)``
    honest. Both legs are floored at 0.1s so requests doesn't hit its
    own zero-timeout edge case.
    """
    remaining = max(deadline - time.monotonic(), 0.1)
    return (
        min(_CONNECT_TIMEOUT_S, remaining),
        min(_READ_TIMEOUT_S, remaining),
    )


def _validate_path_segment(value: str, *, kind: str) -> None:
    """Reject shell-meta / URL-traversal in user/repo identifiers (R5).

    Allowed: ``[a-zA-Z0-9._-]+`` — but explicitly NOT ``.`` or ``..``
    (which match the regex but are URL-traversal in path context).
    Dotted usernames like ``stefan.koch`` are allowed (Gitea permits
    them — that's the dotted-username class from PR #464).
    """
    if not _PATH_SAFE_RE.fullmatch(value):
        raise GiteaError(f"unsafe {kind}: {value!r}")
    if value in (".", ".."):
        raise GiteaError(f"unsafe {kind}: {value!r}")


_USER_FORK_SANITIZE_RE: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9]")


def _sanitize_user_for_fork_name(username: str) -> str:
    """Replace every non-alphanumeric char in ``username`` with ``_``.

    Used to derive a fork repo name like ``<orig>_<sanitized_user>``
    where the user's username may contain dots or hyphens that
    Gitea allows in usernames but operators want flattened in repo
    names. The naming scheme is byte-stable so existing forks across
    re-deploys keep matching.
    """
    return _USER_FORK_SANITIZE_RE.sub("_", username)


def _basename_no_git(repo_url: str) -> str:
    """``basename "$REPO_URL" .git`` — the last path segment with a
    trailing ``.git`` stripped if present.

    Handles both ``https://github.com/owner/repo.git`` and
    ``https://.../repo`` (no .git suffix); both yield ``repo``.
    """
    last = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if last.endswith(".git"):
        return last[: -len(".git")]
    return last


def _escape_sql_string_literal(value: str) -> str:
    """Escape a value for safe inclusion in a single-quoted SQL string.

    ``\\`` → ``\\\\`` first, then ``'`` → ``''``. Order matters —
    escape backslashes before quotes so a literal backslash in the
    password doesn't end up doubling the quote escape.
    """
    return value.replace("\\", "\\\\").replace("'", "''")


def _parse_admin_list_for_user(text: str, username: str) -> tuple[bool, str | None]:
    """Column-exact awk-equivalent on ``gitea admin user list`` output (R1).

    Gitea CLI output:

    .. code-block:: text

        ID    Username    Email                FullName    IsActive
        1     admin       admin@example.com    Admin       true
        2     stefan      stefan@example.com   Stefan      true

    Returns ``(exists, email)``: column-2 (Username) must equal
    ``username`` exactly. NEVER substring match — the dotted-username
    bug from PR #464 was: ``grep -c 'stefan.koch'`` matched admin's
    email column ``stefan.koch@hslu.ch`` even though no user with
    that username existed, so CREATE was skipped, SYNC then failed.

    Empty / malformed output → ``(False, None)``. Headers (``NR==1``)
    are skipped.
    """
    for line_no, raw_line in enumerate(text.splitlines()):
        if line_no == 0:
            continue  # header
        parts = raw_line.split()
        if len(parts) < 2:
            continue
        if parts[1] == username:
            email = parts[2] if len(parts) >= 3 else None
            return True, email
    return False, None


def _render_db_pw_sync_script(
    escaped_pw: str,
    *,
    attempts: int,
    interval_s: float,
) -> str:
    """Render bash to retry psql ALTER USER inside the gitea-db container.

    Peer auth via ``-U nexus-gitea`` (no ``-W``), so no PGPASSWORD env
    var is needed and the password value only enters the SQL string
    literal. The SCRIPT body (containing the SQL) is fed via stdin
    by the caller (``ssh.run_script``), so the password does NOT
    appear in:
      - LOCAL ``ps`` on the deploy host
      - LOCAL CI logs / ``CalledProcessError.cmd`` payloads
      - SSH argv on the deploy host

    The password DOES appear in the gitea-db container's ``ps -ef``
    for the brief duration of the ``psql -c "ALTER USER … PASSWORD
    '<pw>'"`` call (since psql takes the SQL via argv). Tightening
    would require either ``\\password`` (interactive) or a server-
    side script feeding the SQL via stdin to psql, both of which
    add complexity for marginal gain on a runner-isolated container.

    A RESULT line is emitted on success so the caller can disambiguate
    "succeeded after N tries" from "all N tries failed".
    """
    sql = f"ALTER USER \"nexus-gitea\" WITH PASSWORD '{escaped_pw}'"
    quoted_sql = shlex.quote(sql)
    return (
        "set -euo pipefail\n"
        f"for i in $(seq 1 {attempts}); do\n"
        f"  if docker exec gitea-db psql -U nexus-gitea -d gitea "
        f"-c {quoted_sql} >/dev/null 2>&1; then\n"
        '    echo "RESULT db_pw=synced"\n'
        "    exit 0\n"
        "  fi\n"
        f"  sleep {interval_s}\n"
        "done\n"
        'echo "RESULT db_pw=failed"\n'
        "exit 1\n"
    )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


CreateUserStatus = Literal["created", "already_exists", "synced", "failed"]
CreateRepoStatus = Literal["created", "already_exists", "failed"]


@dataclass(frozen=True)
class CreateUserResult:
    name: str
    status: CreateUserStatus
    detail: str = ""


@dataclass(frozen=True)
class CreateRepoResult:
    name: str
    status: CreateRepoStatus
    detail: str = ""


MirrorStatus = Literal["created", "already_exists", "failed"]
ForkStatus = Literal["created", "already_exists", "failed"]


@dataclass(frozen=True)
class MirrorResult:
    """One pull-mirror entry from the GH_MIRROR_REPOS loop.

    ``name`` is the Gitea-side repo name (``mirror-readonly-<basename>``),
    NOT the upstream GitHub URL. ``status`` distinguishes the
    idempotent re-deploy paths: ``already_exists`` is a soft-success
    (the mirror was created on a previous spin-up), ``created`` means
    Gitea ran the migration this call, ``failed`` means the migrate
    POST didn't return a usable id (caller routes to a yellow warning).
    """

    name: str
    status: MirrorStatus
    detail: str = ""


@dataclass(frozen=True)
class ForkResult:
    """The user-fork carved off the FIRST mirror in the loop.

    Only the first iteration's fork is created (matching the legacy
    bash's ``FORKED_WORKSPACE`` flag) — there's exactly one workspace
    repo per stack. ``status`` is one of ``created`` (POST 202),
    ``already_exists`` (POST 409 — fork survived a prior deploy),
    or ``failed`` (HTTP non-2xx-non-409, transport, or temp-token
    mint failed before the fork POST could run).

    The no-user-configured branch (``GITEA_USER_USERNAME`` empty)
    leaves :class:`MirrorSetupResult.fork` as ``None`` — no
    ``ForkResult`` is constructed at all on that path.
    """

    name: str
    owner: str
    status: ForkStatus
    detail: str = ""


@dataclass(frozen=True)
class OAuthAppResult:
    """Result of creating a Gitea OAuth2 application.

    Used for Woodpecker CI's Gitea-as-forge OAuth flow.
    ``client_id`` and ``client_secret`` are emitted via stdout in
    eval-able form so the orchestrator can inject them into
    Woodpecker's ``.env`` before the container starts.
    """

    name: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class GiteaResult:
    """Aggregate of all Gitea-config sub-steps.

    ``token`` is None until :meth:`GiteaCli.mint_token` succeeds (post-
    #519 fix switched from REST basic-auth to CLI peer-auth). The CLI
    handler emits ``GITEA_TOKEN=<token>`` to stdout iff token is
    non-None — eval-able by the orchestrator.
    """

    db_pw_synced: bool
    admin: CreateUserResult
    user: CreateUserResult | None
    token: str | None
    # Diagnostic message when ``token is None`` — empty string on
    # success. Captures the Gitea-CLI-side error description so the
    # CLI handler can emit it to stderr without leaking secrets.
    # Added in the post-#519 fix when production spin-up surfaced a
    # silent token-mint failure with no diagnostic trace.
    token_error: str
    repo: CreateRepoResult | None
    collaborator_added: bool
    restart_services: tuple[str, ...]

    @property
    def is_success(self) -> bool:
        """Strict success: every step that ran must have succeeded.

        - admin status must be ``created``, ``already_exists``, or ``synced``
          (NOT ``failed``)
        - user (if present) same
        - token must exist (if expected — i.e. core happy path)
        - repo (if present) must be ``created`` or ``already_exists``

        Maps False → rc=1 (yellow warn, continue). The CLI only emits
        ``GITEA_TOKEN=`` to stdout when ``token is not None`` — so on
        partial-failure paths where the token DID get minted (e.g.
        legacy email PATCH failed but token + repo OK), the caller
        captures the token via ``eval`` and downstream seed/kestra
        still work. On paths where token is None (token-mint failed)
        is_success is False AND no token line is emitted, so the
        caller sees rc=1 but no ``$GITEA_TOKEN``, and the seed/kestra
        blocks skip themselves on the empty-token guard.
        """
        if self.admin.status == "failed":
            return False
        if self.user is not None and self.user.status == "failed":
            return False
        if self.token is None:
            return False
        return not (self.repo is not None and self.repo.status == "failed")


class GiteaError(Exception):
    """Transport/validation failure surfaced to the caller.

    Carries no response body — Gitea error responses on auth-failure
    paths can echo back the credentials we just sent. Constructed
    from fixed format strings + status codes / type names only.
    """


# ---------------------------------------------------------------------------
# Hybrid client (post-#519 fix):
#   SSH CLI peer-auth: admin/user CRUD + token mint
#   REST basic-auth or token-auth: legacy email PATCH, repo CRUD, collab add
# Token minting moved from REST to CLI after the production
# 400-from-CreateAccessToken bug — see GiteaCli.mint_token docstring.
# ---------------------------------------------------------------------------


class GiteaCli:
    """SSH-driven ``docker exec gitea`` CLI wrapper.

    Used for admin/user CRUD where peer auth (``-u git`` inside the
    container) bypasses the chicken-egg of "we need to sync the
    password before basic-auth works". Output is parsed locally so
    the typed dispatch (``created`` / ``already_exists`` / ``synced``
    / ``failed``) matches the rest of the module.

    All commands fed via ``ssh.run_script`` so passwords land in
    stdin to the remote shell, not argv on either host.
    """

    def __init__(self, ssh: SSHClient) -> None:
        self.ssh = ssh

    def sync_db_password(
        self,
        password: str,
        *,
        attempts: int = 15,
        interval_s: float = 2.0,
    ) -> bool:
        """Retry ``ALTER USER`` until psql accepts the connection.

        On first start, gitea-db can take ~10-30s to accept connections.
        Bounded retry loop renders bash that exits 0 on first success
        or non-zero after exhausting attempts.
        """
        if not password:
            return False
        escaped = _escape_sql_string_literal(password)
        script = _render_db_pw_sync_script(escaped, attempts=attempts, interval_s=interval_s)
        # Generous overall timeout: attempts * interval_s + a safety
        # margin for ssh + docker exec setup per iteration. Never
        # raises — this is best-effort and we map a non-zero rc to
        # ``False`` so the caller can route to a yellow warning.
        timeout = float(attempts) * float(interval_s) + 30.0
        result = self.ssh.run_script(script, check=False, timeout=timeout)
        return result.returncode == 0 and "RESULT db_pw=synced" in result.stdout

    def list_admin_users(self) -> str:
        """Run ``gitea admin user list --admin`` and return raw output.

        Empty string if ssh/docker fails — the caller routes empty
        list to the CREATE branch, where any unexpected error
        surfaces on the next CLI call rather than spinning here.
        """
        # ``2>/dev/null`` keeps deprecated-flag warnings from polluting
        # the parsed output. ``|| echo ""`` swallows non-zero exit
        # (transient docker/gitea startup race).
        result = self.ssh.run_script(
            "docker exec -u git gitea gitea admin user list --admin 2>/dev/null || echo ''",
            check=False,
            timeout=30.0,
        )
        return result.stdout if result.returncode == 0 else ""

    def list_users(self) -> str:
        """Run ``gitea admin user list`` (non-admin scope)."""
        result = self.ssh.run_script(
            "docker exec -u git gitea gitea admin user list 2>/dev/null || echo ''",
            check=False,
            timeout=30.0,
        )
        return result.stdout if result.returncode == 0 else ""

    def create_admin(self, username: str, password: str, email: str) -> CreateUserResult:
        return self._create_user(username, password, email, is_admin=True)

    def create_user(self, username: str, password: str, email: str) -> CreateUserResult:
        return self._create_user(username, password, email, is_admin=False)

    def _create_user(
        self,
        username: str,
        password: str,
        email: str,
        *,
        is_admin: bool,
    ) -> CreateUserResult:
        _validate_path_segment(username, kind="username")
        # email is not a URL segment but still feed via shlex.quote
        # since it lands in argv after rendering. The container's
        # `gitea admin user create` accepts it directly.
        admin_flag = "--admin " if is_admin else ""
        script = (
            "set -euo pipefail\n"
            f"docker exec -u git gitea gitea admin user create {admin_flag}"
            f"--username {shlex.quote(username)} "
            f"--password {shlex.quote(password)} "
            f"--email {shlex.quote(email)} "
            "--must-change-password=false 2>&1\n"
        )
        result = self.ssh.run_script(script, check=False, timeout=30.0)
        text = result.stdout
        # ``CreateUserResult.name`` is always the real username (Copilot
        # round 1) — using a role label ("admin"/"user") here while
        # ``sync_password`` returns the actual username made the field
        # semantics inconsistent and confused downstream reporting.
        text_lc = text.lower()
        if any(kw in text_lc for kw in ("created", "success", "new user")):
            return CreateUserResult(name=username, status="created")
        # Gitea returns "user already exists" / "email already in use" on
        # collision — both route to ``already_exists`` so the caller can
        # follow up with a sync_password (which is idempotent) instead of
        # treating it as a failure.
        if "already" in text_lc:
            return CreateUserResult(name=username, status="already_exists")
        return CreateUserResult(
            name=username,
            status="failed",
            detail=text.strip()[:200] if text else "(no output)",
        )

    def mint_token(
        self,
        username: str,
        name: str,
        scopes: str = "all",
    ) -> tuple[str | None, str]:
        """Generate API token via ``gitea admin user generate-access-token``.

        Returns ``(sha1_or_None, diagnostic_message)``. On success the
        diagnostic is empty. On failure the diagnostic is a short
        Gitea-side error description suitable for stderr — never
        password material.

        Idempotent: deletes any existing token with this name first
        (psql DELETE inside the gitea-db container — peer auth, no
        password needed), then generates fresh. Two-pronged peer-
        auth approach because:

        1. Gitea v1.23 CLI has NO ``delete-access-token`` subcommand
           (verified live: ``admin user`` only exposes create / list
           / change-password / delete-USER / generate-access-token).
           A previous attempt to use ``gitea admin user
           delete-access-token`` failed silently in production
           (PR #520 spin-up surfaced it via the diagnostic field
           added in this same PR, after diagnosing as the bash
           ``|| true`` swallowing the unknown-subcommand error).
        2. REST DELETE on the tokens API requires basic-auth, which
           hits the same chicken-egg as the original PR #519 token-
           mint REST POST. Avoid.

        psql peer-auth bypasses both. The DELETE is scoped to the
        admin's UID via a subquery on the ``user`` table — name
        uniqueness in ``access_token`` is per-user (``UNIQUE INDEX
        UQE_access_token_name`` on (uid, name)). Both ``username``
        and ``name`` pass through :func:`_validate_path_segment`
        first, so the SQL string is injection-safe by construction.
        """
        _validate_path_segment(username, kind="username")
        _validate_path_segment(name, kind="token_name")
        # psql DELETE — peer auth via -U inside gitea-db container.
        # Same approach as :meth:`sync_db_password`.
        #
        # Capture rc + stdout (no ``|| true``, no ``2>/dev/null``).
        # ``ssh.run_script(check=False)`` already prevents the
        # subprocess layer from raising on a non-zero exit, so the
        # earlier "swallow everything" pattern was double-defence
        # at the cost of debuggability: when the delete failed
        # silently and the generate later collided with the
        # surviving token, the operator saw "name has been used
        # already" but no hint why the delete didn't run. Prepend
        # the delete diagnostic to ``token_error`` if the subsequent
        # generate fails (success path: irrelevant, drop it).
        #
        # SQL injection-safe by construction. Both ``name`` and
        # ``username`` are validated against ``_PATH_SAFE_RE``
        # ([a-zA-Z0-9._-]+) above, so neither can contain a single
        # quote or semicolon — i.e. neither value can break out of
        # the single-quoted SQL string literal it's interpolated into.
        # (The dash IS allowed, so e.g. ``stefan-koch`` is a valid
        # username and ``--`` would survive the regex; that's still
        # safe here because the dashes stay INSIDE the quoted string
        # — they only become a SQL comment marker if the surrounding
        # quotes are broken, which the no-single-quote rule prevents.)
        # ruff's S608 below is the generic "f-string SQL" heuristic
        # and doesn't see the validator.
        delete_sql = (
            f"DELETE FROM access_token WHERE name = '{name}' "  # noqa: S608
            f"AND uid = (SELECT id FROM \"user\" WHERE lower_name = lower('{username}'));"
        )
        delete_script = (
            f"docker exec gitea-db psql -U nexus-gitea -d gitea -c {shlex.quote(delete_sql)} 2>&1\n"
        )
        delete_result = self.ssh.run_script(delete_script, check=False, timeout=30.0)
        delete_diag = ""
        if delete_result.returncode != 0:
            # psql / docker error output is non-secret (no row data
            # in the connection-or-permission-failure paths psql
            # produces) — safe to surface. Capture first line only.
            first_line = (delete_result.stdout or "").splitlines()
            detail = first_line[0][:200] if first_line else "(no output)"
            delete_diag = f"prior delete rc={delete_result.returncode}: {detail}"

        generate_script = (
            "set -euo pipefail\n"
            "docker exec -u git gitea gitea admin user generate-access-token "
            f"--username {shlex.quote(username)} "
            f"--token-name {shlex.quote(name)} "
            f"--scopes {shlex.quote(scopes)} 2>&1\n"
        )
        result = self.ssh.run_script(generate_script, check=False, timeout=30.0)
        if result.returncode != 0:
            # Output examples on failure: "User does not exist" or
            # "Command error: access token name has been used already".
            # Capture first line only. Prepend the delete diagnostic
            # so name-collision failures can be traced to a prior
            # delete that didn't actually run.
            first_line = (result.stdout or "").splitlines()
            detail = first_line[0][:200] if first_line else "(no output)"
            msg = f"CLI rc={result.returncode}: {detail}"
            if delete_diag:
                msg = f"{delete_diag} | {msg}"
            return None, msg

        # Success output: "Access token was successfully created: <40-hex>"
        match = re.search(r"\b([a-f0-9]{40})\b", result.stdout or "")
        if match:
            return match.group(1), ""
        return None, "CLI rc=0 but no sha1 in output"

    def sync_password(self, username: str, password: str) -> CreateUserResult:
        """``gitea admin user change-password`` — peer-auth, no old password.

        Gitea's CLI command takes the username + new password and
        updates the credential without requiring the previous one.
        Idempotent: running twice on the same password is a no-op.
        """
        _validate_path_segment(username, kind="username")
        script = (
            "set -euo pipefail\n"
            "docker exec -u git gitea gitea admin user change-password "
            f"--username {shlex.quote(username)} "
            f"--password {shlex.quote(password)} "
            "--must-change-password=false 2>&1\n"
        )
        result = self.ssh.run_script(script, check=False, timeout=30.0)
        if result.returncode == 0:
            return CreateUserResult(name=username, status="synced")
        return CreateUserResult(
            name=username,
            status="failed",
            detail=result.stdout.strip()[:200] if result.stdout else "(no output)",
        )


class GiteaClient:
    """REST client for Gitea. Basic-auth pre-token, token-auth post-token.

    Path components in URL interpolation are validated against the
    R5 path-safety regex before the f-string runs. Credentials in
    Authorization header only — ``with_token`` returns a new client
    instance so the pre/post-token modes don't share mutable state.
    """

    def __init__(
        self,
        base_url: str,
        *,
        admin_username: str,
        admin_password: str,
    ) -> None:
        if not admin_username or not admin_password:
            raise ValueError("GiteaClient requires non-empty admin credentials")
        _validate_path_segment(admin_username, kind="admin_username")
        self.base_url = base_url.rstrip("/")
        self.admin_username = admin_username
        self._auth: tuple[str, str] | None = (admin_username, admin_password)
        self._token: str | None = None

    def with_token(self, token: str) -> GiteaClient:
        """Return a NEW client that uses token-auth instead of basic-auth.

        Token must be non-empty. Returns a separate instance so callers
        can't accidentally fall back to basic-auth on a client that's
        meant to be token-only.
        """
        if not token:
            raise ValueError("with_token requires a non-empty token")
        # New instance — copy URL + admin_username, drop basic-auth,
        # set token. Bypass __init__'s admin_password requirement.
        new = GiteaClient.__new__(GiteaClient)
        new.base_url = self.base_url
        new.admin_username = self.admin_username
        new._auth = None
        new._token = token
        return new

    def _request_kwargs(self) -> dict[str, object]:
        """Build auth kwargs (headers OR auth tuple, never both)."""
        if self._token is not None:
            return {"headers": {"Authorization": f"token {self._token}"}}
        if self._auth is not None:
            return {"auth": self._auth}
        raise GiteaError("client has no auth configured")  # pragma: no cover

    def wait_ready(self, *, timeout_s: float = 60.0, interval_s: float = 2.0) -> bool:
        """Poll ``GET /api/healthz`` until 200. Public endpoint, no auth.

        Sleep clamped to deadline (kestra.py pattern).
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                resp = requests.get(
                    f"{self.base_url}/api/healthz",
                    timeout=_http_timeout_for_deadline(deadline),
                )
            except (requests.ConnectionError, requests.Timeout):
                resp = None
            if resp is not None and resp.status_code == 200:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval_s, remaining))
        return False

    def patch_user_email(self, username: str, email: str, *, login_name: str) -> bool:
        """``PATCH /api/v1/admin/users/<u>`` — email-only update (R2).

        Gitea's admin-users schema rejects partial bodies, so the
        full ``{email, source_id, login_name}`` triple is required
        even though we only want to change email. ``source_id: 0`` =
        local auth provider. Returns True on 200, False on any other
        status (including auth failures — caller handles non-fatal
        path).
        """
        _validate_path_segment(username, kind="username")
        body = {"email": email, "source_id": 0, "login_name": login_name}
        try:
            resp = requests.patch(
                f"{self.base_url}/api/v1/admin/users/{username}",
                json=body,
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def repo_exists(self, owner: str, name: str) -> bool:
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/repos/{owner}/{name}",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GiteaError(f"repo_exists transport ({type(exc).__name__})") from exc
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise GiteaError(f"repo_exists HTTP {resp.status_code}")

    def create_repo(
        self,
        name: str,
        *,
        private: bool = True,
        auto_init: bool = True,
        default_branch: str = "main",
        description: str = "",
    ) -> CreateRepoResult:
        """``POST /api/v1/user/repos`` — creates under the authenticated user.

        409 → ``already_exists``. ``patch_repo_private`` is the
        recommended fallback to ensure the existing repo is private.
        """
        _validate_path_segment(name, kind="repo_name")
        body = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "default_branch": default_branch,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/user/repos",
                json=body,
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            return CreateRepoResult(
                name=name, status="failed", detail=f"transport ({type(exc).__name__})"
            )
        if resp.status_code in (200, 201):
            return CreateRepoResult(name=name, status="created", detail="POST 201")
        if resp.status_code == 409:
            return CreateRepoResult(name=name, status="already_exists", detail="POST 409")
        # Gitea also returns 422 with "already exists" for some modes
        # (CE vs EE differ). Match conservatively.
        if resp.status_code == 422:
            try:
                msg = resp.json().get("message", "") if resp.content else ""
            except ValueError:
                msg = ""
            if isinstance(msg, str) and "already exists" in msg.lower():
                return CreateRepoResult(
                    name=name, status="already_exists", detail="POST 422 already exists"
                )
        return CreateRepoResult(name=name, status="failed", detail=f"POST {resp.status_code}")

    def patch_repo_private(self, owner: str, name: str, *, private: bool = True) -> bool:
        """``PATCH /api/v1/repos/<o>/<n>`` — ensure repo is/isn't private."""
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        try:
            resp = requests.patch(
                f"{self.base_url}/api/v1/repos/{owner}/{name}",
                json={"private": private},
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def add_collaborator(
        self,
        owner: str,
        name: str,
        collaborator: str,
        *,
        permission: str = "write",
    ) -> bool:
        """``PUT /api/v1/repos/<o>/<n>/collaborators/<c>`` — idempotent.

        204 (added) and 422 ("already a collaborator") both → True.
        """
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        _validate_path_segment(collaborator, kind="collaborator")
        try:
            resp = requests.put(
                f"{self.base_url}/api/v1/repos/{owner}/{name}/collaborators/{collaborator}",
                json={"permission": permission},
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code in (204, 422)

    # -------------------------------------------------------------------
    # Mirror-mode operations
    # -------------------------------------------------------------------

    def get_user_id(self, username: str) -> int | None:
        """``GET /api/v1/users/<u>`` — returns user's numeric id, or None.

        Used by the mirror-migrate flow: Gitea's ``/api/v1/repos/migrate``
        requires the target owner's UID (not username) in the
        ``uid`` field. We can't substitute the admin's username
        directly. None on 404 (user doesn't exist).
        """
        _validate_path_segment(username, kind="username")
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/users/{username}",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GiteaError(f"get_user_id transport ({type(exc).__name__})") from exc
        if resp.status_code == 404:
            # Genuine "user doesn't exist" — this is the only path
            # that returns None. Distinct from malformed-response
            # handling below which raises so the caller can surface
            # the diagnostic via admin_uid_error.
            return None
        if resp.status_code != 200:
            raise GiteaError(f"get_user_id HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise GiteaError("get_user_id response was not JSON") from exc
        uid = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(uid, int):
            # 200 but the response shape is wrong (proxy mangling,
            # Gitea schema drift). Raise so admin_uid_error surfaces
            # the diagnostic — without this, run_mirror_setup would
            # treat it as a genuine 404 and the CLI would print the
            # misleading "admin user not found in Gitea". (Copilot R5)
            raise GiteaError("get_user_id response missing integer 'id'")
        return uid

    def migrate_mirror(
        self,
        repo_name: str,
        clone_url: str,
        owner_uid: int,
        github_pat: str,
        *,
        mirror_interval: str = "10m0s",
    ) -> MirrorResult:
        """``POST /api/v1/repos/migrate`` — clone-mirror a remote repo.

        ``github_pat`` is the GitHub personal access token used by
        Gitea to clone the (private) source repo; it travels in
        the request body as ``auth_token`` and is never logged
        locally or rendered into argv.

        Returns :class:`MirrorResult`:
        - ``status="created"`` on 200 OR 201 with a parseable
          integer ``id`` in the body. Gitea v1.20+ documents 201
          for /repos/migrate, but we accept 200 too for forward-
          compat with older / forked Gitea variants.
        - ``status="already_exists"`` on 409 OR 422 where the
          message contains "already exists".
        - ``status="failed"`` for other non-2xx / missing id paths.
          Caller routes to a yellow warning per mirror so a single
          bad URL doesn't abort the whole loop.
        """
        _validate_path_segment(repo_name, kind="repo_name")
        body = {
            "clone_addr": clone_url,
            "repo_name": repo_name,
            "private": True,
            "mirror": True,
            "mirror_interval": mirror_interval,
            "auth_token": github_pat,
            "uid": owner_uid,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/repos/migrate",
                json=body,
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            return MirrorResult(
                name=repo_name,
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        if resp.status_code in (200, 201):
            try:
                payload = resp.json()
            except ValueError:
                return MirrorResult(name=repo_name, status="failed", detail="response not JSON")
            if isinstance(payload, dict) and isinstance(payload.get("id"), int):
                return MirrorResult(
                    name=repo_name, status="created", detail=f"POST {resp.status_code}"
                )
            return MirrorResult(name=repo_name, status="failed", detail="response missing id")
        if resp.status_code == 409:
            return MirrorResult(name=repo_name, status="already_exists", detail="POST 409")
        if resp.status_code == 422:
            try:
                msg = resp.json().get("message", "") if resp.content else ""
            except ValueError:
                msg = ""
            if isinstance(msg, str) and "already exists" in msg.lower():
                return MirrorResult(
                    name=repo_name,
                    status="already_exists",
                    detail="POST 422 already exists",
                )
        return MirrorResult(name=repo_name, status="failed", detail=f"POST {resp.status_code}")

    def trigger_mirror_sync(self, owner: str, name: str) -> bool:
        """``POST /api/v1/repos/<o>/<n>/mirror-sync`` — pull fresh from upstream.

        Returns True on 200 (Gitea queued the sync), False otherwise.
        Best-effort: caller doesn't abort on False — the next 10-min
        cron tick of the mirror schedule will re-sync.
        """
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/repos/{owner}/{name}/mirror-sync",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def get_branch_head_sha(self, owner: str, name: str, branch: str) -> str | None:
        """``GET /api/v1/repos/<o>/<n>/branches/<branch>`` — return the
        commit SHA of the branch tip, or ``None`` on any failure
        (transport, 4xx, malformed response).

        Used by :func:`run_mirror_setup` to poll for mirror-sync
        completion: trigger the sync, then watch the mirror's HEAD
        SHA until it changes from the pre-sync baseline.

        Branch names may legitimately contain slashes (``feat/foo``,
        ``release/1.2``); URL-encode the branch segment rather than
        validating it as a single path segment so those don't raise
        before the GET is even sent. Owner + repo name are still
        single-segment-validated (no slashes allowed there).
        """
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        encoded_branch = urllib.parse.quote(branch, safe="")
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/repos/{owner}/{name}/branches/{encoded_branch}",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return None
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
        except ValueError:
            return None
        commit = payload.get("commit") if isinstance(payload, dict) else None
        if not isinstance(commit, dict):
            return None
        sha = commit.get("id")
        return sha if isinstance(sha, str) else None

    def merge_upstream(self, owner: str, name: str, branch: str) -> str:
        """``POST /api/v1/repos/<o>/<n>/merge-upstream`` — fast-forward fork
        from its parent's branch. Returns HTTP status code as a string
        for the caller's dispatch.

        Gitea's responses:
        - 200: merged (fork advanced)
        - 409: already up to date
        - 404: fork doesn't have a parent / branch missing on upstream
        - 5xx: server-side error

        Returns ``"200"`` / ``"409"`` / etc. or ``"transport"`` on
        connection failure — caller pattern-matches like the legacy
        bash's HTTP-code dispatch.
        """
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        # Branch may contain a slash (e.g. ``feat/branch``), so it's
        # passed in the body, not as a URL segment — no path-validation
        # needed for branch.
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/repos/{owner}/{name}/merge-upstream",
                json={"branch": branch},
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return "transport"
        return str(resp.status_code)

    def create_user_token(
        self,
        username: str,
        token_name: str,
        scopes: list[str],
        *,
        admin_username: str,
        admin_password: str,
    ) -> str | None:
        """Mint a token for ``username`` using admin's basic-auth.

        Used by the fork flow: forking a mirror needs a token that
        belongs to the target user (else the fork lands in admin's
        namespace, not the user's). Admin can create tokens on behalf
        of other users via basic-auth (NOT token-auth — token bearer
        only acts on its own user). Idempotent: on any first-attempt
        failure (non-200/201, transport, JSON parse, missing sha1)
        it deletes the token by name and retries once. (Copilot R6 —
        the previous "201-failure" wording was confusing because 201
        is the success code; the retry trigger is anything-not-success.)

        Returns the sha1 string on success, None on persistent failure
        (both attempts return non-success). None routes to a yellow
        warning + skip-fork at the orchestrator level.
        """
        _validate_path_segment(username, kind="username")
        _validate_path_segment(token_name, kind="token_name")
        body = {"name": token_name, "scopes": scopes}
        auth = (admin_username, admin_password)

        def _attempt() -> str | None:
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/users/{username}/tokens",
                    json=body,
                    auth=auth,
                    timeout=_HTTP_TIMEOUT,
                )
            except (requests.ConnectionError, requests.Timeout):
                return None
            if resp.status_code not in (200, 201):
                return None
            try:
                payload = resp.json()
            except ValueError:
                return None
            sha1 = payload.get("sha1") if isinstance(payload, dict) else None
            return sha1 if isinstance(sha1, str) and sha1 else None

        sha1 = _attempt()
        if sha1:
            return sha1
        # First attempt failed — token name may already exist.
        # Delete and retry once. Errors here are silenced; the next
        # _attempt() will surface any persistent failure as None.
        self.delete_user_token(
            username,
            token_name,
            admin_username=admin_username,
            admin_password=admin_password,
        )
        return _attempt()

    def delete_user_token(
        self,
        username: str,
        token_name: str,
        *,
        admin_username: str,
        admin_password: str,
    ) -> bool:
        """``DELETE /api/v1/users/<u>/tokens/<n>`` with admin basic-auth.

        Idempotent: 204 + 404 → True. Used by the fork flow to clean
        up a temp user-token after the fork POST settles, AND to
        clear a stale token before retrying create_user_token.
        """
        _validate_path_segment(username, kind="username")
        _validate_path_segment(token_name, kind="token_name")
        try:
            resp = requests.delete(
                f"{self.base_url}/api/v1/users/{username}/tokens/{token_name}",
                auth=(admin_username, admin_password),
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code in (204, 404)

    def fork_repo_as_user(
        self,
        source_owner: str,
        source_name: str,
        fork_name: str,
        *,
        user_token: str,
    ) -> str:
        """``POST /api/v1/repos/<o>/<n>/forks`` with the USER's bearer token.

        Returns HTTP status code as a string — caller dispatches:
        - ``"202"``: Gitea accepted the fork (queued)
        - ``"409"``: fork already exists in user's namespace
        - other: failure

        Uses the user's token (not admin's) so the fork lands in the
        user's namespace.
        """
        _validate_path_segment(source_owner, kind="owner")
        _validate_path_segment(source_name, kind="repo_name")
        _validate_path_segment(fork_name, kind="fork_name")
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/repos/{source_owner}/{source_name}/forks",
                json={"name": fork_name},
                headers={"Authorization": f"token {user_token}"},
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout):
            return "transport"
        return str(resp.status_code)

    # -------------------------------------------------------------------
    # OAuth2 application management (Woodpecker CI integration)
    # -------------------------------------------------------------------

    def list_oauth_apps(self) -> list[dict[str, object]]:
        """``GET /api/v1/user/applications/oauth2`` — list current user's apps.

        Returns the JSON array verbatim (each entry has ``id``, ``name``,
        ``redirect_uris``, etc. — but NO ``client_secret``; Gitea only
        returns the secret on initial create). Empty list if the user
        has no OAuth apps. Raises :class:`GiteaError` on transport /
        non-200 — we don't try to recover here; caller decides whether
        to skip the OAuth setup or hard-fail.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/user/applications/oauth2",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GiteaError(f"list_oauth_apps transport ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise GiteaError(f"list_oauth_apps HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise GiteaError("list_oauth_apps response was not JSON") from exc
        # Wrong shape (object instead of array) is a transport-level
        # anomaly — most likely an intermediate proxy returning an
        # error envelope, or a Gitea schema change. Silently coercing
        # to ``[]`` would skip the rotation-delete and let the create
        # pile up duplicate apps — exactly the bug the rotation
        # contract is supposed to prevent. Raise instead. (Copilot R2)
        if not isinstance(payload, list):
            raise GiteaError(
                f"list_oauth_apps response was not a JSON array (got {type(payload).__name__})"
            )
        return [item for item in payload if isinstance(item, dict)]

    def delete_oauth_app(self, app_id: int) -> bool:
        """``DELETE /api/v1/user/applications/oauth2/<id>``. 204+404 → True.

        Idempotent: 404 is treated as success (the app was already gone).
        Used to wipe a stale "Woodpecker CI" app before recreating with
        a fresh client_secret on every deploy.

        Three-way return semantics (Copilot R4-R5 — earlier code
        folded all three into ``False``, which made operator
        diagnostics ambiguous and silently downgraded 5xx to
        "rotation NOT started" even when Gitea may have already
        processed the DELETE before the error response was sent):

        - ``True``: Gitea ACK'd the delete (204) or the app was
          already gone (404). Server state is KNOWN: app no longer
          exists.
        - ``False``: Gitea returned a definitive 4xx (403 permission
          denied, 422 validation, etc.). 4xx semantics in REST are
          "client problem, server hasn't acted" → server state is
          KNOWN: app still exists. Caller can route to "rotation
          NOT started" with confidence.
        - ``raise GiteaError``: ``requests`` couldn't deliver a
          response (ConnectionError, Timeout) OR Gitea returned a
          5xx. In both cases server state is UNKNOWN — Gitea may
          have processed the DELETE before the failure. Caller
          must treat as "rotation possibly started" and abort to
          avoid the stale-creds outage class. (Copilot R5)
        """
        if not isinstance(app_id, int) or app_id <= 0:
            raise GiteaError(f"delete_oauth_app: invalid app_id {app_id!r}")
        try:
            resp = requests.delete(
                f"{self.base_url}/api/v1/user/applications/oauth2/{app_id}",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GiteaError(
                f"delete_oauth_app(id={app_id}) transport ({type(exc).__name__})"
            ) from exc
        if resp.status_code in (204, 404):
            return True
        # 5xx: server-side failure — the DELETE may have been applied
        # before whatever broke broke. Same ambiguity class as a
        # transport timeout: treat as "rotation possibly started".
        if 500 <= resp.status_code < 600:
            raise GiteaError(
                f"delete_oauth_app(id={app_id}) HTTP {resp.status_code} "
                "(server-side error, state ambiguous)"
            )
        # 4xx (or other unexpected codes): client-side problem,
        # Gitea hasn't acted on the DELETE. Server state is known.
        return False

    def create_oauth_app(
        self,
        name: str,
        redirect_uris: list[str],
        *,
        confidential_client: bool = True,
    ) -> OAuthAppResult:
        """``POST /api/v1/user/applications/oauth2`` — create OAuth app.

        Returns :class:`OAuthAppResult` with the freshly-issued
        ``client_id`` and ``client_secret``. Gitea returns the secret
        ONLY on this initial create (subsequent ``GET`` lists hide it),
        so the caller must capture both values from this response and
        persist them immediately.

        Raises :class:`GiteaError` on transport / non-201 / missing
        fields. Name + URIs are passed verbatim to Gitea; both ``name``
        and the host portion of redirect URIs should be operator-
        controlled (no user input), so no path-safety regex applies.
        """
        body = {
            "name": name,
            "redirect_uris": redirect_uris,
            "confidential_client": confidential_client,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/user/applications/oauth2",
                json=body,
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GiteaError(f"create_oauth_app transport ({type(exc).__name__})") from exc
        if resp.status_code != 201:
            raise GiteaError(f"create_oauth_app HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise GiteaError("create_oauth_app response was not JSON") from exc
        client_id = payload.get("client_id") if isinstance(payload, dict) else None
        client_secret = payload.get("client_secret") if isinstance(payload, dict) else None
        if not isinstance(client_id, str) or not client_id:
            raise GiteaError("create_oauth_app response missing 'client_id'")
        if not isinstance(client_secret, str) or not client_secret:
            raise GiteaError("create_oauth_app response missing 'client_secret'")
        return OAuthAppResult(name=name, client_id=client_id, client_secret=client_secret)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def _compute_restart_services(enabled: list[str]) -> tuple[str, ...]:
    """Intersection of ``_GIT_INTEGRATED_SERVICES`` and ``enabled``.

    Order preserved from ``_GIT_INTEGRATED_SERVICES`` so the CLI
    output is deterministic across runs.
    """
    enabled_set = set(enabled)
    return tuple(s for s in _GIT_INTEGRATED_SERVICES if s in enabled_set)


def run_configure_gitea(
    config: NexusConfig,
    *,
    base_url: str,
    ssh: SSHClient,
    admin_email: str,
    gitea_user_email: str | None,
    gitea_user_password: str | None,
    repo_name: str,
    gitea_repo_owner: str,
    is_mirror_mode: bool,
    enabled_services: list[str],
    ready_timeout_s: float = 60.0,
    db_sync_attempts: int = 15,
    db_sync_interval_s: float = 2.0,
) -> GiteaResult:
    """End-to-end Gitea configure runner.

    Steps:

    1. Sync gitea-db postgres password (peer-auth psql ALTER USER)
    2. Wait for ``/api/healthz``
    3. Admin: list via CLI → exists?
       - yes + legacy email collision → REST PATCH email
       - yes → CLI sync_password
       - no  → CLI create_admin
    4. User (if ``gitea_user_email``): list → exists?
       - yes → CLI sync_password
       - no  → CLI create_user
    5. Token: CLI ``mint_token`` (peer-auth ``generate-access-token``,
       idempotent delete-then-create; switched from REST in post-#519 fix)
    6. (non-mirror) repo: create → on already_exists → patch_repo_private
    7. (non-mirror, with user) collaborator add
    8. Build restart_services list (intersection with enabled)

    Returns :class:`GiteaResult` with token in stdout-eval-able form
    via the CLI handoff. Even on partial failures (e.g. legacy email
    PATCH failed but token created), the token IS in the result so
    the orchestrator can capture it via eval.
    """
    admin_username = config.admin_username or "admin"
    admin_password = config.gitea_admin_password or ""
    db_password = config.gitea_db_password or ""

    cli = GiteaCli(ssh)
    rest = GiteaClient(
        base_url=base_url,
        admin_username=admin_username,
        admin_password=admin_password,
    )

    # 1. DB password sync
    db_pw_synced = (
        cli.sync_db_password(
            db_password,
            attempts=db_sync_attempts,
            interval_s=db_sync_interval_s,
        )
        if db_password
        else False
    )

    # 2. Wait for Gitea HTTP ready
    if not rest.wait_ready(timeout_s=ready_timeout_s):
        return GiteaResult(
            db_pw_synced=db_pw_synced,
            # Use the configured admin_username (Copilot round 2) — not
            # the literal "admin" — so CreateUserResult.name carries
            # the same value across all paths regardless of how the
            # operator named the admin user.
            admin=CreateUserResult(name=admin_username, status="failed", detail="gitea not ready"),
            user=None,
            token=None,
            token_error="gitea not ready",  # noqa: S106 — diagnostic, not a credential
            repo=None,
            collaborator_added=False,
            restart_services=_compute_restart_services(enabled_services),
        )

    # 3. Admin: CLI list → parse → exists check → branch
    admin_list = cli.list_admin_users()
    admin_exists, current_admin_email = _parse_admin_list_for_user(admin_list, admin_username)

    # 3a. Legacy email-collision PATCH (before sync_password — if PATCH
    # fails because of password drift, sync_password later will fix
    # the password and the next deploy's PATCH will succeed).
    if admin_exists and gitea_user_email and current_admin_email == gitea_user_email:
        # Best-effort. If it fails, the sync_password below still runs;
        # next deploy will retry the PATCH.
        rest.patch_user_email(admin_username, admin_email, login_name=admin_username)

    if admin_exists:
        admin_result = cli.sync_password(admin_username, admin_password)
    else:
        admin_result = cli.create_admin(admin_username, admin_password, admin_email)
        # CREATE returns ``already_exists`` when the existence check was a
        # false negative (e.g. ssh+docker exec failed → empty list → CREATE
        # path → "user already exists"). Without a follow-up sync, the
        # admin password drift stays — the subsequent REST token mint
        # uses basic-auth with the OpenTofu-generated password and 401s.
        # Fall back to sync_password so we converge on the desired state.
        # Defence-in-depth tightening of rerun-tolerance (Copilot
        # round 1).
        if admin_result.status == "already_exists":
            admin_result = cli.sync_password(admin_username, admin_password)

    # 4. Regular user (only if email + password provided)
    user_result: CreateUserResult | None = None
    user_username: str | None = None
    if gitea_user_email and gitea_user_password:
        user_username = gitea_user_email.split("@", 1)[0]
        user_list = cli.list_users()
        user_exists, _ = _parse_admin_list_for_user(user_list, user_username)
        if user_exists:
            user_result = cli.sync_password(user_username, gitea_user_password)
        else:
            user_result = cli.create_user(user_username, gitea_user_password, gitea_user_email)
            # Same already_exists → sync_password fallback as for admin.
            if user_result.status == "already_exists":
                user_result = cli.sync_password(user_username, gitea_user_password)

    # 5. Token via CLI peer auth (was: REST basic-auth in PR #519).
    # Switched after production spin-up surfaced a silent 400 from
    # POST /api/v1/users/<u>/tokens despite admin password sync
    # reporting success — likely a subtle password-state race
    # between the bcrypt commit and the next-millisecond REST
    # auth check. CLI peer auth eliminates the chicken-egg: the
    # docker-exec runs as the container's git user with no
    # password verification needed.
    token, token_error = cli.mint_token(admin_username, "nexus-automation", "all")

    # 6+7. Repo + collaborator (skip in mirror mode)
    repo_result: CreateRepoResult | None = None
    collaborator_added = False
    if not is_mirror_mode and token is not None:
        rest_token = rest.with_token(token)
        repo_result = rest_token.create_repo(
            repo_name,
            private=True,
            auto_init=True,
            default_branch="main",
            description="Shared workspace for notebooks, workflows, and pipelines",
        )
        if repo_result.status == "already_exists":
            # Belt-and-suspenders: ensure existing repo is private.
            rest_token.patch_repo_private(gitea_repo_owner, repo_name, private=True)
        if repo_result.status != "failed" and user_username is not None and gitea_user_password:
            collaborator_added = rest_token.add_collaborator(
                gitea_repo_owner, repo_name, user_username, permission="write"
            )

    return GiteaResult(
        db_pw_synced=db_pw_synced,
        admin=admin_result,
        user=user_result,
        token=token,
        token_error=token_error,
        repo=repo_result,
        collaborator_added=collaborator_added,
        restart_services=_compute_restart_services(enabled_services),
    )


def run_woodpecker_oauth_setup(
    *,
    base_url: str,
    domain: str,
    gitea_token: str,
    admin_username: str,
    subdomain_separator: str = ".",
) -> tuple[OAuthAppResult | None, str, bool]:
    """End-to-end Woodpecker CI OAuth-app provisioning in Gitea.

    Idempotent re-run pattern:
      1. List existing OAuth apps under the admin user.
      2. If an app named "Woodpecker CI" already exists, DELETE it
         (so the new client_secret-bearing create returns a fresh
         pair — Woodpecker has no rotate-secret API, so deleting +
         recreating is the only way to surface the secret again).
      3. POST a fresh OAuth app with redirect URI
         ``https://woodpecker.<domain>/authorize`` and
         ``confidential_client=True`` (browser flow needs PKCE
         + secret).
      4. Return :class:`OAuthAppResult` with the new credentials.
         The CLI handler emits these via stdout in eval-able form
         so the orchestrator can write Woodpecker's ``.env`` before
         the rsync + ``docker compose up -d``.

    Returns ``(result, error, rotation_started)``:

    - ``result`` is the new :class:`OAuthAppResult` on success, ``None``
      on failure.
    - ``error`` is a short diagnostic on failure, empty on success.
    - ``rotation_started`` is True if at least one delete *might
      have* taken effect during this call:

      - definitively ACK'd by Gitea (204), OR
      - server-side state UNKNOWN (5xx response or transport
        timeout — Gitea may have processed the DELETE before the
        failure surfaced)

      It is False when no delete reached the wire at all (list
      failed, no matching apps) OR when every attempted delete
      was definitively rejected by Gitea (4xx with response — the
      app is KNOWN to still exist).

      The CLI handler uses this to dispatch:

      - True + result is None → rc=2 (abort): Gitea state may have
        moved past the previous OAuth pair, deploy must stop or
        Woodpecker keeps running with possibly-invalidated creds.
      - False + result is None → rc=1 (warn-and-continue): Gitea
        state untouched (or definitively rejected the rotation),
        Woodpecker's existing .env stays consistent.
      - True + result is set → rc=0: rotation completed cleanly.

      (Copilot R2 — initial flag; R5 — refined semantics for
      transport ambiguity, 5xx, and multi-app loop progress.)

    Auth: token-bearer (the GITEA_TOKEN minted in 2.2e/2.2e-fix).
    The list/delete/create endpoints all accept token auth as the
    authenticated user (admin in our case).
    """
    if not gitea_token:
        return None, "GITEA_TOKEN is empty", False
    _validate_path_segment(admin_username, kind="admin_username")

    # ``with_token`` returns a new client that uses token-auth instead
    # of basic-auth. The placeholder password is never sent — see
    # :meth:`GiteaClient.with_token`.
    client = GiteaClient(
        base_url=base_url,
        admin_username=admin_username,
        admin_password="placeholder-not-used",  # noqa: S106
    ).with_token(gitea_token)

    try:
        apps = client.list_oauth_apps()
    except GiteaError as exc:
        # str(exc) is safe — GiteaError messages are constructed from
        # fixed format strings + status codes only, never response bodies.
        return None, f"list_oauth_apps: {exc}", False

    # Find any existing app named exactly "Woodpecker CI" — Gitea
    # allows multiple apps with the same name, so iterate the full
    # list rather than break on first match. Each delete must
    # SUCCEED (204 or 404) before we proceed to create — otherwise
    # the rotation semantics break: we'd issue fresh credentials
    # while the old app remains valid, leaving stale OAuth tokens
    # active until the operator manually cleans up. (Copilot R1)
    rotation_started = False
    for app in apps:
        if app.get("name") == "Woodpecker CI":
            app_id = app.get("id")
            if not isinstance(app_id, int):
                # Defensive: Gitea's API contract returns integer ids,
                # but a malformed list entry (proxy mangling, schema
                # drift) could surface a None/string id. Silently
                # skipping the delete here would let the create
                # below produce a duplicate "Woodpecker CI" app —
                # exactly the bug rotation semantics is meant to
                # prevent. Bail with a definitive failure (rotation
                # NOT started — we never reached the wire). (Copilot R6)
                return (
                    None,
                    f"list entry has non-integer id: {app_id!r} — "
                    "refusing to create duplicate (rotation NOT started)",
                    rotation_started,
                )
            # Three-way dispatch on delete (Copilot R4):
            #   - True: Gitea ACK'd, app gone → continue to create
            #   - False: Gitea returned definitive non-success
            #     (4xx with response) → server state KNOWN, app
            #     still exists → rotation NOT started, safe to
            #     warn-and-continue (the existing .env stays
            #     consistent with Gitea)
            #   - GiteaError: transport timeout/reset OR 5xx →
            #     server state UNKNOWN, app may have been deleted
            #     before the response was lost → conservatively
            #     mark rotation_started=True so the CLI aborts
            try:
                deleted = client.delete_oauth_app(app_id)
            except GiteaError as exc:
                # Transport-ambiguity branch: server state UNKNOWN
                # → mark rotation_started=True regardless of any
                # prior loop progress.
                return (
                    None,
                    f"delete_oauth_app(id={app_id}): {exc} — "
                    "rotation broken (server state ambiguous)",
                    True,
                )
            if not deleted:
                # Definitive non-success on THIS app, but a PRIOR
                # iteration in the same loop may have already
                # successfully deleted a duplicate-named app —
                # preserve the accumulated rotation_started state
                # rather than discarding it. Without this, a
                # multi-app deployment where the first delete
                # succeeds and the second is rejected would
                # report rotation_started=False (rc=1, deploy
                # continues) while Woodpecker is now running on
                # a creds pair Gitea has already invalidated.
                # (Copilot R5)
                return (
                    None,
                    f"delete_oauth_app(id={app_id}): rejected by Gitea — "
                    "refusing to create duplicate (rotation "
                    f"{'partially started' if rotation_started else 'NOT started'})",
                    rotation_started,
                )
            rotation_started = True

    redirect_uri = f"https://{service_host('woodpecker', domain, subdomain_separator)}/authorize"
    try:
        return (
            client.create_oauth_app(
                "Woodpecker CI",
                [redirect_uri],
                confidential_client=True,
            ),
            "",
            rotation_started,
        )
    except GiteaError as exc:
        return None, f"create_oauth_app: {exc}", rotation_started


# ---------------------------------------------------------------------------
# Mirror-mode orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MirrorSetupResult:
    """Aggregate result of a GH_MIRROR_REPOS spin-up.

    The CLI handler emits ``FORK_NAME=<name>`` + ``GITEA_REPO_OWNER=<owner>``
    on stdout when ``fork`` reached ``created`` or ``already_exists``,
    so the orchestrator can call the existing seed-into-fork wrapper post-eval.

    ``is_success`` is True iff every mirror reached ``created`` or
    ``already_exists`` AND (if a fork was attempted) the fork did
    too. The CLI maps False → rc=1 (yellow warn, deploy continues —
    next spin-up retries).
    """

    admin_uid: int | None
    # Diagnostic when admin_uid is None — distinguishes "user
    # genuinely doesn't exist (404)" from auth/5xx/transport
    # failures so the CLI can print the real cause instead of
    # the misleading "admin UID not found". Empty string when
    # admin_uid was successfully resolved. (Copilot R4)
    admin_uid_error: str
    mirrors: tuple[MirrorResult, ...]
    fork: ForkResult | None
    collaborator_added_count: int
    fork_synced: bool
    # Diagnostic for the mirror-sync + merge-upstream chain on the
    # first iteration where the fork existed. Surfaced in the
    # orchestrator's PhaseResult.detail so operators can see WHY a
    # fork didn't pick up new upstream commits (most common cause:
    # GitHub upstream took longer than the settle timeout). Empty
    # string when no sync was attempted (no fork yet).
    sync_detail: str = ""

    @property
    def is_success(self) -> bool:
        if self.admin_uid is None:
            return False
        if any(m.status == "failed" for m in self.mirrors):
            return False
        return not (self.fork is not None and self.fork.status == "failed")


def run_mirror_setup(
    *,
    base_url: str,
    admin_username: str,
    admin_password: str,
    gitea_token: str,
    gitea_user_username: str | None,
    gh_mirror_repos: list[str],
    gh_mirror_token: str,
    workspace_branch: str,
    fork_token_name: str = "nexus-workspace-fork",  # noqa: S107
    mirror_sync_poll_seconds: float = 30.0,
    mirror_sync_poll_interval_seconds: float = 1.5,
) -> MirrorSetupResult:
    """End-to-end GH_MIRROR_REPOS provisioning.

    1. GET admin's UID (required by Gitea's migrate API).
    2. For each repo URL in ``gh_mirror_repos``:
       a. Compute mirror name ``mirror-readonly-<basename>``.
       b. POST /repos/migrate (or skip if 409/already_exists).
       c. Add the user as a read-collaborator on the mirror —
          MUST happen before (d) because the mirror is created
          private and the user's token (used in (d)) sees a
          private repo as 404 until collab is granted.
       d. On the FIRST mirror with a configured user, fork it
          into the user's namespace via a temp user-token
          (created + deleted on this call).
       e. If the fork was created on this iteration: snapshot the
          mirror's HEAD SHA, trigger ``mirror-sync`` on the mirror,
          then poll the mirror's HEAD up to
          ``mirror_sync_poll_seconds`` (with
          ``mirror_sync_poll_interval_seconds`` between polls) waiting
          for the upstream-fetch to land. Whether or not the SHA
          actually changed, call ``merge-upstream`` on the fork at
          ``workspace_branch`` (best-effort — the mirror may already
          be ahead from Gitea's periodic cron-tick or the initial
          migrate-fetch). The pre/post SHA + merge result land in
          ``MirrorSetupResult.sync_detail`` so operators can tell
          'sync landed', 'sync skipped (no change)', and 'sync
          failed but merged anyway' apart.

    The fork creation (step c) and fork-sync (step e) happen ONLY
    on the first iteration that has both a successful migrate AND a
    configured user — single-fork-per-stack semantics. Later
    iterations still do mirror+collab.

    All admin actions use ``gitea_token`` (token-bearer). The fork
    creation step uses a temporary token minted on behalf of
    ``gitea_user_username`` via admin basic-auth, then deleted right
    after. Both ``gitea_token`` and ``admin_password`` reach REST as
    request-auth only, never argv.
    """
    # Path safety on admin_username — used in URL interpolation
    # immediately below.
    _validate_path_segment(admin_username, kind="admin_username")

    client = GiteaClient(
        base_url=base_url,
        admin_username=admin_username,
        admin_password=admin_password,
    ).with_token(gitea_token)

    # 1. Admin UID lookup. Failure → no migrate possible. Distinguish
    # three failure modes so the CLI can surface the real cause
    # instead of the misleading "admin UID not found" for every path
    # (Copilot R4):
    #   - get_user_id raises GiteaError: auth/transport/5xx —
    #     stash exc message in admin_uid_error
    #   - get_user_id returns None: 404 (user genuinely doesn't
    #     exist) — admin_uid_error stays "" but admin_uid is None
    admin_uid: int | None = None
    admin_uid_error = ""
    try:
        admin_uid = client.get_user_id(admin_username)
    except GiteaError as exc:
        # GiteaError messages here are constructed from format
        # strings only (HTTP status / type names), no secrets —
        # safe to surface verbatim.
        admin_uid_error = str(exc)
    if admin_uid is None:
        return MirrorSetupResult(
            admin_uid=None,
            admin_uid_error=admin_uid_error,
            mirrors=(),
            fork=None,
            collaborator_added_count=0,
            fork_synced=False,
        )

    mirrors: list[MirrorResult] = []
    fork: ForkResult | None = None
    last_fork_failure: ForkResult | None = None
    fork_synced = False
    collaborator_added_count = 0
    sync_detail = ""

    for repo_url in gh_mirror_repos:
        repo_url = repo_url.strip()
        if not repo_url:
            continue
        orig_name = _basename_no_git(repo_url)
        mirror_name = f"mirror-readonly-{orig_name}"

        # Validate the derived mirror_name BEFORE calling repo_exists
        # / migrate_mirror — both internally invoke
        # ``_validate_path_segment`` which raises GiteaError on
        # unsafe values. Without this guard, one bad URL with
        # shell-meta chars in the basename (e.g.
        # ``.../repo?evil`` or ``.../repo;sh``) would propagate the
        # GiteaError out of the loop and turn into rc=2 (hard
        # abort), defeating the per-mirror-failed-result intent.
        # (Copilot R1)
        try:
            _validate_path_segment(mirror_name, kind="mirror_name")
        except GiteaError as exc:
            mirrors.append(
                MirrorResult(
                    name=mirror_name,
                    status="failed",
                    detail=f"path validation: {exc}",
                )
            )
            continue

        # Idempotent re-deploy: skip migration if mirror already exists.
        try:
            already_present = client.repo_exists(admin_username, mirror_name)
        except GiteaError:
            already_present = False

        if already_present:
            mirror_result = MirrorResult(
                name=mirror_name,
                status="already_exists",
                detail="GET /repos returned 200",
            )
        else:
            mirror_result = client.migrate_mirror(mirror_name, repo_url, admin_uid, gh_mirror_token)
        mirrors.append(mirror_result)

        if mirror_result.status == "failed":
            # Don't try to fork off a failed mirror; continue to next
            # iteration so a single bad URL doesn't abort the loop.
            continue

        # Grant the user read-only access to the (private) mirror BEFORE
        # the fork attempt below. ``migrate_mirror`` creates the repo with
        # ``"private": True``, and ``fork_repo_as_user`` runs as
        # ``gitea_user_username`` — without prior collaborator access the
        # user cannot see the mirror at all and Gitea returns 404 on
        # ``POST .../forks`` (Gitea conflates not-found with permission-
        # denied on private repos). Doing the add here guarantees the
        # user can see the mirror by the time the fork POST hits.
        if gitea_user_username and client.add_collaborator(
            admin_username, mirror_name, gitea_user_username, permission="read"
        ):
            collaborator_added_count += 1

        # Fork the FIRST successful mirror into the user's namespace
        # (idempotent across spin-ups via the existing-fork 409 branch).
        # On transient failure (token mint glitch, fork POST 5xx),
        # retry on the next mirror iteration. Without retry, a
        # single bad first mirror would prevent the fork on every
        # later mirror in the same loop too. (Copilot R3)
        if fork is None and gitea_user_username:
            sanitized = _sanitize_user_for_fork_name(gitea_user_username)
            fork_name = f"{orig_name}_{sanitized}"

            user_token = client.create_user_token(
                gitea_user_username,
                fork_token_name,
                ["all"],
                admin_username=admin_username,
                admin_password=admin_password,
            )
            if user_token is None:
                attempt: ForkResult = ForkResult(
                    name=fork_name,
                    owner=gitea_user_username,
                    status="failed",
                    detail="could not create user token for fork",
                )
            else:
                try:
                    fork_status = client.fork_repo_as_user(
                        admin_username,
                        mirror_name,
                        fork_name,
                        user_token=user_token,
                    )
                finally:
                    # Always cleanup the temp user-token regardless
                    # of fork outcome.
                    client.delete_user_token(
                        gitea_user_username,
                        fork_token_name,
                        admin_username=admin_username,
                        admin_password=admin_password,
                    )

                if fork_status == "202":
                    attempt = ForkResult(
                        name=fork_name,
                        owner=gitea_user_username,
                        status="created",
                        detail="POST 202",
                    )
                elif fork_status == "409":
                    attempt = ForkResult(
                        name=fork_name,
                        owner=gitea_user_username,
                        status="already_exists",
                        detail="POST 409",
                    )
                else:
                    attempt = ForkResult(
                        name=fork_name,
                        owner=gitea_user_username,
                        status="failed",
                        detail=f"POST {fork_status}",
                    )

            if attempt.status in ("created", "already_exists"):
                # Finalize — no more fork attempts on later iterations.
                fork = attempt
            else:
                # Transient failure: keep ``fork=None`` so the next
                # iteration retries. Save the most recent attempt's
                # diagnostic so the FINAL result still surfaces the
                # last failure if every iteration fails.
                last_fork_failure = attempt

        # Sync the fork from upstream — only on the first iteration
        # where the fork was actually created/already-existed.
        if fork is not None and fork.status in ("created", "already_exists") and not fork_synced:
            fork_synced = True  # set even if the chain below soft-fails
            # Step 1: snapshot the mirror's HEAD SHA so we can detect
            # when the upstream-fetch lands.
            before_sha = client.get_branch_head_sha(admin_username, mirror_name, workspace_branch)
            triggered = client.trigger_mirror_sync(admin_username, mirror_name)
            if not triggered:
                # Don't return early — the mirror may ALREADY be ahead
                # of the fork from (a) Gitea's periodic mirror cron-tick
                # that ran between spin-ups, or (b) the migrate that
                # ran a few seconds ago (which performs an initial
                # fetch as part of repo creation). Skipping merge here
                # would regress the legacy bash's best-effort behavior
                # for those cases. Record the trigger failure but
                # still try merge_upstream against whatever's currently
                # in the mirror.
                merge_status = client.merge_upstream(fork.owner, fork.name, workspace_branch)
                sync_detail = (
                    "trigger_mirror_sync returned non-200 (token / repo state); "
                    f"merge_upstream against current mirror HEAD: {merge_status}"
                )
            else:
                # Step 2: poll the mirror's branch HEAD until it changes
                # from the pre-sync snapshot. The previous fixed 3-second
                # sleep was too short for medium repos — GitHub's clone
                # finished but Gitea's mirror-fetch hadn't propagated by
                # the time merge_upstream ran, so the fork merged the OLD
                # mirror state and silently returned 409 "already up to
                # date". Polling catches a freshly-arrived commit even on
                # slow upstream fetches; the cap (mirror_sync_poll_seconds)
                # protects against a wedged mirror.
                deadline = time.monotonic() + mirror_sync_poll_seconds
                landed = False
                while time.monotonic() < deadline:
                    after_sha = client.get_branch_head_sha(
                        admin_username, mirror_name, workspace_branch
                    )
                    if after_sha is not None and after_sha != before_sha:
                        landed = True
                        break
                    time.sleep(mirror_sync_poll_interval_seconds)
                if landed:
                    # Sync landed (after_sha differed from before_sha,
                    # or before_sha was None but the poll observed any
                    # SHA) — merge fork from the now-updated mirror.
                    merge_status = client.merge_upstream(fork.owner, fork.name, workspace_branch)
                    sync_detail = (
                        f"mirror synced ({(before_sha or 'unknown')[:8]} -> "
                        f"{(after_sha or '')[:8]}), merge_upstream={merge_status}"
                    )
                elif before_sha is None:
                    # Mirror branch couldn't be read pre-sync (404 /
                    # transport) AND polling never observed a SHA
                    # either — we have no way to *verify* the sync,
                    # but the mirror may still be ahead of the fork
                    # from Gitea's periodic cron or the initial
                    # migrate-fetch. Best-effort merge so fork_synced
                    # (which is set unconditionally above) actually
                    # corresponds to an attempted merge call —
                    # otherwise the CLI would report "merge attempted"
                    # when nothing happened.
                    merge_status = client.merge_upstream(fork.owner, fork.name, workspace_branch)
                    sync_detail = (
                        "could not snapshot mirror HEAD before sync (no SHA observed during poll either); "
                        f"merge_upstream against current mirror HEAD: {merge_status}"
                    )
                else:
                    # Sync was triggered but the mirror's HEAD didn't
                    # move within the timeout. Could be: (a) upstream
                    # unchanged (legitimate no-op), or (b) Gitea's
                    # fetcher is wedged / token rejected. We still
                    # call merge_upstream — it'll return 409 in case
                    # (a), giving us a clean diagnostic.
                    merge_status = client.merge_upstream(fork.owner, fork.name, workspace_branch)
                    sync_detail = (
                        f"mirror HEAD unchanged after {mirror_sync_poll_seconds:.0f}s "
                        f"(before={(before_sha or '')[:8]}, "
                        f"merge_upstream={merge_status})"
                    )

    # If every fork attempt across the loop failed, surface the last
    # one's diagnostic in the final result so the operator can see WHY
    # the fork never succeeded. (Copilot R3 — without this, a multi-
    # mirror loop where every fork POST fails would return fork=None
    # which is indistinguishable from the no-user-configured branch.)
    if fork is None and last_fork_failure is not None:
        fork = last_fork_failure

    return MirrorSetupResult(
        admin_uid=admin_uid,
        admin_uid_error="",  # admin_uid resolved successfully
        mirrors=tuple(mirrors),
        fork=fork,
        collaborator_added_count=collaborator_added_count,
        fork_synced=fork_synced,
        sync_detail=sync_detail,
    )

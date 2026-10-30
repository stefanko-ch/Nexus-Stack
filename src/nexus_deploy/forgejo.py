"""Forgejo admin/user/repo configuration + Woodpecker OAuth + mirror setup.

Canonical Forgejo surface for the deploy pipeline. Three end-to-end
runners:

* :func:`run_configure_forgejo` — DB-password sync, admin user lifecycle
  (create or sync, with legacy email-collision PATCH for stacks
  deployed pre-v0.51.9), regular user lifecycle, API token creation
  with retry-via-delete on conflict, workspace repo creation with
  private-PATCH fallback, collaborator add.
* :func:`run_woodpecker_oauth_setup` — provisions the OAuth2 app
  Woodpecker CI uses to authenticate against Forgejo, returns
  client-id + client-secret for the Woodpecker .env writer.
* :func:`run_mirror_setup` — handles ``GH_MIRROR_REPOS`` mirror mode:
  per-mirror migrate into a read-only course repository, plus the
  user's own workspace repository.

Two transports, used deliberately:

- **CLI via ssh.run_script** for admin/user CRUD (list, create,
  change-password). Inside the forgejo container the ``forgejo admin user``
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
exec call: ``forgejo admin user create --password '<pw>'`` and
``psql -c "ALTER USER ... PASSWORD '<pw>'"`` are visible in
``ps -ef`` inside the relevant container while running. We feed
the rendered bash via ``ssh.run_script`` (stdin, not argv) so the
secret never lands in:
  - LOCAL ``ps`` on the deploy host
  - LOCAL CI logs (workflow argv-echoes the bash invocation only)
  - ``CalledProcessError.cmd`` / ``TimeoutExpired.cmd`` exception
    payloads

Tightening further (e.g. piping the password into ``forgejo admin user
create`` via stdin or ``--password-stdin``) is upstream-tooling-dependent.

R5 (path safety): all user/repo path segments are validated against
``^[a-zA-Z0-9._-]+$`` before URL interpolation OR shell-quoting.
Username/repo-name with shell metacharacters are rejected up front.
"""

from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass
from typing import Literal

import requests

from nexus_deploy.config import DEFAULT_ADMIN_USERNAME, NexusConfig, service_host
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


EXIT_NO_CONTAINER = 3
# Forgejo was there but never answered its health endpoint.
EXIT_NOT_READY = 4
# The database is up but would not take the generated password.
EXIT_DB_SYNC_FAILED = 5

# Forgejo usernames: alphanumerics plus dot/dash/underscore, not
# starting with punctuation. Deliberately narrower than what Forgejo
# accepts — these values also become shell words.
_USERNAME_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,38}\Z")
_EMAIL_PATTERN = re.compile(r"\A[^@\s]+@[^@\s]+\.[^@\s]+\Z")


def render_container_check(*, container: str = "forgejo") -> str:
    """Render the "is this container running" gate.

    Separate from the health poll because the account-provisioning path
    has to re-apply the database password *between* the two: a Forgejo
    that cannot reach its database never reports healthy, so polling
    first would time out on the very condition the sync repairs.

    **A docker daemon outage is not "nothing to do".** Piping ``docker
    ps`` straight into ``grep`` under ``pipefail`` collapses "the daemon
    is down" and "the container genuinely is not there" into the same
    exit, and reporting an outage as the harmless case hides real
    breakage. So the listing is captured first and a failure exits 1.
    """
    return f"""CONTAINER={shlex.quote(container)}

if ! RUNNING=$(docker ps --format '{{{{.Names}}}}' 2>&1); then
    echo "docker ps failed: $RUNNING" >&2
    exit 1
fi
if ! grep -qx -- "$CONTAINER" <<< "$RUNNING"; then
    echo "container $CONTAINER is not running" >&2
    exit {EXIT_NO_CONTAINER}
fi
"""


def render_health_poll(
    *,
    container: str = "forgejo",
    ready_attempts: int = 20,
    ready_interval: int = 3,
) -> str:
    """Render the "and Forgejo actually answers" wait.

    A running container is not a ready Forgejo: the process starts, then
    runs database migrations, and a ``forgejo admin`` or ``forgejo-cli``
    call landing in that window fails. Polling ``/api/healthz`` is the
    difference between a flaky first deploy and a reliable one — and it
    matters here specifically because nothing downstream retries these
    phases.
    """
    return f"""ready=""
for _ in $(seq 1 {ready_attempts}); do
    if docker exec "$CONTAINER" curl -sf http://localhost:3000/api/healthz >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep {ready_interval}
done
if [ -z "$ready" ]; then
    echo "forgejo did not answer /api/healthz within {ready_attempts * ready_interval}s" >&2
    exit {EXIT_NOT_READY}
fi
"""


def render_ready_preamble(
    *,
    container: str = "forgejo",
    ready_attempts: int = 20,
    ready_interval: int = 3,
) -> str:
    """Container check followed by the health poll, in one string.

    The combination used by :mod:`nexus_deploy.forgejo_runner`, which
    has no database step to slot between them. Sharing the two halves
    keeps the modules from drifting on what separates *skipped* from
    *failed*.
    """
    return (
        render_container_check(container=container)
        + "\n"
        + render_health_poll(
            container=container,
            ready_attempts=ready_attempts,
            ready_interval=ready_interval,
        )
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
    Dotted usernames like ``stefan.koch`` are allowed (Forgejo permits
    them — that's the dotted-username class from PR #464).
    """
    if not _PATH_SAFE_RE.fullmatch(value):
        raise ForgejoError(f"unsafe {kind}: {value!r}")
    if value in (".", ".."):
        raise ForgejoError(f"unsafe {kind}: {value!r}")


_USER_WORKSPACE_SANITIZE_RE: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9]")


def _sanitize_user_for_workspace_name(username: str) -> str:
    """Replace every non-alphanumeric char in ``username`` with ``_``.

    Used to derive the workspace name ``<orig>_<sanitized_user>``
    where the user's username may contain dots or hyphens that
    Forgejo allows in usernames but operators want flattened in repo
    names. The naming scheme is byte-stable so an existing workspace —
    including one that is still a fork from before — keeps matching.
    """
    return _USER_WORKSPACE_SANITIZE_RE.sub("_", username)


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
    """Column-exact awk-equivalent on ``forgejo admin user list`` output (R1).

    Forgejo CLI output:

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
    """Render bash to retry psql ALTER USER inside the forgejo-db container.

    Peer auth via ``-U nexus-forgejo`` (no ``-W``), so no PGPASSWORD env
    var is needed and the password value only enters the SQL string
    literal. The SCRIPT body (containing the SQL) is fed via stdin
    by the caller (``ssh.run_script``), so the password does NOT
    appear in:
      - LOCAL ``ps`` on the deploy host
      - LOCAL CI logs / ``CalledProcessError.cmd`` payloads
      - SSH argv on the deploy host

    The password DOES appear in the forgejo-db container's ``ps -ef``
    for the brief duration of the ``psql -c "ALTER USER … PASSWORD
    '<pw>'"`` call (since psql takes the SQL via argv). Tightening
    would require either ``\\password`` (interactive) or a server-
    side script feeding the SQL via stdin to psql, both of which
    add complexity for marginal gain on a runner-isolated container.

    A RESULT line is emitted on success so the caller can disambiguate
    "succeeded after N tries" from "all N tries failed".
    """
    sql = f"ALTER USER \"nexus-forgejo\" WITH PASSWORD '{escaped_pw}'"
    quoted_sql = shlex.quote(sql)
    return (
        "set -euo pipefail\n"
        f"for i in $(seq 1 {attempts}); do\n"
        f"  if docker exec forgejo-db psql -U nexus-forgejo -d forgejo "
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


MirrorStatus = Literal["created", "renamed", "already_exists", "failed"]
WorkspaceStatus = Literal["created", "already_exists", "failed"]

# Names of the read-only course mirrors. ``mirror-readonly-`` is the
# name they had while the user's workspace was a fork of them; an
# existing one is renamed on the next spin-up.
COURSE_REPO_PREFIX = "course-"
LEGACY_MIRROR_PREFIX = "mirror-readonly-"


@dataclass(frozen=True)
class MirrorResult:
    """One pull-mirror entry from the GH_MIRROR_REPOS loop.

    ``name`` is the Forgejo-side repo name (``course-<basename>``),
    NOT the upstream GitHub URL. ``status`` distinguishes the
    idempotent re-deploy paths: ``already_exists`` is a soft-success
    (the mirror was created on a previous spin-up), ``renamed`` means a
    ``mirror-readonly-<basename>`` from before was renamed, ``created`` means
    Forgejo ran the migration this call, ``failed`` means the migrate
    POST didn't return a usable id (caller routes to a yellow warning).
    """

    name: str
    status: MirrorStatus
    detail: str = ""


@dataclass(frozen=True)
class WorkspaceResult:
    """The user's workspace repository, ``<first basename>_<user>``.

    Exactly one per stack, ensured from the first successful mirror.
    ``status`` is ``created`` (POST 201), ``already_exists`` (POST 409 —
    from a previous spin-up, or a fork from before the workspace stopped
    being one) or ``failed``.

    The no-user-configured branch leaves
    :class:`MirrorSetupResult.workspace` as ``None``.
    """

    name: str
    owner: str
    status: WorkspaceStatus
    detail: str = ""


@dataclass(frozen=True)
class OAuthAppResult:
    """Result of creating a Forgejo OAuth2 application.

    Used for Woodpecker CI's Forgejo-as-forge OAuth flow.
    ``client_id`` and ``client_secret`` are emitted via stdout in
    eval-able form so the orchestrator can inject them into
    Woodpecker's ``.env`` before the container starts.
    """

    name: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class ForgejoResult:
    """Aggregate of all Forgejo-config sub-steps.

    ``token`` is None until :meth:`ForgejoCli.mint_token` succeeds (post-
    #519 fix switched from REST basic-auth to CLI peer-auth). The CLI
    handler emits ``FORGEJO_TOKEN=<token>`` to stdout iff token is
    non-None — eval-able by the orchestrator.
    """

    db_pw_synced: bool
    admin: CreateUserResult
    user: CreateUserResult | None
    token: str | None
    # Diagnostic message when ``token is None`` — empty string on
    # success. Captures the Forgejo-CLI-side error description so the
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
        ``FORGEJO_TOKEN=`` to stdout when ``token is not None`` — so on
        partial-failure paths where the token DID get minted (e.g.
        legacy email PATCH failed but token + repo OK), the caller
        captures the token via ``eval`` and downstream seed/kestra
        still work. On paths where token is None (token-mint failed)
        is_success is False AND no token line is emitted, so the
        caller sees rc=1 but no ``$FORGEJO_TOKEN``, and the seed/kestra
        blocks skip themselves on the empty-token guard.
        """
        if self.admin.status == "failed":
            return False
        if self.user is not None and self.user.status == "failed":
            return False
        if self.token is None:
            return False
        return not (self.repo is not None and self.repo.status == "failed")


class ForgejoError(Exception):
    """Transport/validation failure surfaced to the caller.

    Carries no response body — Forgejo error responses on auth-failure
    paths can echo back the credentials we just sent. Constructed
    from fixed format strings + status codes / type names only.
    """


# ---------------------------------------------------------------------------
# Hybrid client (post-#519 fix):
#   SSH CLI peer-auth: admin/user CRUD + token mint
#   REST basic-auth or token-auth: legacy email PATCH, repo CRUD, collab add
# Token minting moved from REST to CLI after the production
# 400-from-CreateAccessToken bug — see ForgejoCli.mint_token docstring.
# ---------------------------------------------------------------------------


class ForgejoCli:
    """SSH-driven ``docker exec forgejo`` CLI wrapper.

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

        On first start, forgejo-db can take ~10-30s to accept connections.
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
        """Run ``forgejo admin user list --admin`` and return raw output.

        Empty string if ssh/docker fails — the caller routes empty
        list to the CREATE branch, where any unexpected error
        surfaces on the next CLI call rather than spinning here.
        """
        # ``2>/dev/null`` keeps deprecated-flag warnings from polluting
        # the parsed output. ``|| echo ""`` swallows non-zero exit
        # (transient docker/forgejo startup race).
        result = self.ssh.run_script(
            "docker exec -u git forgejo forgejo admin user list --admin 2>/dev/null || echo ''",
            check=False,
            timeout=30.0,
        )
        return result.stdout if result.returncode == 0 else ""

    def list_users(self) -> str:
        """Run ``forgejo admin user list`` (non-admin scope)."""
        result = self.ssh.run_script(
            "docker exec -u git forgejo forgejo admin user list 2>/dev/null || echo ''",
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
        # `forgejo admin user create` accepts it directly.
        admin_flag = "--admin " if is_admin else ""
        script = (
            "set -euo pipefail\n"
            f"docker exec -u git forgejo forgejo admin user create {admin_flag}"
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
        # Forgejo returns "user already exists" / "email already in use" on
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
        """Generate API token via ``forgejo admin user generate-access-token``.

        Returns ``(sha1_or_None, diagnostic_message)``. On success the
        diagnostic is empty. On failure the diagnostic is a short
        Forgejo-side error description suitable for stderr — never
        password material.

        Idempotent: deletes any existing token with this name first
        (psql DELETE inside the forgejo-db container — peer auth, no
        password needed), then generates fresh. Two-pronged peer-
        auth approach because:

        1. Forgejo v1.23 CLI has NO ``delete-access-token`` subcommand
           (verified live: ``admin user`` only exposes create / list
           / change-password / delete-USER / generate-access-token).
           A previous attempt to use ``forgejo admin user
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
        # psql DELETE — peer auth via -U inside forgejo-db container.
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
        delete_script = f"docker exec forgejo-db psql -U nexus-forgejo -d forgejo -c {shlex.quote(delete_sql)} 2>&1\n"
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
            "docker exec -u git forgejo forgejo admin user generate-access-token "
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
        """``forgejo admin user change-password`` — peer-auth, no old password.

        Forgejo's CLI command takes the username + new password and
        updates the credential without requiring the previous one.
        Idempotent: running twice on the same password is a no-op.
        """
        _validate_path_segment(username, kind="username")
        script = (
            "set -euo pipefail\n"
            "docker exec -u git forgejo forgejo admin user change-password "
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


class ForgejoClient:
    """REST client for Forgejo. Basic-auth pre-token, token-auth post-token.

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
            raise ValueError("ForgejoClient requires non-empty admin credentials")
        _validate_path_segment(admin_username, kind="admin_username")
        self.base_url = base_url.rstrip("/")
        self.admin_username = admin_username
        self._auth: tuple[str, str] | None = (admin_username, admin_password)
        self._token: str | None = None

    @classmethod
    def from_token(cls, base_url: str, *, admin_username: str, token: str) -> ForgejoClient:
        """A token-only client, for callers that never need basic-auth."""
        if not token:
            raise ValueError("from_token requires a non-empty token")
        _validate_path_segment(admin_username, kind="admin_username")
        new = cls.__new__(cls)
        new.base_url = base_url.rstrip("/")
        new.admin_username = admin_username
        new._auth = None
        new._token = token
        return new

    def with_token(self, token: str) -> ForgejoClient:
        """Return a NEW client that uses token-auth instead of basic-auth.

        Token must be non-empty. Returns a separate instance so callers
        can't accidentally fall back to basic-auth on a client that's
        meant to be token-only.
        """
        if not token:
            raise ValueError("with_token requires a non-empty token")
        # New instance — copy URL + admin_username, drop basic-auth,
        # set token. Bypass __init__'s admin_password requirement.
        new = ForgejoClient.__new__(ForgejoClient)
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
        raise ForgejoError("client has no auth configured")  # pragma: no cover

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

        Forgejo's admin-users schema rejects partial bodies, so the
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
            raise ForgejoError(f"repo_exists transport ({type(exc).__name__})") from exc
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise ForgejoError(f"repo_exists HTTP {resp.status_code}")

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
        # Forgejo also returns 422 with "already exists" for some modes
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

        Used by the mirror-migrate flow: Forgejo's ``/api/v1/repos/migrate``
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
            raise ForgejoError(f"get_user_id transport ({type(exc).__name__})") from exc
        if resp.status_code == 404:
            # Genuine "user doesn't exist" — this is the only path
            # that returns None. Distinct from malformed-response
            # handling below which raises so the caller can surface
            # the diagnostic via admin_uid_error.
            return None
        if resp.status_code != 200:
            raise ForgejoError(f"get_user_id HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ForgejoError("get_user_id response was not JSON") from exc
        uid = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(uid, int):
            # 200 but the response shape is wrong (proxy mangling,
            # Forgejo schema drift). Raise so admin_uid_error surfaces
            # the diagnostic — without this, run_mirror_setup would
            # treat it as a genuine 404 and the CLI would print the
            # misleading "admin user not found in Forgejo". (Copilot R5)
            raise ForgejoError("get_user_id response missing integer 'id'")
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
        Forgejo to clone the (private) source repo; it travels in
        the request body as ``auth_token`` and is never logged
        locally or rendered into argv.

        Returns :class:`MirrorResult`:
        - ``status="created"`` on 200 OR 201 with a parseable
          integer ``id`` in the body. Forgejo v1.20+ documents 201
          for /repos/migrate, but we accept 200 too for forward-
          compat with older / forked Forgejo variants.
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

        Returns True on 200 (Forgejo queued the sync), False otherwise.
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

    def create_repo_for_user(
        self,
        username: str,
        name: str,
        *,
        private: bool = True,
        auto_init: bool = True,
        default_branch: str = "main",
        description: str = "",
    ) -> CreateRepoResult:
        """``POST /api/v1/admin/users/<u>/repos`` — create in the user's namespace.

        Needs an admin token. 409 → ``already_exists``: the repository is
        left exactly as it is, whatever it holds.
        """
        _validate_path_segment(username, kind="owner")
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
                f"{self.base_url}/api/v1/admin/users/{username}/repos",
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
        return CreateRepoResult(name=name, status="failed", detail=f"POST {resp.status_code}")

    def rename_repo(self, owner: str, name: str, new_name: str) -> bool:
        """``PATCH /api/v1/repos/<o>/<n>`` with ``{"name": new_name}``.

        Forgejo keeps a redirect from the old name, so links and remotes
        that still use it keep working.
        """
        _validate_path_segment(owner, kind="owner")
        _validate_path_segment(name, kind="repo_name")
        _validate_path_segment(new_name, kind="repo_name")
        try:
            resp = requests.patch(
                f"{self.base_url}/api/v1/repos/{owner}/{name}",
                json={"name": new_name},
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    # -------------------------------------------------------------------
    # OAuth2 application management (Woodpecker CI integration)
    # -------------------------------------------------------------------

    def list_oauth_apps(self) -> list[dict[str, object]]:
        """``GET /api/v1/user/applications/oauth2`` — list current user's apps.

        Returns the JSON array verbatim (each entry has ``id``, ``name``,
        ``redirect_uris``, etc. — but NO ``client_secret``; Forgejo only
        returns the secret on initial create). Empty list if the user
        has no OAuth apps. Raises :class:`ForgejoError` on transport /
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
            raise ForgejoError(f"list_oauth_apps transport ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise ForgejoError(f"list_oauth_apps HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ForgejoError("list_oauth_apps response was not JSON") from exc
        # Wrong shape (object instead of array) is a transport-level
        # anomaly — most likely an intermediate proxy returning an
        # error envelope, or a Forgejo schema change. Silently coercing
        # to ``[]`` would skip the rotation-delete and let the create
        # pile up duplicate apps — exactly the bug the rotation
        # contract is supposed to prevent. Raise instead. (Copilot R2)
        if not isinstance(payload, list):
            raise ForgejoError(
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
        "rotation NOT started" even when Forgejo may have already
        processed the DELETE before the error response was sent):

        - ``True``: Forgejo ACK'd the delete (204) or the app was
          already gone (404). Server state is KNOWN: app no longer
          exists.
        - ``False``: Forgejo returned a definitive 4xx (403 permission
          denied, 422 validation, etc.). 4xx semantics in REST are
          "client problem, server hasn't acted" → server state is
          KNOWN: app still exists. Caller can route to "rotation
          NOT started" with confidence.
        - ``raise ForgejoError``: ``requests`` couldn't deliver a
          response (ConnectionError, Timeout) OR Forgejo returned a
          5xx. In both cases server state is UNKNOWN — Forgejo may
          have processed the DELETE before the failure. Caller
          must treat as "rotation possibly started" and abort to
          avoid the stale-creds outage class. (Copilot R5)
        """
        if not isinstance(app_id, int) or app_id <= 0:
            raise ForgejoError(f"delete_oauth_app: invalid app_id {app_id!r}")
        try:
            resp = requests.delete(
                f"{self.base_url}/api/v1/user/applications/oauth2/{app_id}",
                timeout=_HTTP_TIMEOUT,
                **self._request_kwargs(),  # type: ignore[arg-type]
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise ForgejoError(
                f"delete_oauth_app(id={app_id}) transport ({type(exc).__name__})"
            ) from exc
        if resp.status_code in (204, 404):
            return True
        # 5xx: server-side failure — the DELETE may have been applied
        # before whatever broke broke. Same ambiguity class as a
        # transport timeout: treat as "rotation possibly started".
        if 500 <= resp.status_code < 600:
            raise ForgejoError(
                f"delete_oauth_app(id={app_id}) HTTP {resp.status_code} "
                "(server-side error, state ambiguous)"
            )
        # 4xx (or other unexpected codes): client-side problem,
        # Forgejo hasn't acted on the DELETE. Server state is known.
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
        ``client_id`` and ``client_secret``. Forgejo returns the secret
        ONLY on this initial create (subsequent ``GET`` lists hide it),
        so the caller must capture both values from this response and
        persist them immediately.

        Raises :class:`ForgejoError` on transport / non-201 / missing
        fields. Name + URIs are passed verbatim to Forgejo; both ``name``
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
            raise ForgejoError(f"create_oauth_app transport ({type(exc).__name__})") from exc
        if resp.status_code != 201:
            raise ForgejoError(f"create_oauth_app HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ForgejoError("create_oauth_app response was not JSON") from exc
        client_id = payload.get("client_id") if isinstance(payload, dict) else None
        client_secret = payload.get("client_secret") if isinstance(payload, dict) else None
        if not isinstance(client_id, str) or not client_id:
            raise ForgejoError("create_oauth_app response missing 'client_id'")
        if not isinstance(client_secret, str) or not client_secret:
            raise ForgejoError("create_oauth_app response missing 'client_secret'")
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


def run_configure_forgejo(
    config: NexusConfig,
    *,
    base_url: str,
    ssh: SSHClient,
    admin_email: str,
    forgejo_user_email: str | None,
    forgejo_user_password: str | None,
    repo_name: str,
    forgejo_repo_owner: str,
    is_mirror_mode: bool,
    enabled_services: list[str],
    ready_timeout_s: float = 60.0,
    db_sync_attempts: int = 15,
    db_sync_interval_s: float = 2.0,
) -> ForgejoResult:
    """End-to-end Forgejo configure runner.

    Steps:

    1. Sync forgejo-db postgres password (peer-auth psql ALTER USER)
    2. Wait for ``/api/healthz``
    3. Admin: list via CLI → exists?
       - yes + legacy email collision → REST PATCH email
       - yes → CLI sync_password
       - no  → CLI create_admin
    4. User (if ``forgejo_user_email``): list → exists?
       - yes → CLI sync_password
       - no  → CLI create_user
    5. Token: CLI ``mint_token`` (peer-auth ``generate-access-token``,
       idempotent delete-then-create; switched from REST in post-#519 fix)
    6. (non-mirror) repo: create → on already_exists → patch_repo_private
    7. (non-mirror, with user) collaborator add
    8. Build restart_services list (intersection with enabled)

    Returns :class:`ForgejoResult` with token in stdout-eval-able form
    via the CLI handoff. Even on partial failures (e.g. legacy email
    PATCH failed but token created), the token IS in the result so
    the orchestrator can capture it via eval.
    """
    admin_username = config.admin_username or DEFAULT_ADMIN_USERNAME
    admin_password = config.forgejo_admin_password or ""
    db_password = config.forgejo_db_password or ""

    cli = ForgejoCli(ssh)
    rest = ForgejoClient(
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

    # 2. Wait for Forgejo HTTP ready
    if not rest.wait_ready(timeout_s=ready_timeout_s):
        return ForgejoResult(
            db_pw_synced=db_pw_synced,
            # Use the configured admin_username (Copilot round 2) — not
            # the literal "admin" — so CreateUserResult.name carries
            # the same value across all paths regardless of how the
            # operator named the admin user.
            admin=CreateUserResult(
                name=admin_username, status="failed", detail="forgejo not ready"
            ),
            user=None,
            token=None,
            token_error="forgejo not ready",  # noqa: S106 — diagnostic, not a credential
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
    if admin_exists and forgejo_user_email and current_admin_email == forgejo_user_email:
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
    if forgejo_user_email and forgejo_user_password:
        user_username = forgejo_user_email.split("@", 1)[0]
        user_list = cli.list_users()
        user_exists, _ = _parse_admin_list_for_user(user_list, user_username)
        if user_exists:
            user_result = cli.sync_password(user_username, forgejo_user_password)
        else:
            user_result = cli.create_user(user_username, forgejo_user_password, forgejo_user_email)
            # Same already_exists → sync_password fallback as for admin.
            if user_result.status == "already_exists":
                user_result = cli.sync_password(user_username, forgejo_user_password)

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
            rest_token.patch_repo_private(forgejo_repo_owner, repo_name, private=True)
        if repo_result.status != "failed" and user_username is not None and forgejo_user_password:
            collaborator_added = rest_token.add_collaborator(
                forgejo_repo_owner, repo_name, user_username, permission="write"
            )

    return ForgejoResult(
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
    forgejo_token: str,
    admin_username: str,
    subdomain_separator: str = ".",
) -> tuple[OAuthAppResult | None, str, bool]:
    """End-to-end Woodpecker CI OAuth-app provisioning in Forgejo.

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

      - definitively ACK'd by Forgejo (204), OR
      - server-side state UNKNOWN (5xx response or transport
        timeout — Forgejo may have processed the DELETE before the
        failure surfaced)

      It is False when no delete reached the wire at all (list
      failed, no matching apps) OR when every attempted delete
      was definitively rejected by Forgejo (4xx with response — the
      app is KNOWN to still exist).

      The CLI handler uses this to dispatch:

      - True + result is None → rc=2 (abort): Forgejo state may have
        moved past the previous OAuth pair, deploy must stop or
        Woodpecker keeps running with possibly-invalidated creds.
      - False + result is None → rc=1 (warn-and-continue): Forgejo
        state untouched (or definitively rejected the rotation),
        Woodpecker's existing .env stays consistent.
      - True + result is set → rc=0: rotation completed cleanly.

      (Copilot R2 — initial flag; R5 — refined semantics for
      transport ambiguity, 5xx, and multi-app loop progress.)

    Auth: token-bearer (the FORGEJO_TOKEN minted in 2.2e/2.2e-fix).
    The list/delete/create endpoints all accept token auth as the
    authenticated user (admin in our case).
    """
    if not forgejo_token:
        return None, "FORGEJO_TOKEN is empty", False
    _validate_path_segment(admin_username, kind="admin_username")

    # ``with_token`` returns a new client that uses token-auth instead
    # of basic-auth. The placeholder password is never sent — see
    # :meth:`ForgejoClient.with_token`.
    client = ForgejoClient(
        base_url=base_url,
        admin_username=admin_username,
        admin_password="placeholder-not-used",  # noqa: S106
    ).with_token(forgejo_token)

    try:
        apps = client.list_oauth_apps()
    except ForgejoError as exc:
        # str(exc) is safe — ForgejoError messages are constructed from
        # fixed format strings + status codes only, never response bodies.
        return None, f"list_oauth_apps: {exc}", False

    # Find any existing app named exactly "Woodpecker CI" — Forgejo
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
                # Defensive: Forgejo's API contract returns integer ids,
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
            #   - True: Forgejo ACK'd, app gone → continue to create
            #   - False: Forgejo returned definitive non-success
            #     (4xx with response) → server state KNOWN, app
            #     still exists → rotation NOT started, safe to
            #     warn-and-continue (the existing .env stays
            #     consistent with Forgejo)
            #   - ForgejoError: transport timeout/reset OR 5xx →
            #     server state UNKNOWN, app may have been deleted
            #     before the response was lost → conservatively
            #     mark rotation_started=True so the CLI aborts
            try:
                deleted = client.delete_oauth_app(app_id)
            except ForgejoError as exc:
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
                # a creds pair Forgejo has already invalidated.
                # (Copilot R5)
                return (
                    None,
                    f"delete_oauth_app(id={app_id}): rejected by Forgejo — "
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
    except ForgejoError as exc:
        return None, f"create_oauth_app: {exc}", rotation_started


# ---------------------------------------------------------------------------
# Mirror-mode orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MirrorSetupResult:
    """Aggregate result of a GH_MIRROR_REPOS spin-up.

    Two kinds of repository come out of it, with separate roles:

    * one read-only **course** repository per URL, ``course-<basename>``,
      a pull mirror owned by the admin that Forgejo keeps current;
    * one **workspace** for the user, ``<first basename>_<user>``, an
      ordinary repository in the user's namespace where their work and
      the seeds live.

    The workspace used to be a fork of the first mirror. A fork carries
    the seeds as commits of its own from the first spin-up on, so it
    diverges from the mirror at once, and Forgejo 15 can then neither
    fast-forward it (``sync_fork`` refuses a diverged fork) nor merge
    into it (``merge-upstream`` is a Gitea route Forgejo does not have).
    Course updates therefore never reached the user. Keeping the course
    read-only and the workspace separate removes the need to merge at
    all. A workspace that is still such a fork is kept as it is — it is
    the user's work — and simply no longer synced.

    The CLI handler emits ``FORK_NAME=<name>`` + ``FORGEJO_REPO_OWNER=<owner>``
    on stdout when ``workspace`` reached ``created`` or ``already_exists``,
    so the orchestrator can seed it post-eval. The ``FORK_NAME`` key is
    kept for compatibility with that handoff.

    ``is_success`` is True iff every mirror reached ``created``,
    ``renamed`` or ``already_exists`` AND (if a workspace was attempted)
    it did too. The CLI maps False → rc=1 (yellow warn, deploy
    continues — next spin-up retries).
    """

    admin_uid: int | None
    # Diagnostic when admin_uid is None — distinguishes "user
    # genuinely doesn't exist (404)" from auth/5xx/transport
    # failures so the CLI can print the real cause instead of
    # the misleading "admin UID not found". Empty string when
    # admin_uid was successfully resolved. (Copilot R4)
    admin_uid_error: str
    mirrors: tuple[MirrorResult, ...]
    workspace: WorkspaceResult | None
    collaborator_added_count: int

    @property
    def is_success(self) -> bool:
        if self.admin_uid is None:
            return False
        if any(m.status == "failed" for m in self.mirrors):
            return False
        return not (self.workspace is not None and self.workspace.status == "failed")


def course_repo_name(repo_url: str) -> str:
    """The Forgejo name of the read-only course mirror for ``repo_url``."""
    return f"{COURSE_REPO_PREFIX}{_basename_no_git(repo_url)}"


def workspace_repo_name(repo_url: str, username: str) -> str:
    """The user's workspace name: ``<basename>_<sanitized user>``.

    Byte-identical to the name the fork used to get, so a stack whose
    workspace is still such a fork finds it under the same name.
    """
    return f"{_basename_no_git(repo_url)}_{_sanitize_user_for_workspace_name(username)}"


def run_mirror_setup(
    *,
    base_url: str,
    admin_username: str,
    forgejo_token: str,
    forgejo_user_username: str | None,
    gh_mirror_repos: list[str],
    gh_mirror_token: str,
) -> MirrorSetupResult:
    """End-to-end GH_MIRROR_REPOS provisioning.

    1. GET admin's UID (required by Forgejo's migrate API).
    2. For each repo URL in ``gh_mirror_repos``:
       a. Course name ``course-<basename>``. If it does not exist but
          the old ``mirror-readonly-<basename>`` does, rename that one
          (Forgejo keeps a redirect from the old name). Otherwise
          POST /repos/migrate, or skip when it already exists.
       b. Trigger a mirror sync, best effort, so the clones the
          containers make on this spin-up see the newest commit rather
          than the one from Forgejo's last scheduled fetch.
       c. Add the user as a **read** collaborator — the mirror is
          private, and a pull mirror refuses pushes anyway.
       d. For the FIRST successful mirror with a configured user,
          ensure the user's workspace ``<basename>_<user>`` exists as a
          private repository in the user's namespace. An existing one,
          including a fork from before this change, is left untouched.

    All admin actions use ``forgejo_token`` (token-bearer), which
    reaches REST as request-auth only, never argv.
    """
    # Path safety on admin_username — used in URL interpolation
    # immediately below.
    _validate_path_segment(admin_username, kind="admin_username")

    client = ForgejoClient.from_token(base_url, admin_username=admin_username, token=forgejo_token)

    # 1. Admin UID lookup. Failure → no migrate possible. Distinguish
    # three failure modes so the CLI can surface the real cause
    # instead of the misleading "admin UID not found" for every path
    # (Copilot R4):
    #   - get_user_id raises ForgejoError: auth/transport/5xx —
    #     stash exc message in admin_uid_error
    #   - get_user_id returns None: 404 (user genuinely doesn't
    #     exist) — admin_uid_error stays "" but admin_uid is None
    admin_uid: int | None = None
    admin_uid_error = ""
    try:
        admin_uid = client.get_user_id(admin_username)
    except ForgejoError as exc:
        # ForgejoError messages here are constructed from format
        # strings only (HTTP status / type names), no secrets —
        # safe to surface verbatim.
        admin_uid_error = str(exc)
    if admin_uid is None:
        return MirrorSetupResult(
            admin_uid=None,
            admin_uid_error=admin_uid_error,
            mirrors=(),
            workspace=None,
            collaborator_added_count=0,
        )

    mirrors: list[MirrorResult] = []
    workspace: WorkspaceResult | None = None
    last_workspace_failure: WorkspaceResult | None = None
    collaborator_added_count = 0

    for repo_url in gh_mirror_repos:
        repo_url = repo_url.strip()
        if not repo_url:
            continue
        orig_name = _basename_no_git(repo_url)
        mirror_name = course_repo_name(repo_url)
        legacy_name = f"{LEGACY_MIRROR_PREFIX}{orig_name}"

        # Validate the derived names BEFORE calling repo_exists /
        # migrate_mirror — both internally invoke
        # ``_validate_path_segment`` which raises ForgejoError on
        # unsafe values. Without this guard, one bad URL with
        # shell-meta chars in the basename (e.g.
        # ``.../repo?evil`` or ``.../repo;sh``) would propagate the
        # ForgejoError out of the loop and turn into rc=2 (hard
        # abort), defeating the per-mirror-failed-result intent.
        # (Copilot R1)
        try:
            _validate_path_segment(mirror_name, kind="mirror_name")
            _validate_path_segment(legacy_name, kind="mirror_name")
        except ForgejoError as exc:
            mirrors.append(
                MirrorResult(
                    name=mirror_name,
                    status="failed",
                    detail=f"path validation: {exc}",
                )
            )
            continue

        # Idempotent re-deploy: skip migration if the course repo exists.
        try:
            already_present = client.repo_exists(admin_username, mirror_name)
        except ForgejoError:
            already_present = False

        if already_present:
            mirror_result = MirrorResult(
                name=mirror_name,
                status="already_exists",
                detail="GET /repos returned 200",
            )
        else:
            try:
                legacy_present = client.repo_exists(admin_username, legacy_name)
            except ForgejoError:
                legacy_present = False
            if legacy_present:
                if client.rename_repo(admin_username, legacy_name, mirror_name):
                    mirror_result = MirrorResult(
                        name=mirror_name,
                        status="renamed",
                        detail=f"from {legacy_name}",
                    )
                else:
                    mirror_result = MirrorResult(
                        name=mirror_name,
                        status="failed",
                        detail=f"rename from {legacy_name} refused",
                    )
            else:
                mirror_result = client.migrate_mirror(
                    mirror_name, repo_url, admin_uid, gh_mirror_token
                )
        mirrors.append(mirror_result)

        if mirror_result.status == "failed":
            # Continue to next iteration so a single bad URL doesn't
            # abort the loop.
            continue

        # Best effort: a failed trigger only means the clones see the
        # commit from Forgejo's last scheduled fetch.
        client.trigger_mirror_sync(admin_username, mirror_name)

        if forgejo_user_username and client.add_collaborator(
            admin_username, mirror_name, forgejo_user_username, permission="read"
        ):
            collaborator_added_count += 1

        # The workspace is created once, from the first successful
        # mirror. On a transient failure, retry on the next iteration.
        if workspace is None and forgejo_user_username:
            name = workspace_repo_name(repo_url, forgejo_user_username)
            created = client.create_repo_for_user(
                forgejo_user_username,
                name,
                private=True,
                auto_init=True,
                default_branch="main",
                description="Your own work — course material is in the course repository",
            )
            attempt = WorkspaceResult(
                name=name,
                owner=forgejo_user_username,
                status=created.status,
                detail=created.detail,
            )
            if attempt.status in ("created", "already_exists"):
                workspace = attempt
            else:
                last_workspace_failure = attempt

    # If every workspace attempt failed, surface the last one's
    # diagnostic — otherwise the result would read like the
    # no-user-configured branch.
    if workspace is None and last_workspace_failure is not None:
        workspace = last_workspace_failure

    return MirrorSetupResult(
        admin_uid=admin_uid,
        admin_uid_error="",  # admin_uid resolved successfully
        mirrors=tuple(mirrors),
        workspace=workspace,
        collaborator_added_count=collaborator_added_count,
    )

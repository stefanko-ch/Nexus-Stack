"""Forgejo account provisioning.

Forgejo ships with ``INSTALL_LOCK`` and ``DISABLE_REGISTRATION`` both
on in this stack, which is the right posture for a server reachable
through Cloudflare Access — but it also means a fresh database has no
way to grow a first account. Without this module the web UI is locked
the moment the stack comes up, and the passwords OpenTofu generated and
pushed to Infisical belong to accounts that do not exist.

So this creates them, from inside the container, over the Forgejo CLI:

* the **admin** account, which owns the workspace repository and the
  automation token, and
* a **regular** account, which is what a student logs in as.

Both are idempotent. On a re-run the accounts already exist, so the
password is re-applied rather than the create failing — that also makes
this the repair path after a credential rotation, where the database
survived but every generated password changed.

WHY THE CLI AND NOT THE REST API. The API needs a password to
authenticate with, and on a fresh instance no password has been set
yet — the classic chicken-and-egg. ``forgejo admin`` runs inside the
container against the database directly and needs no HTTP identity at
all. :mod:`nexus_deploy.gitea` reaches the same conclusion for the same
reason.

ON PASSWORDS IN ARGV. ``forgejo admin user create`` takes the password
only as ``--password <value>``; upstream offers no stdin or file form,
exactly as with the runner's ``create-runner-file``. So the value is in
the *remote* ``docker exec`` argv for the duration of the call. The
script still travels over SSH stdin, so it never reaches local argv or
``CalledProcessError.cmd``, and observing the remote side needs
host-level Docker access. This matches what :mod:`nexus_deploy.gitea`
has always done; it is a constraint, not a choice.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Literal

from .ssh import SSHClient

# Account provisioning is two container execs against a local
# database. If it has not finished in two minutes the container is
# wedged and waiting longer will not help.
_CONFIGURE_TIMEOUT = 180.0

# A missing container is "nothing to do", not "something broke".
# Public because forgejo_runner shares the preamble that emits them —
# the two modules must agree on what each code means.
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


@dataclass(frozen=True)
class Account:
    """One account to provision."""

    username: str
    password: str
    email: str
    admin: bool = False


@dataclass(frozen=True)
class ConfigureResult:
    """Outcome of one provisioning run.

    ``detail`` is safe to log: it names accounts and what happened to
    them, never a password.
    """

    status: Literal["configured", "skipped", "failed"]
    detail: str


def _escape_sql_string_literal(value: str) -> str:
    """Escape a value for a single-quoted SQL string.

    Backslashes before quotes — the other order would double the quote
    escape for a password containing a literal backslash. Same helper
    as :mod:`nexus_deploy.gitea`.
    """
    return value.replace("\\", "\\\\").replace("'", "''")


def render_db_password_sync(
    password: str,
    *,
    container: str = "forgejo-db",
    role: str = "nexus-forgejo",
    database: str = "forgejo",
    attempts: int = 15,
    interval_s: float = 2.0,
) -> str:
    """Render bash that re-applies the generated password to the role.

    WHY THIS EXISTS AT ALL. ``POSTGRES_PASSWORD`` is read only when the
    container initialises an *empty* data directory. Forgejo's lives on
    a bind mount that the R2 persistence layer restores, so after a
    rebuild teardown the database comes back carrying the password from
    the previous generation — while an untargeted ``tofu destroy`` has
    rotated every ``random_*`` resource and handed Forgejo a new one.
    The forge then cannot authenticate to its own database.

    This was not a problem while Forgejo's data was ephemeral: the
    directory started empty every time and Postgres took the current
    password. Adding Forgejo to the persistence targets created the
    mismatch, and this closes it. :mod:`nexus_deploy.gitea` carries the
    same helper for the same reason.

    ORDERING MATTERS. This has to run before the health poll, not after
    it: a Forgejo that cannot reach its database never reports healthy,
    so waiting first would time out on a condition this call is what
    fixes.

    Peer auth via ``-U`` means no ``PGPASSWORD``; the value only enters
    the SQL literal. The script travels over SSH stdin, so the password
    never reaches local argv. It does appear in the *container's*
    process list for the duration of the ``psql -c`` call — the same
    trade gitea.py documents, and the same one the account CLI makes.
    """
    if not password:
        raise ValueError("empty password")
    sql = f"ALTER USER \"{role}\" WITH PASSWORD '{_escape_sql_string_literal(password)}'"
    return f"""# Re-apply the generated password to the restored role. A fresh
# database already has it; a restored one carries the previous
# generation's, which is the case this exists for.
for _ in $(seq 1 {attempts}); do
    if docker exec {shlex.quote(container)} psql -U {shlex.quote(role)} \
        -d {shlex.quote(database)} -c {shlex.quote(sql)} >/dev/null 2>&1; then
        db_synced=1
        break
    fi
    sleep {interval_s}
done
if [ -z "${{db_synced:-}}" ]; then
    echo "could not apply the database password after {attempts} attempts" >&2
    exit {EXIT_DB_SYNC_FAILED}
fi
"""


def is_valid_username(username: str) -> bool:
    """True when Forgejo will accept this as a username.

    Exposed so callers can decide *before* building a batch. The
    identity derivation upstream allows local parts that are valid
    e-mail but invalid usernames — `alice+tag@example.com` is the
    common one — and letting such a value reach
    :func:`render_configure_script` fails the whole batch, taking the
    admin account down with it.
    """
    return bool(_USERNAME_PATTERN.match(username))


def _validate(account: Account) -> None:
    if not _USERNAME_PATTERN.match(account.username):
        raise ValueError("invalid username")
    if not _EMAIL_PATTERN.match(account.email):
        raise ValueError("invalid email")
    if not account.password:
        raise ValueError("empty password")
    if "\n" in account.password or "\r" in account.password:
        # The password crosses into the container through `read -r`,
        # which stops at the first newline — a multi-line value would
        # be silently truncated and the account would get a password
        # nobody could reproduce. Generated passwords are alphanumeric,
        # so this is a guard against a future change, not today's data.
        raise ValueError("password contains a newline")


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
if ! printf '%s\\n' "$RUNNING" | grep -qx "$CONTAINER"; then
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


def render_configure_script(
    accounts: tuple[Account, ...],
    *,
    container: str = "forgejo",
    db_password: str = "",
) -> str:
    """Render the remote bash that provisions every account.

    When ``db_password`` is given, the role's password is re-applied
    first — see :func:`render_db_password_sync` for why that is needed
    and why it has to come before the health poll rather than after.
    """
    if not accounts:
        raise ValueError("no accounts to provision")
    for account in accounts:
        _validate(account)

    blocks: list[str] = []
    for account in accounts:
        admin_flag = " --admin" if account.admin else ""
        blocks.append(
            f"ensure_account {shlex.quote(account.username)} "
            f"{shlex.quote(account.password)} "
            f"{shlex.quote(account.email)}{admin_flag}\n"
        )

    db_sync = (
        render_db_password_sync(db_password, container=f"{container}-db") if db_password else ""
    )

    return f"""set -euo pipefail

{render_container_check(container=container)}
{db_sync}
{render_health_poll(container=container)}
# Column-exact parse, not a substring match. `admin user list` prints a
# header row and space-padded columns; a plain grep for the username
# would also match it as a substring of somebody else's name or email.
account_exists() {{
    docker exec -u git "$CONTAINER" forgejo admin user list \\
        | awk 'NR > 1 {{ print $2 }}' \\
        | grep -qxF "$1"
}}

# The password reaches the container on STDIN, never as an argument to
# `docker exec`. That is the project standard (see the argv-vs-stdin
# note in services.py): a value passed as `--password "$p"` out here
# lands in docker's argv on the HOST, visible to any local `ps`.
#
# `forgejo admin` has no password-stdin flag of its own, so the inner
# shell still hands it to forgejo as an argument — the same cost
# services.py accepts for Superset's `fab create-admin`. The host-level
# surface is what this buys, and that is the surface that matters here.
ensure_account() {{
    username=$1
    password=$2
    email=$3
    admin_flag=${{4:-}}
    if account_exists "$username"; then
        printf '%s' "$password" | docker exec -i -u git "$CONTAINER" sh -c '
            IFS= read -r p || true
            exec forgejo admin user change-password \\
                --username "$1" --password "$p" --must-change-password=false
        ' _ "$username" >/dev/null
        echo "  = $username (password synced)"
    else
        printf '%s' "$password" | docker exec -i -u git "$CONTAINER" sh -c '
            IFS= read -r p || true
            # shellcheck disable=SC2086 — $3 is empty or the literal
            # --admin, and must not become an empty argument.
            exec forgejo admin user create $3 \\
                --username "$1" --password "$p" --email "$2" \\
                --must-change-password=false
        ' _ "$username" "$email" "$admin_flag" >/dev/null
        echo "  + $username (created)"
    fi
}}

{"".join(blocks)}"""


def run_configure(
    ssh: SSHClient,
    accounts: tuple[Account, ...],
    *,
    container: str = "forgejo",
    db_password: str = "",
    timeout: float = _CONFIGURE_TIMEOUT,
) -> ConfigureResult:
    """Provision the accounts on the running Forgejo. Idempotent."""
    try:
        script = render_configure_script(accounts, container=container, db_password=db_password)
    except ValueError as exc:
        # Category, not message: the inputs include a password, and a
        # future validation change should not be able to turn this into
        # a leak. The distinct exit paths below carry the diagnosis.
        return ConfigureResult(status="failed", detail=f"validation ({type(exc).__name__})")

    try:
        proc = ssh.run_script(script, check=False, timeout=timeout, merge_stderr=True)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ConfigureResult(status="failed", detail=f"transport ({type(exc).__name__})")

    if proc.returncode == EXIT_NO_CONTAINER:
        return ConfigureResult(status="skipped", detail="forgejo container not running")
    if proc.returncode == EXIT_DB_SYNC_FAILED:
        return ConfigureResult(
            status="failed",
            detail="could not apply the database password to the restored role",
        )
    if proc.returncode == EXIT_NOT_READY:
        return ConfigureResult(status="failed", detail="forgejo did not become healthy")
    if proc.returncode != 0:
        return ConfigureResult(status="failed", detail=f"forgejo admin exited {proc.returncode}")

    names = ", ".join(a.username for a in accounts)
    return ConfigureResult(status="configured", detail=f"accounts={names}")

"""Server-side half of the Forgejo Actions runner registration.

Forgejo offers two ways to pair a runner with an instance:

*Token registration* — an operator clicks through Site Administration →
Actions → Runners, copies a token, and pastes it into the runner. The
tokens are single-use. That is fine for one runner tended by hand and
useless for a platform that rebuilds a stack on every spin-up.

*Offline registration* — the same 40-hex-character secret is handed to
both sides independently. The server learns it via ``forgejo-cli
actions register``; the runner writes its credentials file from it via
``forgejo-runner create-runner-file``. Neither call contacts the other,
so ordering does not matter, and re-running either one with the same
secret is a no-op.

This module is the server half. The runner half lives in the runner
container's entrypoint (``stacks/forgejo/docker-compose.yml``), and the
secret both read comes from ``random_id.forgejo_runner_secret``.

TWO PLACES THE SECRET MUST NOT APPEAR, and how each is avoided:

1. **Local argv.** The secret is embedded in the rendered script, and
   the script goes to :meth:`SSHClient.run_script`, which feeds it over
   stdin. ``ps`` and ``CalledProcessError.cmd`` see only
   ``ssh <host> bash -s``. Same approach as
   :mod:`nexus_deploy.secret_sync`.
2. **Remote argv.** Hence ``--secret-stdin`` rather than ``--secret
   <value>``, piped from ``printf``. ``printf`` is a shell builtin, so
   no process is created carrying the value, and the exec's own
   ``/proc/<pid>/cmdline`` ends at ``--secret-stdin``.

Neither concern is theoretical here: the repository is public and its
CI logs are world-readable.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Literal

from .ssh import SSHClient

# Registration is a local database write behind a container exec. Two
# minutes is generous; anything slower means the container is wedged
# and waiting longer will not help.
_REGISTER_TIMEOUT = 120.0

# Forgejo requires exactly this: 40 lowercase hex characters, the first
# 16 being the runner's identifier and the rest the secret proper.
_SECRET_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")

# A distinct exit code so the caller can tell "nothing to do" from
# "something is broken" without parsing prose.
_EXIT_NO_CONTAINER = 3

# Conservative: what Forgejo accepts as a runner name is broader, but
# these values also end up in shell words and in the Actions UI, and
# nothing in this project needs punctuation beyond dot/dash/underscore.
_NAME_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z")
_SCOPE_PATTERN = re.compile(
    r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,62}(/[A-Za-z0-9][A-Za-z0-9._-]{0,62})?\Z"
)


@dataclass(frozen=True)
class RegisterResult:
    """Outcome of one registration attempt.

    ``detail`` is safe to log and to surface in a PhaseResult — it never
    contains the secret, only a shape complaint or an exit code.
    """

    status: Literal["registered", "skipped", "failed"]
    detail: str


def render_register_script(
    *,
    secret: str,
    name: str,
    scope: str = "",
    container: str = "forgejo",
) -> str:
    """Render the remote bash, secret included.

    The secret genuinely has to be in the script body. The alternative —
    keeping the rendered text clean and sending the value on stdin —
    cannot work: ``run_script`` already occupies stdin with the script
    itself, so a ``cat`` inside the script would read an empty stream.
    Embedding it is safe for the same reason ``secret_sync`` does it:
    the whole script travels over stdin and never becomes an argument.

    ``scope`` narrows the runner to one owner or ``owner/repo``. Empty
    means an instance-wide runner, which is Forgejo's default and the
    right choice while Forgejo hosts nothing but its own repositories.
    """
    if not _SECRET_PATTERN.match(secret):
        raise ValueError("secret must be exactly 40 lowercase hex characters")
    if not _NAME_PATTERN.match(name):
        raise ValueError(f"invalid runner name: {name!r}")
    if scope and not _SCOPE_PATTERN.match(scope):
        raise ValueError(f"invalid runner scope: {scope!r}")

    scope_line = f'set -- "$@" --scope {shlex.quote(scope)}\n' if scope else ""

    return f"""set -euo pipefail

CONTAINER={shlex.quote(container)}

# A missing container is not a failure — Forgejo may simply not be
# enabled on this stack, or may still be starting. Say so with a
# distinct exit code and let the caller decide.
if ! docker ps --format '{{{{.Names}}}}' | grep -qx "$CONTAINER"; then
    echo "container $CONTAINER is not running" >&2
    exit {_EXIT_NO_CONTAINER}
fi

set -- actions register --name {shlex.quote(name)}
{scope_line}
# printf is a shell builtin: the secret never becomes a process
# argument on this side either, and --secret-stdin keeps it out of the
# exec's own command line.
printf '%s' {shlex.quote(secret)} \\
    | docker exec -i -u git "$CONTAINER" forgejo forgejo-cli "$@" --secret-stdin
"""


def run_register(
    ssh: SSHClient,
    *,
    secret: str,
    name: str = "nexus-runner",
    scope: str = "",
    container: str = "forgejo",
    timeout: float = _REGISTER_TIMEOUT,
) -> RegisterResult:
    """Register the runner with the Forgejo instance. Idempotent.

    Re-running with an unchanged secret is a no-op on Forgejo's side,
    which is what makes this safe to call on every spin-up rather than
    only on first deploy.
    """
    try:
        script = render_register_script(
            secret=secret,
            name=name,
            scope=scope,
            container=container,
        )
    except ValueError as exc:
        # str(exc) is built from the shape of the input, never its
        # value — see the raises in render_register_script. A wrong
        # length is the likely symptom of a mis-wired tofu output, and
        # is exactly what an operator needs told.
        return RegisterResult(status="failed", detail=str(exc))

    try:
        proc = ssh.run_script(script, check=False, timeout=timeout, merge_stderr=True)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return RegisterResult(status="failed", detail=f"transport ({type(exc).__name__})")

    if proc.returncode == _EXIT_NO_CONTAINER:
        return RegisterResult(status="skipped", detail="forgejo container not running")
    if proc.returncode != 0:
        return RegisterResult(
            status="failed",
            detail=f"forgejo-cli exited {proc.returncode}",
        )
    return RegisterResult(
        status="registered",
        detail=f"name={name} scope={scope or 'instance-wide'}",
    )

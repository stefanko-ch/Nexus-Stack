"""Server-side half of the Forgejo Actions runner registration.

Forgejo v15 offers three ways to pair a runner with an instance —
interactive, over the HTTP API, and offline. Only the last one fits
here.

*Interactive and API registration* both hand out a token an operator
then gives to the runner: through Site Administration → Actions →
Runners, or by driving the same endpoint programmatically. Both need
somebody, or something, holding an authenticated session at the moment
of registration. That is fine for one runner tended by hand and
useless for a platform that rebuilds a stack on every spin-up.

*Offline registration* — the same 40-hex-character secret is handed to
both sides independently. The server learns it via ``forgejo-cli
actions register``; the runner writes its credentials file from it via
``forgejo-runner create-runner-file``. Neither call contacts the other,
so ordering does not matter, and re-running either one with the same
secret is a no-op.

This module is the server half. The runner half lives in the runner
container's entrypoint (``stacks/forgejo-runner/docker-compose.yml``), and the
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

from .forgejo import EXIT_NO_CONTAINER, EXIT_NOT_READY, render_ready_preamble
from .ssh import SSHClient

# Registration is a local database write behind a container exec. Two
# minutes is generous; anything slower means the container is wedged
# and waiting longer will not help.
_REGISTER_TIMEOUT = 120.0

# Forgejo requires exactly this: 40 lowercase hex characters, the first
# 16 being the runner's identifier and the rest the secret proper.
_SECRET_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")

# Conservative: what Forgejo accepts as a runner name is broader, but
# these values also end up in shell words and in the Actions UI, and
# nothing in this project needs punctuation beyond dot/dash/underscore.
_NAME_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z")

# The labels this runner advertises, and the reason they are here
# rather than only in runner-config.yml.
#
# Offline registration writes the server's runner record from
# `forgejo-cli actions register`. A record created without `--labels`
# has none — and the server matches a workflow's `runs-on:` against
# the record, not against whatever the daemon later reads from its own
# config. So a runner can sit there green and idle while every job
# queues forever against a label nobody declared. That is exactly what
# the first live deploy showed: connected, idle, Labels column empty.
#
# `runner-config.yml` carries the same list for the daemon's own use;
# a test asserts the two stay identical, because drift between them is
# silent in precisely this way.
#
# Three names, one image, deliberately: `docker` is the Forgejo-native
# label, and the two `ubuntu-*` aliases exist so a workflow copied from
# GitHub with `runs-on: ubuntu-latest` is picked up instead of hanging.
DEFAULT_RUNNER_LABELS: tuple[str, ...] = (
    "docker:docker://node:22-bookworm",
    "ubuntu-latest:docker://node:22-bookworm",
    "ubuntu-22.04:docker://node:22-bookworm",
)

# A label is `<name>:<backend>://<image>` or `<name>:host`. Kept
# deliberately loose on the value side and strict on the separator, so
# a malformed entry is caught here rather than by the remote CLI.
_LABEL_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._:/+-]*\Z")
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
    labels: tuple[str, ...] = DEFAULT_RUNNER_LABELS,
    attempts: int = 3,
    interval: int = 5,
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
    for label in labels:
        if not _LABEL_PATTERN.match(label):
            raise ValueError(f"invalid runner label: {label!r}")

    scope_line = f'set -- "$@" --scope {shlex.quote(scope)}\n' if scope else ""
    labels_line = f'set -- "$@" --labels {shlex.quote(",".join(labels))}\n' if labels else ""

    return f"""set -euo pipefail

{render_ready_preamble(container=container)}
set -- actions register --name {shlex.quote(name)}
{scope_line}{labels_line}
# Bounded retry, because nothing downstream repairs this. The runner
# keeps restarting until the server knows the secret, but the server
# only learns it here — so a single transient failure would leave a
# runner that can never authenticate. Registration is idempotent, so
# repeating it costs nothing.
attempt=1
while :; do
    # printf is a shell builtin: the secret never becomes a process
    # argument on this side, and --secret-stdin keeps it out of the
    # exec's own command line.
    #
    # The `=1` is not a typo and not the secret. Forgejo declares
    # `secret-stdin` as a cli.StringFlag rather than a BoolFlag, so the
    # parser demands a value — but the implementation only calls
    # `IsSet("secret-stdin")` and then reads the actual secret from
    # stdin, discarding whatever the flag was given. Passing the bare
    # flag fails with "flag needs an argument"; passing a placeholder
    # is the only way to reach the stdin path.
    if printf '%s' {shlex.quote(secret)} \\
        | docker exec -i -u git "$CONTAINER" forgejo forgejo-cli "$@" --secret-stdin=1
    then
        break
    fi
    if [ "$attempt" -ge {attempts} ]; then
        echo "forgejo-cli actions register failed after $attempt attempt(s)" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep {interval}
done
"""


def run_register(
    ssh: SSHClient,
    *,
    secret: str,
    name: str = "nexus-runner",
    scope: str = "",
    container: str = "forgejo",
    labels: tuple[str, ...] = DEFAULT_RUNNER_LABELS,
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
            labels=labels,
        )
    except ValueError as exc:
        # Category, not message. The project rule is `type(exc).__name__`
        # rather than `str(exc)` in error output, and it applies even
        # though these particular messages are shape-only: the rule
        # exists so a later validation change cannot quietly turn this
        # into a leak. The shape check below keeps the diagnosis.
        return RegisterResult(
            status="failed",
            detail=f"validation ({type(exc).__name__}): secret/name/scope rejected",
        )

    try:
        proc = ssh.run_script(script, check=False, timeout=timeout, merge_stderr=True)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return RegisterResult(status="failed", detail=f"transport ({type(exc).__name__})")

    if proc.returncode == EXIT_NO_CONTAINER:
        return RegisterResult(status="skipped", detail="forgejo container not running")
    if proc.returncode == EXIT_NOT_READY:
        return RegisterResult(status="failed", detail="forgejo did not become healthy")
    if proc.returncode != 0:
        return RegisterResult(
            status="failed",
            detail=f"forgejo-cli exited {proc.returncode}",
        )
    return RegisterResult(
        status="registered",
        detail=f"name={name} scope={scope or 'instance-wide'} labels={len(labels)}",
    )

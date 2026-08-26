"""Per-service ``docker compose restart`` loop.

Server-side ssh-loop ``cd $REMOTE_STACKS_DIR/$SVC && docker compose
restart`` over a list of service names. Used by two orchestrator
phases:

* ``_phase_compose_restart`` — post-forgejo git-restart of services
  that integrate with Forgejo (consumes ``state.restart_services``)
* ``_phase_mirror_finalize`` — mirror-mode git-restart loop that
  picks up the latest fork content for jupyter / marimo /
  code-server / meltano / prefect

Kept separate from :mod:`compose_runner`: that module's single
responsibility is the parallel compose-up + docker-ps verification;
a sequential restart loop is a different lifecycle operation.

Exit-code semantics mirror ``compose_runner``:

* RESULT line shape: ``RESULT restarted=N failed=M``
* Empty input → noop, RESULT 0/0 (skip the ssh round-trip entirely)
* Per-service failure adds 1 to ``failed`` but doesn't abort the loop
  (restart failures are non-blocking; the operator sees the warning
  in stderr)
* Transport / parse failure → :class:`RestartResult` with
  ``failed=len(services)``, mirroring compose_runner's defensive
  fall-through pattern.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from . import _remote

# Server-side stacks dir. Same constant as compose_runner — kept as a
# local copy to avoid cross-module coupling for what is conceptually
# a deployment constant.
_REMOTE_STACKS_DIR = "/opt/docker-server/stacks"

# RESULT-line shape — same wire-format family as compose_runner /
# secret_sync / seeder: ``RESULT key=value key=value``.
_RESULT_PATTERN = re.compile(
    r"^RESULT restarted=(?P<restarted>\d+) failed=(?P<failed>\d+)$",
    re.MULTILINE,
)

ScriptRunner = Callable[[str], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RestartResult:
    """Counters parsed from the remote RESULT line.

    ``restarted`` = services where ``docker compose restart`` exited 0.
    ``failed``    = services where it exited non-zero, OR services
                    whose stack directory didn't exist on the server
                    (counted as failed so a typo in the input list
                    surfaces as a visible warning rather than a silent
                    skip).
    """

    restarted: int
    failed: int

    @property
    def is_success(self) -> bool:
        """True iff zero failures."""
        return self.failed == 0


def render_remote_script(services: list[str]) -> str:
    """Render the bash that the server runs via stdin.

    For each service in ``services`` (already filtered + de-duped by
    the caller), the script:

    1. Checks the stack directory exists. Missing dir → counts as
       failed (typo / disabled-but-still-listed). Same fail-fast
       contract as compose_runner's missing-compose-yml branch.
    2. Runs ``docker compose restart`` with stderr+stdout merged. A
       non-zero rc increments the failure counter; we don't abort the
       loop (different services are independent).
    3. Emits one ``RESULT`` line at the end with the counters; deploy
       parses this to typed counters.
    """
    if not services:
        # Empty input → emit RESULT 0/0 directly. Same script template
        # works even with zero services (the for-loop body never
        # runs), but explicitly short-circuiting saves an ssh round-
        # trip in the common case (no git-integrated services
        # enabled / no RESTART_SERVICES emitted).
        return "echo 'RESULT restarted=0 failed=0'\n"

    services_quoted = " ".join(f"'{s}'" for s in services)
    # PR #533 R1 #5: suppress docker compose's normal output. Only
    # emit the concise per-service ✓/✗ lines; on failure, capture
    # docker compose's stderr for the operator. Matches the legacy
    # bash `>/dev/null 2>&1 || true` semantics — restart loops
    # produce minimal log output by default.
    return f"""\
set -u
STACKS_DIR={_REMOTE_STACKS_DIR}
RESTARTED=0
FAILED=0
COMPOSE_ERR=$(mktemp)
trap 'rm -f "$COMPOSE_ERR"' EXIT HUP INT TERM
for SVC in {services_quoted}; do
    if [ ! -d "$STACKS_DIR/$SVC" ]; then
        echo "  ✗ Restart $SVC: stack directory missing on server" >&2
        FAILED=$((FAILED + 1))
        continue
    fi
    if (cd "$STACKS_DIR/$SVC" && docker compose restart) >/dev/null 2>"$COMPOSE_ERR"; then
        echo "  ✓ Restarted $SVC"
        RESTARTED=$((RESTARTED + 1))
    else
        echo "  ✗ Restart $SVC: docker compose restart returned non-zero" >&2
        # Only print compose stderr on failure so operators can
        # diagnose; the success path stays quiet.
        if [ -s "$COMPOSE_ERR" ]; then
            sed 's/^/      /' "$COMPOSE_ERR" >&2
        fi
        FAILED=$((FAILED + 1))
    fi
    : > "$COMPOSE_ERR"
done
echo "RESULT restarted=$RESTARTED failed=$FAILED"
"""


def parse_result(stdout: str) -> RestartResult | None:
    """Defensive RESULT-line parser.

    Returns None if no RESULT line was found, mirroring the
    compose_runner / seeder pattern. The caller treats ``None`` as
    ``RestartResult(restarted=0, failed=len(services))`` (every
    requested restart counted as failed, since we have no proof
    any of them succeeded).
    """
    match = _RESULT_PATTERN.search(stdout)
    if match is None:
        return None
    return RestartResult(
        restarted=int(match.group("restarted")),
        failed=int(match.group("failed")),
    )


def run_restart(
    services: list[str],
    *,
    host: str = "nexus",
    script_runner: ScriptRunner | None = None,
) -> RestartResult:
    """Render → exec → parse the per-service docker-compose-restart loop.

    Returns ``RestartResult(restarted=0, failed=0)`` on empty input
    (noop short-circuit; no ssh round-trip).

    On transport / parse failure, returns
    ``RestartResult(restarted=0, failed=len(services))`` so the caller
    sees every requested restart as failed (mirrors compose_runner's
    defensive contract).

    ``host`` selects the ssh-config alias (default ``"nexus"``;
    orchestrator passes ``self.ssh_host`` so a non-default
    ``SSH_HOST_ALIAS`` reaches the restart loop too — same plumbing
    pattern as PR #532 R2 #2 + R4 #1).

    ``script_runner`` is the DI seam for tests; production callers
    leave it None and get :func:`_remote.ssh_run_script`.
    """
    if not services:
        return RestartResult(restarted=0, failed=0)

    script = render_remote_script(services)
    # PR #533 R3 #3: default runner uses ``check=False`` so an ssh
    # transport failure (network blip, expired CF Access token, host
    # down) returns a CompletedProcess with non-zero rc instead of
    # raising CalledProcessError. The RESULT-line parser then sees no
    # parseable line and the function returns
    # ``RestartResult(failed=len(services))``. The orchestrator
    # converts that to ``status='partial'`` (best-effort restart-loop
    # semantics — same as the legacy bash ``|| true``). With
    # ``check=True``, an exception would have aborted the entire
    # post-bootstrap pipeline; behavior change vs legacy.
    runner = script_runner or (lambda s: _remote.ssh_run_script(s, host=host, check=False))
    completed = runner(script)

    # Forward per-service ✓/✗ lines to local stderr — same
    # Modul-1.2 round-4 pattern as compose_runner / secret_sync.
    # The RESULT line itself is filtered out.
    for line in completed.stdout.splitlines():
        if not line.startswith("RESULT "):
            sys.stderr.write(line + "\n")

    result = parse_result(completed.stdout)
    if result is None:
        # No RESULT line = remote script broke before the final echo,
        # OR ssh transport failed (with check=False, that's also a
        # non-zero rc but no RESULT). Treat every requested service as
        # failed so the caller surfaces this as a partial / failed
        # PhaseResult — best-effort semantics matching legacy bash.
        return RestartResult(restarted=0, failed=len(services))
    return result

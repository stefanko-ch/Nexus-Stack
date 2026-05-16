"""Parallel ``docker compose up`` runner.

Walks the enabled-services list, expands virtual services to their
parent stacks, starts each stack via ``docker compose up -d --build``
in parallel via bash ``&``/``wait``, and verifies each container made
it into ``docker ps``.

Server-side bash loop, consistent with :mod:`infisical` /
:mod:`secret_sync` / :mod:`seeder`: one SSH round-trip; the rendered
script is testable as a string.

Eight rounds of hardening preserved (one regression test per round in
``tests/unit/test_compose_runner.py``):

R1. ``set -euo pipefail`` first executable line.
R2. Per-stack firewall override applied when
    ``docker-compose.firewall.yml`` exists on the server.
R3. Background-jobs + ``wait`` for parallel deploy; failed PIDs
    surface via the per-service exit code.
R4. ``docker ps`` verification — a container that ``compose up``
    "succeeded" but didn't actually start (e.g. immediate exit due
    to bad config) is counted as failed.
R5. Virtual-service deduplication: a parent stack started for one
    virtual service is NOT started a second time when another
    virtual service from the same parent appears.
R6. Deferred services skipped (woodpecker — depends on Gitea OAuth
    credentials, started by the post-bootstrap pipeline).
R7. ``set -a`` + ``source /opt/docker-server/stacks/.env`` exports
    image-version pins to the compose-up environment.
R8. RESULT line emitted at end with started/failed counts; orchestrator
    parses it instead of grepping stdout for emoji.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from nexus_deploy import _remote

# Hardcoded deploy-config: parent-stack mapping and deferred services.
# New stacks that fit one of the two patterns get added here.
#
# ``_VIRTUAL_SERVICES`` is derived from ``_STACK_PARENTS.keys()``
# rather than maintained as a separate frozenset so the two can't
# drift — previously they were both manually listed and a round-4
# review pointed out the duplication risk (a service could be treated
# as virtual yet have no parent mapping → skipped from leaves AND
# from parents → silently never started).
_STACK_PARENTS: dict[str, str] = {
    "seaweedfs-filer": "seaweedfs",
    "seaweedfs-manager": "seaweedfs",
}
_VIRTUAL_SERVICES: frozenset[str] = frozenset(_STACK_PARENTS.keys())
_DEFERRED_SERVICES: frozenset[str] = frozenset({"woodpecker"})

# Server-side stacks dir.
_REMOTE_STACKS_DIR = "/opt/docker-server/stacks"

# Server-side env file with image-version pins; sourced into the
# compose-up environment via `set -a; source ...; set +a`.
_REMOTE_GLOBAL_ENV = "/opt/docker-server/stacks/.env"

# RESULT-line shape (same wire-format family as infisical / secret_sync
# / seeder — `RESULT key=value key=value`). started/failed are counts;
# the human-readable per-service status reaches the operator via stderr
# warnings forwarded from the remote loop.
_RESULT_PATTERN = re.compile(
    r"^RESULT started=(?P<started>\d+) failed=(?P<failed>\d+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ComposeUpResult:
    """Counters parsed from the remote ``RESULT`` line.

    ``started`` counts services that both reported ``compose up``
    success AND were observed in ``docker ps`` afterwards (R4
    invariant). ``failed`` counts everything else: compose-up
    non-zero exit, container missing from ``docker ps`` post-up,
    missing ``docker-compose.yml`` for an enabled service.
    """

    started: int
    failed: int

    @property
    def is_success(self) -> bool:
        """True iff zero failures."""
        return self.failed == 0


# ---------------------------------------------------------------------------
# Pure-logic helpers — virtual-service resolution.
# ---------------------------------------------------------------------------


def expand_targets(enabled: list[str]) -> tuple[list[str], list[str]]:
    """Resolve the enabled list into (parent_stacks, leaf_stacks).

    Parent stacks are derived from the ``_STACK_PARENTS`` map for any
    virtual service in ``enabled``. Each parent is added once even if
    multiple virtual children are enabled (R5). Leaf stacks are the
    remaining services minus virtuals, parents-already-included, and
    deferred services (R6).

    Returns the two lists in source order so operators can correlate
    the per-service log lines with the input order.
    """
    parents: list[str] = []
    seen_parents: set[str] = set()
    for svc in enabled:
        parent = _STACK_PARENTS.get(svc)
        if parent and parent not in seen_parents:
            parents.append(parent)
            seen_parents.add(parent)

    leaves: list[str] = []
    seen_leaves: set[str] = set()
    for svc in enabled:
        if svc in _VIRTUAL_SERVICES:
            continue
        if svc in seen_parents:
            continue  # already covered as a parent above
        if svc in _DEFERRED_SERVICES:
            continue
        if svc in seen_leaves:
            continue
        leaves.append(svc)
        seen_leaves.add(svc)

    return parents, leaves


# ---------------------------------------------------------------------------
# Bash rendering — produces the server-side script that
# `_remote.ssh_run_script` will exec via stdin.
# ---------------------------------------------------------------------------


def render_remote_script(
    *,
    parents: list[str],
    leaves: list[str],
    dify_storage_prep: bool = False,
    metabase_storage_prep: bool = False,
    stacks_dir: str = _REMOTE_STACKS_DIR,
    global_env: str = _REMOTE_GLOBAL_ENV,
) -> str:
    """Render the bash that does parallel ``docker compose up`` + verify.

    All inputs are shlex-quoted. Service names land in a bash array
    (one per line, quoted) so spaces / special chars in a hypothetical
    future stack name can't break the loop.

    The script:
      1. ``set -euo pipefail``, ``set -a``+source the global env
         (image-version pins).
      2. Pre-deploy hooks (e.g. Dify storage perms) gated on flags.
      3. Spawn ``docker compose up -d --build`` in the background
         for every parent stack AND every leaf stack — PIDs from
         both tiers accumulate in a single ``PIDS`` array, no
         barrier between them. (Acceptable because parents and
         leaves don't share docker-compose YAML or container
         dependencies in practice — the parent/leaf split is just
         a virtual-service-mapping convention, not a startup-order
         constraint.) Each leaf invocation also applies
         ``-f docker-compose.firewall.yml`` when present on disk.
      4. ``wait`` each PID, then verify the container is in
         ``docker ps`` (R4 — fixed-string + line-exact grep). The
         rendered bash splits per-service ✓ to stdout and ✗ to
         stderr, but ``_remote.ssh_run_script(merge_stderr=True)``
         merges them on capture, and ``run_compose_up`` then
         forwards every non-RESULT line to local stderr. Net
         operator UX: both ✓ and ✗ land in the workflow-log
         stderr stream alongside the bash warnings, in source
         order. A future paramiko refactor could preserve the
         split if desired.
      5. Emit the RESULT line on stdout.
    """
    stacks_q = shlex.quote(stacks_dir)
    env_q = shlex.quote(global_env)
    parents_q = " ".join(shlex.quote(p) for p in parents)
    leaves_q = " ".join(shlex.quote(le) for le in leaves)

    dify_block = ""
    if dify_storage_prep:
        # Dify API/worker run as uid 1001; storage + plugins dirs
        # need ownership to match. Idempotent.
        dify_block = """
mkdir -p /mnt/nexus-data/dify/storage /mnt/nexus-data/dify/plugins
chown -R 1001:1001 /mnt/nexus-data/dify/storage /mnt/nexus-data/dify/plugins
"""

    metabase_block = ""
    if metabase_storage_prep:
        # Metabase runs as uid 2000 (since v0.46 official image) and
        # needs its data dir owned for the H2/DB + dashboards/questions
        # persistence (issue #528).
        #
        # The chown is guarded on the top-level dir's current owner
        # rather than running unconditionally: as Metabase state grows
        # (long-running classes can accumulate GB of H2/Lucene/cache
        # files), an unconditional `chown -R` would walk the entire
        # tree on every compose-up — measurable seconds added to deploy
        # time, plus needless I/O. The owner-check is O(1) and only
        # runs the recursive chown when we actually need to (first
        # spin-up after the bind-mount lands, or after a manual
        # ownership mishap).
        metabase_block = """
mkdir -p /mnt/nexus-data/metabase
if [ "$(stat -c '%u:%g' /mnt/nexus-data/metabase)" != "2000:2000" ]; then
  chown -R 2000:2000 /mnt/nexus-data/metabase
fi
"""

    return f"""set -euo pipefail

STACKS_DIR={stacks_q}
GLOBAL_ENV={env_q}

# Source image-version pins so compose-up sees the right tags.
if [ -f "$GLOBAL_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$GLOBAL_ENV"
    set +a
fi

PARENTS=({parents_q})
LEAVES=({leaves_q})
{dify_block}{metabase_block}
STARTED=0
FAILED=0
PIDS=()
NAMES=()

# 1. Start parent stacks (parallel — see docstring for why no barrier
#    between parents and leaves).
# A missing parent compose.yml is a real configuration error: a
# virtual service is enabled, its parent is implied, and the
# parent's compose.yml is missing — operators need to know. We
# unify the two tiers (parent + leaf) so both treat it as failed.
for svc in "${{PARENTS[@]}}"; do
    if [ -f "$STACKS_DIR/$svc/docker-compose.yml" ]; then
        ( cd "$STACKS_DIR/$svc" && docker compose up -d --build 2>&1 ) &
        PIDS+=($!)
        NAMES+=("$svc")
    else
        echo "  ⚠ docker-compose.yml missing for parent $svc" >&2
        FAILED=$((FAILED+1))
    fi
done

# 2. Start leaf stacks in parallel, applying firewall override if present.
for svc in "${{LEAVES[@]}}"; do
    if [ ! -f "$STACKS_DIR/$svc/docker-compose.yml" ]; then
        echo "  ⚠ docker-compose.yml missing for $svc" >&2
        FAILED=$((FAILED+1))
        continue
    fi
    if [ -f "$STACKS_DIR/$svc/docker-compose.firewall.yml" ]; then
        ( cd "$STACKS_DIR/$svc" && docker compose -f docker-compose.yml -f docker-compose.firewall.yml up -d --build 2>&1 ) &
    else
        ( cd "$STACKS_DIR/$svc" && docker compose up -d --build 2>&1 ) &
    fi
    PIDS+=($!)
    NAMES+=("$svc")
done

# 3. Wait for all PIDs, verify container is running for each.
for i in "${{!PIDS[@]}}"; do
    pid=${{PIDS[$i]}}
    name=${{NAMES[$i]}}
    if wait "$pid"; then
        # `docker ps --format '{{{{.Names}}}}' | grep -qFx -- "$name"`:
        # -F treats $name as a fixed string (so a hypothetical future
        # stack name with regex metacharacters like `.`, `[`, `*`
        # can't false-match), -x requires the entire line to match,
        # and `--` terminates options so a name starting with `-`
        # doesn't get parsed as a flag. Equivalent semantic to
        # `^name$` regex but safe for arbitrary inputs. Verified by
        # R4 exec'd-bash test against substring-trap + regex-meta
        # inputs.
        if docker ps --format '{{{{.Names}}}}' | grep -qFx -- "$name"; then
            STARTED=$((STARTED+1))
            echo "  ✓ $name started and running"
        else
            FAILED=$((FAILED+1))
            echo "  ✗ $name compose up succeeded but container not in 'docker ps'" >&2
        fi
    else
        rc=$?
        FAILED=$((FAILED+1))
        echo "  ✗ $name compose up failed (rc=$rc)" >&2
    fi
done

echo "RESULT started=$STARTED failed=$FAILED"
"""


def parse_result(stdout: str) -> ComposeUpResult | None:
    """Extract the ``RESULT`` line from remote stdout.

    Returns None if no parseable RESULT line — caller (CLI) maps that
    to the same hard-failure path missing-stdin would.
    """
    match = _RESULT_PATTERN.search(stdout)
    if match is None:
        return None
    g = match.groupdict()
    return ComposeUpResult(started=int(g["started"]), failed=int(g["failed"]))


# ---------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------


ScriptRunner = Callable[[str], subprocess.CompletedProcess[str]]


def run_compose_up(
    enabled: list[str],
    *,
    host: str = "nexus",
    dify_storage_prep: bool | None = None,
    metabase_storage_prep: bool | None = None,
    script_runner: ScriptRunner | None = None,
) -> ComposeUpResult:
    """Render → exec → parse.

    ``dify_storage_prep`` / ``metabase_storage_prep`` default to True
    iff the corresponding service is in ``enabled`` — caller can
    override (tests pass False to skip the mkdir/chown block,
    production lets the default fire). Both stacks bind-mount onto
    ``/mnt/nexus-data/``; the bind-mount itself is ephemeral host
    storage (post-RFC-0001 there's no Hetzner block volume), but
    the paths are registered in ``s3_restore.standard_targets`` so
    the R2 snapshot/restore cycle preserves the content across
    teardowns. The mkdir/chown prep here only handles the on-host
    ownership the container UIDs (1001 for Dify, 2000 for Metabase)
    need before the daemon writes — actual persistence is the R2
    snapshot/restore mechanism, not the bind-mount itself.

    ``host`` selects which ssh-config alias the remote script runs
    against. Defaults to ``"nexus"`` for back-compat with existing
    callers; orchestrator passes its ``self.ssh_host`` so a non-default
    ``SSH_HOST_ALIAS`` reaches every phase uniformly (PR #532 R2 #2).

    Returns ``ComposeUpResult(started=0, failed=len(enabled))`` if the
    remote script produced no parseable RESULT line — same defensive
    parse pattern as seeder.py / secret_sync.py.

    ``script_runner`` is a dependency-injection seam for tests;
    production callers leave it None.
    """
    parents, leaves = expand_targets(enabled)
    actual_dify = dify_storage_prep if dify_storage_prep is not None else "dify" in enabled
    actual_metabase = (
        metabase_storage_prep if metabase_storage_prep is not None else "metabase" in enabled
    )

    script = render_remote_script(
        parents=parents,
        leaves=leaves,
        dify_storage_prep=actual_dify,
        metabase_storage_prep=actual_metabase,
    )

    run_script = script_runner or (lambda s: _remote.ssh_run_script(s, host=host))
    completed = run_script(script)

    # Forward remote per-service ✓/✗ + warnings to local stderr (Modul-1.2
    # Round-4 pattern). The RESULT wire-format line is stripped.
    for line in completed.stdout.splitlines():
        if not line.startswith("RESULT "):
            sys.stderr.write(line + "\n")

    result = parse_result(completed.stdout)
    if result is None:
        # No RESULT — count every requested service as failed (mirrors
        # seeder.py's assumption that none of them landed).
        return ComposeUpResult(started=0, failed=len(parents) + len(leaves))
    return result

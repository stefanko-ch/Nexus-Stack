"""Pipeline-side orchestration for S3 spinup-restore + teardown-
snapshot (RFC 0001 PR-2 + PR-4).

This module is the *caller* of the pure-rendering functions in
:mod:`nexus_deploy.s3_persistence`. The split mirrors the
``setup.py`` pattern: ``s3_persistence.py`` produces bash strings,
``s3_restore.py`` reads environment / config, builds the target
lists, and ships the rendered scripts to the remote via
:class:`SSHClient`. Two directions live here:

* **spinup-restore** (:func:`restore_from_s3`) — pulls the latest
  snapshot from R2 onto the server's local SSD right after
  bootstrap, before docker compose comes up.
* **teardown-snapshot** (:func:`snapshot_to_s3`) — pushes the
  current state to R2 right before ``tofu destroy``, with the
  atomic verify-before-destroy contract from RFC 0001 §"Atomicity
  guarantees".

The module name predates the snapshot side; it's kept for stable
imports (4 call sites today). Both directions share env-var
parsing, feature-flag gating, and the canonical target list.

Public surface:

* :class:`S3RestoreSkipped` / :class:`S3RestoreApplied` — outcome
  marker classes returned by :func:`restore_from_s3`. Tests assert
  on the type; pipeline.py branches on ``isinstance()`` and reads
  ``reason`` (Skipped) or ``snapshot_timestamp`` (Applied) for
  the one-line stderr summary.
* :func:`build_endpoint_from_env` — read the five required env
  vars (three ``PERSISTENCE_S3_*`` — endpoint, region, bucket —
  plus the project-wide ``R2_ACCESS_KEY_ID`` and
  ``R2_SECRET_ACCESS_KEY``), return a populated
  :class:`S3Endpoint`. Returns ``None`` when any of them is
  unset — the caller treats that as "S3 persistence not
  configured on this stack, skip the phase."
* :func:`standard_targets` — produces the canonical tuple of
  postgres + rsync targets for the two stacks we persist
  (Gitea + Dify). Hard-coded for v1.0 because those are the only
  stacks with persistent data on the volume; a future
  per-stack config registry can replace this if other stacks
  start carrying state.
* :func:`restore_from_s3` — the orchestration entry point.
  Render rclone config + restore script via
  :mod:`s3_persistence`, ship them through ``ssh.run_script``,
  return a typed result.

Feature flag: this whole module is a *no-op* if
``NEXUS_S3_PERSISTENCE`` is not set to ``true`` in the spinup
environment. That keeps the existing volume-mount path
unchanged for stacks that haven't migrated yet (RFC Phase A:
prepare without breaking changes). The flip happens per-stack
during Phase B/C of the rollout — see RFC 0001 phased-rollout
plan.

Why a flag rather than presence-of-env-vars detection: a stack
mid-migration may have the PERSISTENCE_S3_* env vars populated
*before* its volume data has been evacuated to S3. Silently
flipping to the S3 path on env-presence would cause the first
post-flag spinup to come up with empty data dirs and the
existing volume detached + ignored. The explicit
``NEXUS_S3_PERSISTENCE=true`` flag forces an operator-aware
flip per stack.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import sys
from collections.abc import Callable
from typing import Literal

from nexus_deploy import s3_persistence as _s3
from nexus_deploy.ssh import SSHClient

# ---------------------------------------------------------------------------
# Feature-flag env var name
# ---------------------------------------------------------------------------

FEATURE_FLAG_ENV = "NEXUS_S3_PERSISTENCE"
"""Stack-level toggle. Must be exactly ``"true"`` (lowercase) to
enable the new S3-restore path. Any other value (unset, empty,
``"false"``, ``"True"`` with capital T) keeps the old
volume-mount path in pipeline.py. Strict matching is deliberate:
operators set this via GitHub Actions repo-variables where
shell-style truthy-coercion would hide configuration mistakes."""


# ---------------------------------------------------------------------------
# Outcome marker classes — pipeline.py branches on isinstance()
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class S3RestoreSkipped:
    """Restore was a no-op. ``reason`` is operator-facing: one of
    ``"feature_flag_off"``, ``"no_endpoint_env"``,
    ``"fresh_start_empty_s3"``. The first two are configuration
    states (no S3 path taken at all). The third means the path
    was taken but S3 had nothing to restore — first-ever
    spinup of a freshly-provisioned bucket. All three are
    success cases from pipeline.py's perspective."""

    reason: Literal["feature_flag_off", "no_endpoint_env", "fresh_start_empty_s3"]


@dataclasses.dataclass(frozen=True)
class S3RestoreApplied:
    """Restore ran end-to-end. ``snapshot_timestamp`` is the value
    of ``snapshots/latest.txt`` that was applied (operator can
    grep for it in the S3 bucket to find the matching
    ``snapshots/<timestamp>/`` subtree). Used by pipeline.py to
    emit a one-line summary to stderr after the phase."""

    snapshot_timestamp: str


@dataclasses.dataclass(frozen=True)
class S3SnapshotSkipped:
    """Snapshot was a no-op. ``reason`` is operator-facing:

    * ``"feature_flag_off"`` — stack hasn't opted in to S3
      persistence. Teardown proceeds safely (legacy volume path
      keeps the data on the Hetzner volume across teardowns).
      CLI rc=0.
    * ``"no_endpoint_env"`` — opted in but credentials missing.
      **Teardown MUST abort**: an unverified snapshot followed
      by ``tofu destroy`` would lose the only copy of student
      state. CLI rc=2 enforces this. The :func:`snapshot_to_s3`
      caller has already written an operator-actionable
      ``Refusing to teardown`` line to stderr listing the
      missing env vars.
    * ``"no_state_to_snapshot"`` — opted in, credentials present,
      but ``tofu state list`` reports ``No state file was found!``
      (i.e. ``tofu apply`` never ran against ``tofu/stack``). This
      is the partially-deployed-fork case from issue #564: the
      Spin-Up workflow failed BEFORE any stack resources were
      provisioned (e.g. Hetzner capacity selection aborted), so
      there is literally nothing on the server to snapshot. A
      legitimate no-op; teardown proceeds (the subsequent ``tofu
      destroy`` will also be a no-op against the empty state) and
      operators can recover without needing ``destroy-all`` to
      wipe the whole fork. CLI rc=0. NOTE: This is *narrowly*
      matched on the ``"No state file was found"`` substring from
      ``diagnose_state()`` — any other state-list failure (binary
      missing, R2 backend timeout, auth error) still raises
      ``PipelineError`` and aborts the teardown."""

    reason: Literal[
        "feature_flag_off",
        "no_endpoint_env",
        "no_state_to_snapshot",
    ]


@dataclasses.dataclass(frozen=True)
class S3SnapshotApplied:
    """Snapshot was written and verified end-to-end. ``timestamp``
    is the ISO-8601 directory under ``snapshots/`` that the
    rendered bash uploaded into AND pointed ``snapshots/latest.txt``
    at. The CLI handler prints this on success so an operator can
    correlate the teardown log line with the matching S3 object
    tree.

    Returning this class is the explicit "verified, safe to
    proceed with tofu destroy" signal from the orchestration
    side. Any non-zero rc from the rendered bash raises
    ``CalledProcessError`` instead; the snapshot's atomicity
    contract (RFC 0001) means a half-uploaded snapshot must
    block the destroy, not signal success."""

    timestamp: str


# ---------------------------------------------------------------------------
# Env-var parsing
# ---------------------------------------------------------------------------

# Names of the env vars we read. Match the keys that
# ``scripts/init-s3-bucket.sh`` writes into Infisical (under the
# ``/persistence/<stack-slug>`` path), and that spin-up.yml
# subsequently exports into the runner environment. The R2 access
# credentials are reused project-wide (from
# ``scripts/init-r2-state.sh``) so they use the existing names.

# These constants hold the NAMES of the environment variables we read —
# never their values. The strings ``"R2_ACCESS_KEY_ID"`` and
# ``"R2_SECRET_ACCESS_KEY"`` are configuration metadata; the actual
# secret material is whatever the operator (or Infisical) sets those
# env vars *to*. Renaming the constants with a ``_NAME`` suffix makes
# the safety property explicit at every call site and silences the
# CodeQL ``py/clear-text-logging-sensitive-data`` taint-tracker, which
# otherwise flags any log line that mentions a constant containing
# "secret" or "access_key" even when the logged value is just the
# name itself.
_ENV_ENDPOINT_NAME = "PERSISTENCE_S3_ENDPOINT"
_ENV_REGION_NAME = "PERSISTENCE_S3_REGION"
_ENV_BUCKET_NAME = "PERSISTENCE_S3_BUCKET"
_ENV_ACCESS_KEY_NAME = "R2_ACCESS_KEY_ID"
_ENV_SECRET_KEY_NAME = "R2_SECRET_ACCESS_KEY"  # noqa: S105 — env-var *name*, not a secret value

_REQUIRED_ENV_VAR_NAMES = (
    _ENV_ENDPOINT_NAME,
    _ENV_REGION_NAME,
    _ENV_BUCKET_NAME,
    _ENV_ACCESS_KEY_NAME,
    _ENV_SECRET_KEY_NAME,
)


def build_endpoint_from_env(env: dict[str, str] | None = None) -> _s3.S3Endpoint | None:
    """Build a :class:`S3Endpoint` from the five required env vars.

    Three are persistence-bucket coords (``PERSISTENCE_S3_ENDPOINT``,
    ``PERSISTENCE_S3_REGION``, ``PERSISTENCE_S3_BUCKET``); the other
    two are the project-wide R2 access credentials reused from
    ``init-r2-state.sh`` (``R2_ACCESS_KEY_ID``,
    ``R2_SECRET_ACCESS_KEY``).

    Returns ``None`` if any of them is missing — the caller treats
    that as "no S3 persistence configured for this stack, fall back
    to the volume-mount path." Strict all-or-nothing because a
    partially-populated config (e.g. bucket name set but credentials
    missing) almost certainly indicates a misconfigured Infisical
    secret push, and silently picking up some env vars + ignoring
    others would mask that.

    Charset validation happens inside the :class:`S3Endpoint`
    constructor — any bad value raises
    :class:`s3_persistence.S3PersistenceError` with a message that
    names the offending field.

    The ``env`` parameter is for testability — production callers
    pass ``None`` (read os.environ); tests inject a fixture dict.
    """
    source = env if env is not None else os.environ
    if any(name not in source or not source[name] for name in _REQUIRED_ENV_VAR_NAMES):
        return None
    return _s3.S3Endpoint(
        endpoint=source[_ENV_ENDPOINT_NAME],
        region=source[_ENV_REGION_NAME],
        access_key=source[_ENV_ACCESS_KEY_NAME],
        secret_key=source[_ENV_SECRET_KEY_NAME],
        bucket=source[_ENV_BUCKET_NAME],
    )


def is_enabled(env: dict[str, str] | None = None) -> bool:
    """Return True iff the feature flag is set to exactly ``"true"``.

    The strict comparison is intentional — see :data:`FEATURE_FLAG_ENV`
    docstring. ``"1"``, ``"yes"``, ``"True"``, ``"TRUE"`` all return
    ``False`` so operators get a clean error from pipeline.py rather
    than a silently-half-enabled state.
    """
    source = env if env is not None else os.environ
    return source.get(FEATURE_FLAG_ENV, "") == "true"


# ---------------------------------------------------------------------------
# Canonical target list for v1.0
# ---------------------------------------------------------------------------


def standard_targets() -> tuple[tuple[_s3.PostgresDumpTarget, ...], tuple[_s3.RsyncTarget, ...]]:
    """Return the (postgres, rsync) target tuples for the three stacks
    that v1.0 persists.

    Hard-coded because:
    1. Stateful stacks are explicitly opted in here. Adding a stack
       to the list is the SINGLE source-of-truth change that wires
       both snapshot (teardown) and restore (spin-up) for that stack.
       Skipping this step means the stack's bind-mount under
       ``/mnt/nexus-data/<stack>/`` is purely ephemeral — present
       across container restarts on the same VM, gone the moment
       ``tofu destroy`` re-creates the host.
    2. The mappings are user-name / database-name pairs from the
       respective ``docker-compose.yml`` files. Hardcoding here is
       defended by the unit tests, which assert those mappings stay
       in sync with the compose files; a docs-comment near the
       fixture would drift, the test won't.
    3. A future per-stack registry (services.yaml extension, or a
       dedicated config table) can replace this single function
       without touching any caller — :func:`restore_from_s3` only
       sees the returned tuples.

    Mappings (verified against the respective ``docker-compose.yml``
    files at PR-2 time):

    * Gitea container ``gitea-db`` — database ``gitea``, role
      ``nexus-gitea`` (``stacks/gitea/docker-compose.yml`` line 67).
    * Dify container ``dify-db`` — database ``dify``, role
      ``nexus-dify`` (``stacks/dify/docker-compose.yml`` line 180).
    * Metabase — NO PostgresDumpTarget (the OSS image uses an
      internal H2 database stored in ``/metabase-data``, captured
      via the filesystem rsync below; switching to external Postgres
      would mean adding a ``MB_DB_TYPE=postgres`` env + a sidecar
      DB + a PostgresDumpTarget here).

    Local paths land at **``/mnt/nexus-data/...``** — that's
    where the actual docker-compose bind-mounts live (see
    ``stacks/gitea/docker-compose.yml:45``,
    ``stacks/dify/docker-compose.yml:84``, and
    ``stacks/metabase/docker-compose.yml`` for the canonical
    references). An earlier draft of this function restored to
    ``/var/lib/nexus-data/...``, which would have landed the
    snapshot in a directory NO container ever sees — restore
    would appear to succeed but Gitea/Dify/Metabase would come up empty.

    S3-side layout: ``snapshots/<timestamp>/gitea/{repos,lfs}/`` and
    ``snapshots/<timestamp>/dify/{storage,weaviate,plugins}/`` follow
    RFC 0001 §"Storage layout"; ``snapshots/<timestamp>/metabase/data/``
    extends the same convention for the metabase-data target added in
    issue #528. The RFC document itself still describes only the two
    original stacks — when the next storage-layout RFC revision lands,
    add Metabase to the diagram so the canonical reference stays in
    sync.
    ``db/`` and ``redis/`` deliberately NOT in the rsync list —
    Postgres state goes through ``pg_dump`` separately, Redis is
    regeneratable on container start.
    """
    postgres = (
        _s3.PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        _s3.PostgresDumpTarget(container="dify-db", database="dify", user="nexus-dify"),
    )
    rsync = (
        _s3.RsyncTarget(
            name="gitea-repos",
            local_path="/mnt/nexus-data/gitea/repos",
            s3_subpath="gitea/repos",
        ),
        _s3.RsyncTarget(
            name="gitea-lfs",
            local_path="/mnt/nexus-data/gitea/lfs",
            s3_subpath="gitea/lfs",
        ),
        _s3.RsyncTarget(
            name="dify-storage",
            local_path="/mnt/nexus-data/dify/storage",
            s3_subpath="dify/storage",
        ),
        _s3.RsyncTarget(
            name="dify-weaviate",
            local_path="/mnt/nexus-data/dify/weaviate",
            s3_subpath="dify/weaviate",
        ),
        _s3.RsyncTarget(
            name="dify-plugins",
            local_path="/mnt/nexus-data/dify/plugins",
            s3_subpath="dify/plugins",
        ),
        # Metabase: H2/Lucene/dashboards + everything user-created
        # under /metabase-data. Single rsync target — no separate
        # PostgresDumpTarget needed for the OSS image. Issue #528.
        _s3.RsyncTarget(
            name="metabase-data",
            local_path="/mnt/nexus-data/metabase",
            s3_subpath="metabase/data",
        ),
    )
    return postgres, rsync


# ---------------------------------------------------------------------------
# Combined-script render (rclone config + restore body in one bash)
# ---------------------------------------------------------------------------


def render_combined_restore_script(
    *,
    endpoint: _s3.S3Endpoint,
    postgres_targets: tuple[_s3.PostgresDumpTarget, ...],
    rsync_targets: tuple[_s3.RsyncTarget, ...],
    local_root: str = "/mnt/nexus-data",
    phase: Literal["all", "filesystem", "postgres"] = "all",
) -> str:
    """Render a single bash script that does BOTH:

    1. Writes the rclone config to
       ``~/.config/rclone/rclone.conf`` via ``install -m 600
       /dev/stdin``. ``install`` creates the file with the
       requested permission bits in one syscall — no ``open()
       then chmod()`` race window where another process on the
       host could read the credentials with default 644
       permissions. The write itself is NOT a temp-file +
       rename (an earlier docstring revision claimed it was);
       it's a direct write at the target path with safe perms
       set on creation. That's sufficient for our threat model
       (single-user server, no concurrent writers).
    2. Runs the restore body produced by
       :func:`s3_persistence.render_restore_script`.

    Caller ships the combined script via one ``ssh.run_script``
    invocation. This is the cheapest plumbing: a single SSH
    round-trip, no temp-file management on the orchestrator side,
    no risk of a partial write between config and body.
    """
    rclone_config = _s3.render_rclone_config(endpoint)
    restore_body = _s3.render_restore_script(
        endpoint=endpoint,
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
        local_root=local_root,
        phase=phase,
    )
    # Strip the shebang + outer ``set -euo pipefail`` from the
    # restore body — the wrapper script provides them. Keeping
    # two shebangs would just be cruft; double ``set -e`` would
    # work but reads weird. We splice the body in after our
    # wrapper preamble.
    body_lines = restore_body.splitlines()
    while body_lines and (
        body_lines[0].startswith("#!")
        or body_lines[0].startswith("# Generated")
        or body_lines[0].strip() == "set -euo pipefail"
        or body_lines[0].strip() == ""
    ):
        body_lines.pop(0)
    body_inner = "\n".join(body_lines)

    return (
        "#!/usr/bin/env bash\n"
        "# Generated by nexus_deploy.s3_restore — do not edit by hand.\n"
        "set -euo pipefail\n"
        "\n"
        "# ---- write rclone config (mode 600 from creation) -----\n"
        "# `install -m 600 /dev/stdin` creates the file with the\n"
        "# secure mode in one syscall — no chmod-race window. The\n"
        "# write itself streams to the target path (not a\n"
        "# temp-file + rename), but the surrounding `set -euo\n"
        "# pipefail` guarantees fail-closed semantics: if the SSH\n"
        "# session dies mid-write, the body below never runs, so a\n"
        "# partial config can never feed into rclone.\n"
        'mkdir -p "$HOME/.config/rclone"\n'
        "install -m 600 /dev/stdin \"$HOME/.config/rclone/rclone.conf\" <<'RCLONE_CONFIG_EOF'\n"
        f"{rclone_config}"
        "RCLONE_CONFIG_EOF\n"
        "\n"
        "# ---- restore body -------------------------------------\n"
        f"{body_inner}\n"
    )


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------


def restore_from_s3(
    ssh: SSHClient,
    *,
    env: dict[str, str] | None = None,
    phase: Literal["all", "filesystem", "postgres"] = "all",
) -> S3RestoreSkipped | S3RestoreApplied:
    """Pull the latest snapshot from R2 onto the server's local SSD.

    Pipeline-side counterpart to
    :func:`s3_persistence.render_restore_script`. Returns a typed
    outcome:

    * :class:`S3RestoreSkipped` (``"feature_flag_off"``) — the
      feature flag isn't set; pipeline.py proceeds with empty
      data dirs (post-RFC-0001 cutover, there's no legacy
      volume-mount path to fall back to — the only persistence
      mechanism is R2).
    * :class:`S3RestoreSkipped` (``"no_endpoint_env"``) — the flag
      is on but credentials are missing. Treated as "skip with
      warning"; pipeline.py emits a stderr message. This is a
      misconfiguration the operator needs to see, but it's
      survivable (downstream stacks that don't need persistence
      come up fine).
    * :class:`S3RestoreSkipped` (``"fresh_start_empty_s3"``) —
      the restore ran but the bucket has no
      ``snapshots/latest.txt`` yet (brand-new bucket, first-ever
      spinup). docker compose comes up with empty data dirs;
      future teardowns will populate the bucket.
    * :class:`S3RestoreApplied` — restore ran end-to-end.
      ``snapshot_timestamp`` lets pipeline.py log which snapshot
      was applied.

    Any non-zero exit from the rendered bash that *isn't* the
    fresh-start case raises ``subprocess.CalledProcessError`` from
    inside ``ssh.run_script(check=True)``. That propagates up
    pipeline.py as a hard failure — restore corruption should NOT
    let the spinup proceed with half-populated data.

    The ``phase`` parameter splits restore into two halves because
    pg_restore needs the gitea-db / dify-db containers running
    (``docker exec`` target), while the filesystem rsync MUST land
    before compose-up (containers come up reading the seeded
    bind-mounts):

    * ``"filesystem"`` — call BEFORE compose-up; only rsync.
    * ``"postgres"`` — call AFTER compose-up; only pg_restore.
    * ``"all"`` (default) — single-shot; both halves in one
      script. Safe ONLY when the caller guarantees the gitea-db
      / dify-db containers are already running for the duration
      of the restore (otherwise the pg_restore via docker exec
      will fail). The spinup pipeline must NOT use this — its
      containers start at compose-up, between the two halves —
      and uses the split filesystem→postgres calls instead. The
      "all" phase exists for one-off operator scripts and tests
      that restore against an already-running stack.
    """
    if not is_enabled(env):
        return S3RestoreSkipped(reason="feature_flag_off")

    endpoint = build_endpoint_from_env(env)
    if endpoint is None:
        # Identify the specific missing/empty names so the operator
        # doesn't have to grep their secret store for the entire list.
        # Reading os.environ here (not the parameter ``env``) is
        # intentional — the production caller passes ``env=None`` and
        # this diagnostic should match what build_endpoint_from_env
        # actually saw. Tests pass an explicit ``env`` dict, which
        # we re-use here.
        source = env if env is not None else os.environ
        missing = [name for name in _REQUIRED_ENV_VAR_NAMES if not source.get(name)]
        sys.stderr.write(
            f"⚠ s3-restore: feature flag {FEATURE_FLAG_ENV}=true but the following "
            f"required env vars are unset or empty: {', '.join(missing)}. "
            "Skipping S3 restore.\n",
        )
        return S3RestoreSkipped(reason="no_endpoint_env")

    postgres_targets, rsync_targets = standard_targets()
    script = render_combined_restore_script(
        endpoint=endpoint,
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
        phase=phase,
    )

    # The rendered restore script either:
    #  - exits 0 after "fresh-start: no snapshot in S3" (latest.txt
    #    missing → first-time spinup). Output contains the
    #    "fresh-start" marker.
    #  - exits 0 after a real restore.
    #  - exits non-zero on any other failure (rclone error,
    #    pg_restore failure, malformed latest.txt). check=True
    #    raises CalledProcessError, which is the right behavior:
    #    a partial restore must not silently let the stack come up.
    completed = ssh.run_script(script, check=True)
    output = completed.stdout
    # Forward server-side log lines to local stderr so operators see
    # what the remote did. Mirrors mount_persistent_volume's pattern.
    for line in output.splitlines():
        sys.stderr.write(line + "\n")

    if "fresh-start: no snapshot in S3" in output:
        return S3RestoreSkipped(reason="fresh_start_empty_s3")

    # Parse the applied timestamp from "→ restore: using snapshot
    # snapshots/<timestamp>" line. If we can't find it (server-side
    # script changed shape), still return Applied — the restore did
    # complete successfully (rc=0), just with a less-informative
    # log line. Falling back to "(unknown timestamp)" keeps the
    # outcome class invariant ("rc=0 means data is in place") even
    # when the diagnostic parsing drifts.
    timestamp = "(unknown)"
    for line in output.splitlines():
        if "→ restore: using snapshot snapshots/" in line:
            # Format: "→ restore: using snapshot snapshots/<TS>"
            with contextlib.suppress(IndexError):
                timestamp = line.split("snapshots/", 1)[1].strip()
            break
    return S3RestoreApplied(snapshot_timestamp=timestamp)


# ---------------------------------------------------------------------------
# Teardown-side snapshot (PR-4)
# ---------------------------------------------------------------------------


# Compose-file list for the stop-before-snapshot step. v1.0 stops the
# three stateful stacks (Gitea, Dify, Metabase) before pg_dump + rsync
# so we get a quiesced filesystem view. Other stacks aren't stopped —
# they don't carry state, and the longer we keep them up the shorter
# the spinup-side downtime window. If a future stack gains state,
# extend this list AND add to standard_targets().
#
# Why Metabase needs to be in the stop-list even though it has no
# Postgres sidecar: the OSS image keeps a H2 database under
# /metabase-data + Lucene search indexes. rsync against those files
# while metabase is actively writing is the canonical "corrupted
# index" footgun — H2 page-file torn writes and Lucene segment
# half-writes both produce a snapshot that restores to "DB cannot
# open" on next spin-up. Stopping the container ensures all in-flight
# writes flushed + file handles closed before rclone touches the dir.
#
# Paths match the on-server layout the orchestrator already uses
# elsewhere (compose_runner.py writes each stack to
# /opt/docker-server/stacks/<name>/docker-compose.yml).
_STANDARD_STOP_COMPOSE_FILES = (
    "/opt/docker-server/stacks/gitea/docker-compose.yml",
    "/opt/docker-server/stacks/dify/docker-compose.yml",
    "/opt/docker-server/stacks/metabase/docker-compose.yml",
)


def _build_snapshot_timestamp() -> str:
    """ISO-8601 timestamp in the strict shape the s3_persistence
    snapshot script accepts (``[0-9A-Za-z_-]+``, no colons).

    Format: ``YYYYMMDDTHHMMSSZ`` (basic ISO-8601 without
    punctuation). Stable lexicographic ordering of timestamped
    snapshots is what makes the "latest by sort order" cleanup
    cron in v1.1 work — it relies on this exact shape.

    Factored out so tests can monkey-patch a deterministic value
    instead of asserting on ``datetime.utcnow``.
    """
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def render_combined_snapshot_script(
    *,
    endpoint: _s3.S3Endpoint,
    stack_slug: str,
    template_version: str,
    timestamp: str,
    postgres_targets: tuple[_s3.PostgresDumpTarget, ...],
    rsync_targets: tuple[_s3.RsyncTarget, ...],
    stop_compose_files: tuple[str, ...] = _STANDARD_STOP_COMPOSE_FILES,
) -> str:
    """Render a single bash script that does BOTH:

    1. Writes the rclone config to ``~/.config/rclone/rclone.conf``
       via ``install -m 600 /dev/stdin`` — same atomic-perms
       pattern as :func:`render_combined_restore_script`.
    2. Runs the snapshot body from
       :func:`s3_persistence.render_snapshot_script`, which
       implements the RFC 0001 atomicity contract (stop →
       pg_dump → rclone sync → per-source verify → only-then
       point ``snapshots/latest.txt``).

    Caller ships the combined script via one ``ssh.run_script``
    invocation. Any non-zero exit raises CalledProcessError,
    which the workflow caller MUST treat as "abort teardown,
    leave server up." That's the verify-before-destroy contract:
    we never let ``tofu destroy`` run if the snapshot didn't
    complete cleanly.
    """
    rclone_config = _s3.render_rclone_config(endpoint)
    snapshot_body = _s3.render_snapshot_script(
        endpoint=endpoint,
        stack_slug=stack_slug,
        template_version=template_version,
        timestamp=timestamp,
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
        stop_compose_files=stop_compose_files,
    )
    body_lines = snapshot_body.splitlines()
    while body_lines and (
        body_lines[0].startswith("#!")
        or body_lines[0].startswith("# Generated")
        or body_lines[0].strip() == "set -euo pipefail"
        or body_lines[0].strip() == ""
    ):
        body_lines.pop(0)
    body_inner = "\n".join(body_lines)

    return (
        "#!/usr/bin/env bash\n"
        "# Generated by nexus_deploy.s3_restore — do not edit by hand.\n"
        "set -euo pipefail\n"
        "\n"
        "# ---- write rclone config (mode 600 from creation) -----\n"
        "# `install -m 600 /dev/stdin` creates the file with the\n"
        "# secure mode in one syscall — no chmod-race window. The\n"
        "# write itself streams to the target path (not a\n"
        "# temp-file + rename), but the surrounding `set -euo\n"
        "# pipefail` guarantees fail-closed semantics: if the SSH\n"
        "# session dies mid-write, the body below never runs, so a\n"
        "# partial config can never feed into rclone.\n"
        'mkdir -p "$HOME/.config/rclone"\n'
        "install -m 600 /dev/stdin \"$HOME/.config/rclone/rclone.conf\" <<'RCLONE_CONFIG_EOF'\n"
        f"{rclone_config}"
        "RCLONE_CONFIG_EOF\n"
        "\n"
        "# ---- snapshot body ------------------------------------\n"
        f"{body_inner}\n"
    )


def snapshot_to_s3(
    ssh: SSHClient,
    *,
    stack_slug: str,
    template_version: str,
    env: dict[str, str] | None = None,
    timestamp_factory: Callable[[], str] | None = None,
) -> S3SnapshotSkipped | S3SnapshotApplied:
    """Push the current persistent state to R2 atomically.

    Teardown-side counterpart to :func:`restore_from_s3`. Returns
    a typed outcome:

    * :class:`S3SnapshotSkipped` (``"feature_flag_off"``) — the
      stack hasn't opted in. Caller proceeds with the legacy
      teardown path (no snapshot, volume keeps the data on
      Hetzner across teardowns).
    * :class:`S3SnapshotSkipped` (``"no_endpoint_env"``) — flag on
      but credentials missing. **Caller MUST abort the teardown**
      here — the operator opted in to S3 persistence but the
      env is misconfigured; proceeding with ``tofu destroy``
      would mean the next spinup pulls an empty bucket and the
      volume data is the only copy of student state. CLI handler
      maps this to a non-zero exit code.
    * :class:`S3SnapshotApplied` — snapshot written, verified
      (every per-source ``rclone check`` passed), and
      ``snapshots/latest.txt`` updated. Safe to proceed with
      ``tofu destroy``.

    Any non-zero exit from the rendered bash propagates as
    ``CalledProcessError``. That's the atomicity gate: rclone
    drift, pg_dump failure, or compose-stop failure all map to a
    hard abort. The teardown workflow must let it bubble up
    (``set -e`` in the workflow shell step) so ``tofu destroy``
    never runs against an unverified snapshot state.

    ``stack_slug`` + ``template_version`` are caller-supplied so
    the rendered manifest carries the right identity. Production
    callers read them from tofu outputs / env vars; tests inject
    string fixtures. ``timestamp_factory`` is the DI seam — tests
    pass a lambda returning a deterministic value; production
    uses :func:`_build_snapshot_timestamp`.
    """
    if not is_enabled(env):
        return S3SnapshotSkipped(reason="feature_flag_off")

    endpoint = build_endpoint_from_env(env)
    if endpoint is None:
        source = env if env is not None else os.environ
        missing = [name for name in _REQUIRED_ENV_VAR_NAMES if not source.get(name)]
        sys.stderr.write(
            f"✗ s3-snapshot: feature flag {FEATURE_FLAG_ENV}=true but the following "
            f"required env vars are unset or empty: {', '.join(missing)}. "
            "Refusing to teardown — fix the credentials or unset the flag.\n",
        )
        return S3SnapshotSkipped(reason="no_endpoint_env")

    postgres_targets, rsync_targets = standard_targets()
    factory = timestamp_factory if timestamp_factory is not None else _build_snapshot_timestamp
    timestamp = factory()

    script = render_combined_snapshot_script(
        endpoint=endpoint,
        stack_slug=stack_slug,
        template_version=template_version,
        timestamp=timestamp,
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
    )

    # Any non-zero exit raises CalledProcessError — let it
    # propagate up to the CLI handler / workflow so tofu destroy
    # never runs against an unverified snapshot. This is the
    # atomicity contract from RFC 0001 §"Atomicity guarantees".
    completed = ssh.run_script(script, check=True)
    output = completed.stdout
    for line in output.splitlines():
        sys.stderr.write(line + "\n")
    return S3SnapshotApplied(timestamp=timestamp)

"""Tests for nexus_deploy.s3_persistence (RFC 0001 foundation).

Pure-rendering tests: we assert on the bash text and the manifest
JSON, no subprocess calls. The remote execution path is covered
separately in pipeline.py once it's wired up.

Coverage focus areas:

* :class:`S3Endpoint` charset gating — every malformed value is
  rejected at construction time, with a message that names the
  offending field.
* :class:`PostgresDumpTarget` charset gating — container,
  database and user identifiers all validated against shapes
  that are safe to interpolate into the rendered bash + SQL.
* Manifest round-trip — ``to_json`` → ``from_json`` is identity
  for valid input; corrupt input (bad JSON, wrong root type,
  unknown version, malformed components) raises
  :class:`S3PersistenceError` with a useful message rather than
  a confusing ``KeyError`` from indexing into bad data.
* Snapshot script invariants — required structure (``set -euo
  pipefail``, ordered phases), atomicity gate (``rclone check``
  exit code captured via ``PIPESTATUS`` so a check-itself failure
  isn't masked by ``|| true``), no shell injection from any
  interpolated value.
* Restore script invariants — graceful handling of the empty-S3
  case (fresh-start branch), drop+recreate around pg_restore,
  filesystem-before-postgres ordering, ``snapshots/latest.txt``
  shape validation.
* ``bash -n`` syntax check — the rendered scripts parse cleanly
  with bash's no-execute mode. Catches dangling heredocs,
  unmatched quotes etc. — bugs that don't surface in
  string-equality tests but break at runtime on the server. Full
  exec-with-stubs smoke tests are deferred to the pipeline-
  integration PR where the SSHClient runner is plumbed in.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus_deploy.s3_persistence import (
    RCLONE_PROFILE,
    ComponentSnapshot,
    PostgresDumpTarget,
    RsyncTarget,
    S3Endpoint,
    S3PersistenceError,
    SnapshotManifest,
    manifest_for_components,
    render_rclone_config,
    render_restore_script,
    render_snapshot_script,
)


def _bash_can_be_invoked() -> bool:
    return shutil.which("bash") is not None


# ---------------------------------------------------------------------------
# S3Endpoint validation
# ---------------------------------------------------------------------------


def test_s3endpoint_accepts_canonical_r2_values() -> None:
    """Smoke: the constructor doesn't reject a real R2 config."""
    e = S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="ABCDEFG1234567890",
        secret_key="abc123XYZ+/=_-",
        bucket="nexus-stefan-hslu",
    )
    assert e.region == "auto"
    assert e.bucket == "nexus-stefan-hslu"


def test_s3endpoint_accepts_canonical_hetzner_values() -> None:
    """Smoke: the module is endpoint-agnostic; a Hetzner Object
    Storage config also passes the gate (used by future migration
    tooling, not the v1.0 steady state)."""
    e = S3Endpoint(
        endpoint="https://fsn1.your-objectstorage.com",
        region="fsn1",
        access_key="ABCDEFG1234567890",
        secret_key="abc123XYZ+/=_-",
        bucket="nexus-stefan-hslu",
    )
    assert e.region == "fsn1"
    assert e.bucket == "nexus-stefan-hslu"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint", "abc123.r2.cloudflarestorage.com"),  # missing scheme
        ("endpoint", "ftp://abc123.r2.cloudflarestorage.com"),  # wrong scheme
    ],
)
def test_s3endpoint_rejects_non_http_endpoint(field: str, value: str) -> None:
    """Non-HTTP endpoints get caught — common copy-paste error
    where someone pastes the bucket name into the endpoint slot."""
    kwargs = {
        "endpoint": "https://abc123.r2.cloudflarestorage.com",
        "region": "fsn1",
        "access_key": "AKIAEXAMPLE",
        "secret_key": "secret123",
        "bucket": "nexus-test",
    }
    kwargs[field] = value
    with pytest.raises(S3PersistenceError, match="must start with http"):
        S3Endpoint(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("region", "fsn1; rm -rf /", "region"),
        ("region", "FSN1", "region"),  # uppercase rejected
        ("bucket", "nexus stack", "bucket"),  # space rejected
        ("bucket", "ab", "bucket"),  # too short
        ("access_key", "key with spaces", "access_key"),
        ("secret_key", "secret with $bash", "secret_key"),
    ],
)
def test_s3endpoint_rejects_unsafe_charset(field: str, value: str, fragment: str) -> None:
    """Any value that could break out of bash interpolation gets
    caught at the constructor — the rendered script never sees an
    unsafe value."""
    kwargs = {
        "endpoint": "https://abc123.r2.cloudflarestorage.com",
        "region": "fsn1",
        "access_key": "AKIAEXAMPLE",
        "secret_key": "secret123",
        "bucket": "nexus-test",
    }
    kwargs[field] = value
    with pytest.raises(S3PersistenceError, match=fragment):
        S3Endpoint(**kwargs)


# ---------------------------------------------------------------------------
# rclone config
# ---------------------------------------------------------------------------


def test_render_rclone_config_emits_full_profile_block() -> None:
    """The block contains every key rclone needs to authenticate
    against R2. No accidental ``env_auth = true`` (which would
    silently fall back to ambient AWS env vars). The
    ``provider = Cloudflare`` switch is what tells rclone to
    apply R2-specific quirks."""
    e = S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="AKIA1234",
        secret_key="secret/key+abc=",
        bucket="nexus-stefan-hslu",
    )
    config = render_rclone_config(e)

    assert config.startswith(f"[{RCLONE_PROFILE}]\n")
    assert "type = s3\n" in config
    assert "provider = Cloudflare\n" in config
    assert "env_auth = false\n" in config
    assert "access_key_id = AKIA1234\n" in config
    assert "secret_access_key = secret/key+abc=\n" in config
    assert "endpoint = https://abc123.r2.cloudflarestorage.com\n" in config
    assert "region = auto\n" in config
    assert "acl = private\n" in config


def test_render_rclone_config_uses_module_level_profile_name() -> None:
    """Regression: render and script use the SAME profile name.
    Hardcoded literal would be fine but a constant means a future
    rename can't drift between the two render functions."""
    e = S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="AKIA",
        secret_key="secret",
        bucket="nexus-test",
    )
    config = render_rclone_config(e)
    snapshot = render_snapshot_script(
        endpoint=e,
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(),
    )
    assert f"[{RCLONE_PROFILE}]" in config
    assert f"{RCLONE_PROFILE}:" in snapshot


# ---------------------------------------------------------------------------
# Manifest serialisation
# ---------------------------------------------------------------------------


def test_manifest_round_trip_is_identity() -> None:
    """to_json → from_json preserves every component."""
    original = SnapshotManifest(
        version=1,
        created_at="2026-05-10T20:00:00Z",
        stack="nexus-stefan-hslu",
        template_version="v0.56.0",
        components=(
            ComponentSnapshot(
                name="gitea-repos", path="gitea/repos", size_bytes=1024, sha256="abc123"
            ),
            ComponentSnapshot(
                name="dify-storage", path="dify/storage", size_bytes=2048, sha256="def456"
            ),
        ),
    )
    parsed = SnapshotManifest.from_json(original.to_json())
    assert parsed == original


def test_manifest_to_json_is_deterministic() -> None:
    """Sorted keys → same bytes for the same input. Important for
    rclone-check ETag stability across re-renders."""
    m = SnapshotManifest(stack="x", template_version="y", components=())
    assert m.to_json() == m.to_json()


def test_manifest_from_json_rejects_unknown_version() -> None:
    """A future v2 manifest read by a v1 client should hard-fail
    rather than silently truncate fields."""
    raw = json.dumps({"version": 2, "components": []})
    with pytest.raises(S3PersistenceError, match=r"version 2 .* not supported"):
        SnapshotManifest.from_json(raw)


def test_manifest_from_json_rejects_non_object_root() -> None:
    raw = "[]"
    with pytest.raises(S3PersistenceError, match="root must be an object"):
        SnapshotManifest.from_json(raw)


def test_manifest_from_json_rejects_invalid_json() -> None:
    with pytest.raises(S3PersistenceError, match="not valid JSON"):
        SnapshotManifest.from_json("{ not json")


def test_manifest_from_json_rejects_non_dict_component() -> None:
    """A component that's not a dict (e.g. a stray string) must
    surface as :class:`S3PersistenceError` with an actionable
    message, not a confusing TypeError. Promised in the
    docstring; the previous implementation indexed straight in
    and raised ``TypeError: string indices must be integers``."""
    raw = json.dumps({"version": 1, "components": ["not-a-dict"]})
    with pytest.raises(S3PersistenceError, match=r"components\[0\] must be an object"):
        SnapshotManifest.from_json(raw)


def test_manifest_from_json_rejects_component_missing_keys() -> None:
    """A component dict missing one of the four required keys is
    a manifest corruption — caller needs an actionable error,
    not a KeyError stack trace."""
    raw = json.dumps(
        {
            "version": 1,
            "components": [{"name": "x", "path": "x"}],  # no size_bytes/sha256
        }
    )
    with pytest.raises(S3PersistenceError, match=r"missing required key"):
        SnapshotManifest.from_json(raw)


def test_manifest_from_json_rejects_component_with_bad_size() -> None:
    """``size_bytes`` must be coerce-able to int. A string like
    'banana' would have raised ValueError mid-parse with the old
    code; we now wrap it to S3PersistenceError."""
    raw = json.dumps(
        {
            "version": 1,
            "components": [
                {
                    "name": "x",
                    "path": "x",
                    "size_bytes": "banana",  # invalid
                    "sha256": "abc",
                }
            ],
        }
    )
    with pytest.raises(S3PersistenceError, match="bad value"):
        SnapshotManifest.from_json(raw)


# ---------------------------------------------------------------------------
# PostgresDumpTarget charset gating (added in PR review round 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        # container — docker-service-name shape (Hetzner-region regex)
        ("container", "Gitea_DB", "container"),  # underscore + uppercase
        ("container", "gitea db", "container"),  # space
        ("container", "gitea;rm", "container"),  # injection attempt
        # database / user — strict PG identifier
        ("database", "drop table users", "database"),
        ("database", "1abc", "database"),  # leading digit
        ("database", 'gitea"', "database"),  # quote injection
        ("user", "user;DROP", "user"),
        ("user", "user with space", "user"),
    ],
)
def test_postgres_dump_target_rejects_unsafe_identifiers(
    field: str, value: str, fragment: str
) -> None:
    """Every value that could break out of bash interpolation OR
    SQL identifier interpolation must be rejected at construction
    time. The rendered bash + SQL never sees an unsafe value."""
    kwargs = {"container": "gitea-db", "database": "gitea", "user": "nexus-gitea"}
    kwargs[field] = value
    with pytest.raises(S3PersistenceError, match=fragment):
        PostgresDumpTarget(**kwargs)


def test_postgres_dump_target_accepts_canonical_values() -> None:
    """Smoke: real-world configs (``gitea-db`` / ``gitea`` /
    ``nexus-gitea``) pass the gate."""
    PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea")
    PostgresDumpTarget(container="dify-db", database="dify", user="nexus_dify")
    PostgresDumpTarget(container="x-db-2", database="db_v2", user="role_admin")


# ---------------------------------------------------------------------------
# RsyncTarget charset gating (Copilot round-3 #3216323836 / #3216323852)
# ---------------------------------------------------------------------------


def test_rsync_target_accepts_canonical_values() -> None:
    """Smoke: the typical nexus-data layout passes the gate."""
    RsyncTarget(
        name="gitea-repos", local_path="/var/lib/nexus-data/gitea/repos", s3_subpath="gitea/repos"
    )
    RsyncTarget(
        name="dify-storage",
        local_path="/var/lib/nexus-data/dify/storage",
        s3_subpath="dify/storage",
    )


@pytest.mark.parametrize(
    "subpath",
    [
        "gitea/$(rm -rf /)",  # command substitution
        "gitea/`whoami`",  # backticks
        "gitea/repos with space",
        "/gitea/repos",  # leading slash
        "gitea/repos/",  # trailing slash
        "../gitea",  # parent ref
        "gitea/../etc",  # parent ref middle
        'gitea/"injection',  # quote
    ],
)
def test_rsync_target_rejects_unsafe_s3_subpath(subpath: str) -> None:
    """``s3_subpath`` is interpolated into double-quoted bash strings
    where ``shlex.quote`` doesn't help. Constructor must catch every
    shape that would corrupt the rendered bash or escape the bucket
    path."""
    with pytest.raises(S3PersistenceError, match="s3_subpath"):
        RsyncTarget(name="x", local_path="/var/lib/nexus-data/x", s3_subpath=subpath)


def test_rsync_target_rejects_relative_local_path() -> None:
    with pytest.raises(S3PersistenceError, match="local_path must be absolute"):
        RsyncTarget(name="x", local_path="relative/path", s3_subpath="x")


# ---------------------------------------------------------------------------
# S3Endpoint endpoint-URL charset gating (Copilot round-3 #3216323864)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fsn1.your-objectstorage.com\nextra_key = injection",
        "https://fsn1 .your-objectstorage.com",  # space
        "https://fsn1.your-objectstorage.com\r\n",
        "https://fsn1.your-objectstorage.com\t",
    ],
)
def test_s3endpoint_rejects_endpoint_with_whitespace_or_newlines(endpoint: str) -> None:
    """Whitespace/newlines in the endpoint URL would corrupt the
    rendered rclone config (split the value across multiple keys,
    inject extra config lines). Regression for Copilot round-3
    #3216323864."""
    with pytest.raises(S3PersistenceError, match="corrupt the rendered rclone config"):
        S3Endpoint(
            endpoint=endpoint,
            region="auto",
            access_key="AKIA",
            secret_key="secret",
            bucket="nexus-test",
        )


def test_manifest_for_components_helper_sorts_components() -> None:
    """Components map → sorted ComponentSnapshot tuple. Sorting
    matters for deterministic manifest bytes regardless of the
    order callers populate the map in."""
    m = manifest_for_components(
        stack="nexus-test",
        template_version="v0.56.0",
        created_at="2026-05-11T04:00:00Z",
        components={
            "z-stack": (10, "z-hash"),
            "a-stack": (20, "a-hash"),
        },
    )
    assert [c.name for c in m.components] == ["a-stack", "z-stack"]


def test_manifest_for_components_propagates_created_at() -> None:
    """Regression: ``created_at`` is now an actual parameter (was
    previously a no-op ``timestamp`` arg that the helper ignored).
    The value must land on the manifest's ``created_at`` field."""
    m = manifest_for_components(
        stack="nexus-test",
        template_version="v0.56.0",
        created_at="2026-05-11T04:00:00Z",
        components={},
    )
    assert m.created_at == "2026-05-11T04:00:00Z"


# ---------------------------------------------------------------------------
# Snapshot script structure
# ---------------------------------------------------------------------------


def _endpoint() -> S3Endpoint:
    return S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="AKIA1234",
        secret_key="secret123",
        bucket="nexus-test",
    )


def test_snapshot_script_has_bash_safety_pragmas() -> None:
    """Every rendered script must start with the standard bash
    pragmas — silent failure mid-snapshot would leave inconsistent
    S3 state."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(),
    )
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script


def test_snapshot_script_orders_phases_correctly() -> None:
    """The phase order is the atomicity contract: **dump → stop →
    upload → verify → point latest**. Note dump comes BEFORE stop —
    pg_dump is a client tool that requires the postgres container
    running, so stopping it first leaves dump with nothing to
    connect to. The earlier "stop first, dump second" form failed
    every real teardown with "container is not running". Reorder
    would silently break the guarantee that ``snapshots/latest.txt``
    only updates after upload succeeded.

    We use ``docker compose stop`` (graceful 10s drain), not
    ``pause`` (SIGSTOP via cgroup freezer, hard-kills in-flight
    writes mid-transaction).
    """
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="gitea-repos",
                local_path="/var/lib/nexus-data/gitea/repos",
                s3_subpath="gitea/repos",
            ),
        ),
        stop_compose_files=("/opt/docker-server/stacks/gitea/docker-compose.yml",),
    )
    # Locate each phase via a stable substring + assert ordering.
    # **dump → stop** is the load-bearing ordering: pg_dump needs
    # the container running, so it must come before compose-stop.
    dump_pos = script.find("pg_dump")
    stop_pos = script.find("compose -f")
    upload_pos = script.find("rclone sync")
    check_pos = script.find("rclone check")
    latest_pos = script.find("snapshots/latest.txt")
    assert dump_pos < stop_pos < upload_pos < check_pos < latest_pos
    # Regression: stop, not pause, AND no `... || echo` blanket
    # error-swallowing (per CLAUDE.md "Never silently swallow
    # errors in critical operations"). The current implementation
    # uses ``if docker compose ps -q ... then stop`` so a genuine
    # `stop` failure bubbles via ``set -e``.
    assert "docker compose -f" in script
    assert "stop" in script  # rendered command verb is `stop`
    assert "pause" not in script
    # No blanket "|| echo non-fatal" masking on the stop step.
    stop_block = script.split("→ snapshot: stopping compose stacks")[1].split("→ snapshot:")[0]
    assert "stop || echo" not in stop_block
    # Regression for Copilot round-6 #3216702497: the
    # ``ps -q`` probe must capture both the exit code AND the
    # stdout separately, so an empty-stdout-from-ps-FAILING
    # case (missing compose file, daemon down, YAML syntax)
    # doesn't masquerade as the empty-stdout-from-no-containers
    # case. The earlier ``[ -n "$(ps -q 2>/dev/null)" ]`` form
    # silently mapped failure to "skip stop" and continued the
    # snapshot while services kept running.
    assert "PS_RC=$?" in stop_block
    assert '[ "$PS_RC" -eq 0 ] && [ -z "$PS_OUT" ]' in stop_block


def test_snapshot_script_skips_compose_stop_when_file_missing() -> None:
    """If a compose file isn't on disk the snapshot must skip its
    stop step cleanly (stack-not-deployed) instead of letting
    ``docker compose stop`` abort with 'no such file or directory'.
    Same pattern for the rsync + pg_dump targets below. Real
    incident: PR #557 first teardown of the cutover snapshotted
    gitea successfully then failed on dify because dify wasn't
    deployed on that server. The persistence layer can't assume
    every stack in its target list is actually present."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
            PostgresDumpTarget(container="dify-db", database="dify", user="nexus-dify"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="gitea-repos",
                local_path="/var/lib/nexus-data/gitea/repos",
                s3_subpath="gitea/repos",
            ),
            RsyncTarget(
                name="dify-db",
                local_path="/var/lib/nexus-data/dify/db",
                s3_subpath="dify/db",
            ),
        ),
        stop_compose_files=(
            "/opt/docker-server/stacks/gitea/docker-compose.yml",
            "/opt/docker-server/stacks/dify/docker-compose.yml",
        ),
    )
    # Compose-stop must guard with `[ -f "$COMPOSE_FILE" ]` before
    # touching docker. The skip branch must log explicitly so
    # operators see WHY the stack wasn't stopped.
    assert 'if [ ! -f "$COMPOSE_FILE" ]; then' in script
    assert "stack not deployed" in script
    # pg_dump must guard with `docker inspect <container>` — a
    # missing container today produces an opaque "Error: No such
    # container" with rc=1 which set -e turns into a teardown
    # abort.
    # pg_dump must guard with `docker inspect --format='{{.State.Running}}'`
    # — a missing container (not deployed) AND a stopped container
    # (e.g. crashed earlier) both produce non-"true" output, both
    # land in the skip branch. Bare `docker inspect <c>` would
    # incorrectly succeed for stopped containers, then `docker
    # exec` would fail with rc=1 and abort the snapshot.
    assert "docker inspect --format='{{.State.Running}}' gitea-db" in script
    assert "container dify-db not running" in script
    # rsync sync must guard with `[ -d <path> ]`. The verify_one
    # function (called for every rs_target) must short-circuit on
    # missing source too — verifying a non-existent local dir
    # against an empty S3 prefix would otherwise mark the snapshot
    # as drifted and abort.
    assert "if [ -d /var/lib/nexus-data/dify/db ]" in script
    assert 'if [ ! -d "$src" ]; then' in script


def test_snapshot_script_omits_compose_stop_when_no_files_passed() -> None:
    """No compose files passed → no docker compose calls at all.
    Avoids the ``no compose files`` echo-only no-op block."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(),
    )
    assert "docker compose" not in script


def test_snapshot_script_omits_postgres_phase_when_no_targets() -> None:
    """A compose-only stack (no Postgres) shouldn't render the
    pg_dump block — and shouldn't try to upload an empty dump
    directory either."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(RsyncTarget(name="r", local_path="/var/lib/nexus-data/x", s3_subpath="x"),),
    )
    assert "pg_dump" not in script
    assert "uploading postgres dumps" not in script


def test_snapshot_script_rejects_unsafe_stack_slug() -> None:
    with pytest.raises(S3PersistenceError, match="stack_slug"):
        render_snapshot_script(
            endpoint=_endpoint(),
            stack_slug="nexus stack with spaces",
            template_version="v",
            timestamp="t",
            postgres_targets=(),
            rsync_targets=(),
        )


def test_snapshot_script_rejects_unsafe_timestamp() -> None:
    """A timestamp containing shell metacharacters could break out
    of the rendered ``$TIMESTAMP=...`` interpolation."""
    with pytest.raises(S3PersistenceError, match="timestamp"):
        render_snapshot_script(
            endpoint=_endpoint(),
            stack_slug="nexus-test",
            template_version="v0.56.0",
            timestamp="2026-05-10T20:00:00Z",  # colons rejected
            postgres_targets=(),
            rsync_targets=(),
        )


def test_snapshot_script_verify_logs_live_outside_workdir() -> None:
    """The rclone-check stderr/stdout dumps MUST live OUTSIDE
    ``$WORKDIR``. The first verify_one call compares ``$WORKDIR``
    against S3; if the dumps lived inside $WORKDIR they'd appear
    as untracked extras and rclone would report 'differences
    found', failing every snapshot.

    Real incident: PR #557 first end-to-end teardown surfaced this
    after every other layer was patched — the verify gate fired
    for the first time ever, the manifest+pg-dumps verify
    reported 2 diffs (rclone-check.err + rclone-check.out), and
    the snapshot aborted without flipping snapshots/latest.txt.
    """
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(),
    )
    # Scratch dir for verify-phase logs must be declared separately
    # and live outside $WORKDIR.
    assert "LOG_DIR=/tmp/nexus-snapshot-logs" in script
    # The rclone-check redirects must go to LOG_DIR, NOT WORKDIR.
    assert '2>"$LOG_DIR/rclone-check.err"' in script
    assert '"$LOG_DIR/rclone-check.out"' in script
    # And NOTHING should write rclone-check.{err,out} into WORKDIR
    # — the regression we're guarding against.
    assert "WORKDIR/rclone-check" not in script


def test_snapshot_script_atomicity_gate_distinguishes_two_failure_modes() -> None:
    """The atomicity gate must distinguish (a) rclone-check itself
    erroring (auth/network/quota) from (b) drift found via the
    pipe-grep on rclone-check's --combined output. Both rcs are
    captured via ``PIPESTATUS`` so neither can be silently masked
    by ``|| true``."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(),
    )
    assert "rclone check" in script
    # PIPESTATUS must be captured into a LOCAL ARRAY immediately
    # after the pipeline runs, BEFORE any other command (including
    # `local`). The `local` builtin overwrites PIPESTATUS with its
    # own single-element exit-code array, so two separate
    # `local rclone_rc=${PIPESTATUS[0]}; local drift_rc=${PIPESTATUS[2]}`
    # would fail with "PIPESTATUS[2]: unbound variable" under
    # set -u — the second `local` reads from the already-clobbered
    # 1-element array.
    #
    # Regression pin for two distinct bugs in the same line block:
    #   - drift_rc must read [2] (grep), not [1] (tee — always 0,
    #     would make every snapshot report drift)
    #   - the capture must be a single `local ps=("${PIPESTATUS[@]}")`
    #     before the two reads, NOT two separate `local` lines
    assert 'local pipeline_status=("${PIPESTATUS[@]}")' in script
    assert "rclone_rc=${pipeline_status[0]}" in script
    assert "drift_rc=${pipeline_status[2]}" in script
    # And both abort messages must distinguish the two modes.
    assert "snapshot-failed: rclone check ${label} errored" in script
    assert "snapshot-failed: rclone check ${label} found drift" in script


def test_snapshot_script_verifies_every_rsync_target() -> None:
    """The verify gate must run an rclone check for ``$WORKDIR``
    (manifest + postgres dumps) AND one per ``RsyncTarget`` — the
    filesystem trees uploaded via ``rclone sync {local} {dst}``
    are NOT in $WORKDIR, so a $WORKDIR-only check would have left
    the bulk of the persisted state unverified.

    Regression for Copilot round-3 #3216323822."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(),
        rsync_targets=(
            RsyncTarget(
                name="gitea-repos",
                local_path="/var/lib/nexus-data/gitea/repos",
                s3_subpath="gitea/repos",
            ),
            RsyncTarget(
                name="dify-storage",
                local_path="/var/lib/nexus-data/dify/storage",
                s3_subpath="dify/storage",
            ),
        ),
    )
    # Workdir verify (manifest + postgres dumps)
    assert 'verify_one "$WORKDIR" "$BUCKET/$SNAPSHOT_PREFIX" "workdir(manifest+postgres)"' in script
    # Plus per-rsync-target verify
    assert "verify_one /var/lib/nexus-data/gitea/repos" in script
    assert "verify_one /var/lib/nexus-data/dify/storage" in script
    # Final gate before pointing snapshots/latest
    assert 'if [ "$verify_failed" -ne 0 ]; then' in script
    assert "not pointing snapshots/latest at $TIMESTAMP" in script


# ---------------------------------------------------------------------------
# Restore script structure
# ---------------------------------------------------------------------------


def test_restore_script_has_bash_safety_pragmas() -> None:
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script


def test_restore_script_handles_empty_s3_gracefully() -> None:
    """First-time spinup → no snapshot in S3 → script must exit
    0, not blow up. The pipeline then proceeds with a clean
    docker-compose-up just like a brand-new install."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    assert "fresh-start" in script
    assert "exit 0" in script


def test_restore_script_drops_database_before_pg_restore() -> None:
    """A restore against a running Postgres with existing rows
    would conflict on PK; the drop+recreate keeps the pg_restore
    deterministic.

    SQL identifiers are now ALWAYS double-quoted because real role
    names use hyphens (``nexus-gitea``) which would be invalid as
    unquoted SQL — the previous unquoted form would have produced
    ``OWNER nexus-gitea`` which Postgres rejects as a syntax error.
    """
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(),
    )
    assert 'DROP DATABASE IF EXISTS "gitea"' in script
    assert 'CREATE DATABASE "gitea" OWNER "nexus-gitea"' in script
    # CLI args don't need SQL quoting — pg_restore's -U/-d take plain
    # values via argv, not embedded SQL.
    assert "pg_restore -U nexus-gitea -d gitea" in script


def test_restore_script_skips_pg_restore_when_dump_missing_or_container_absent() -> None:
    """Symmetric "stack not deployed" handling between snapshot
    and restore. Two distinct skip cases on the restore side:

    1. The dump file isn't in WORKDIR/postgres/ because the
       snapshot side skipped that DB (container wasn't running
       at snapshot time).
    2. The dump exists but the target container isn't running
       on this restore stack (snapshot composition differs from
       restore composition — e.g. dify snapshotted but not
       restored).

    Without these guards, ``gunzip ... | docker exec dify-db
    pg_restore`` aborts the whole restore with "No such file"
    or "No such container". This is the symmetric fix to the
    snapshot-side pg_dump skip guard.

    Real incident: first end-to-end restore test of PR #557 —
    snapshot correctly skipped dify-db (not deployed), but
    restore tried to ``docker exec dify-db`` and aborted with
    rc=1 → spin-up failed."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
            PostgresDumpTarget(container="dify-db", database="dify", user="nexus-dify"),
        ),
        rsync_targets=(),
    )
    # Both guards must be present, in the right shape, before the
    # docker exec / gunzip lines that would otherwise crash.
    assert "if [ ! -f $WORKDIR/postgres/gitea.dump.gz ]" in script
    assert "if [ ! -f $WORKDIR/postgres/dify.dump.gz ]" in script
    assert "no dump for dify" in script
    assert "no dump for gitea" in script
    assert "container dify-db not running" in script
    assert "container gitea-db not running" in script
    # And the skip path must be an EARLY return — no DROP DATABASE
    # / gunzip / pg_restore on the dify side when container's gone.
    # Pin the if-elif-else structure so the guards can't be silently
    # bypassed by a future refactor.
    assert "docker inspect --format='{{.State.Running}}' dify-db" in script
    assert "docker inspect --format='{{.State.Running}}' gitea-db" in script


def test_restore_script_pulls_filesystem_trees_before_postgres() -> None:
    """Order matters: restore the FS first (in case any postgres
    init script reads a config file from the FS), THEN pg_restore.
    Reversing this ordering would race on first start."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="r", local_path="/var/lib/nexus-data/gitea/repos", s3_subpath="gitea/repos"
            ),
        ),
    )
    fs_pos = script.find("pulling filesystem trees")
    pg_pos = script.find("pulling postgres dumps")
    assert 0 < fs_pos < pg_pos


def test_restore_script_phase_filesystem_omits_postgres_block() -> None:
    """RFC 0001 cutover: ``phase="filesystem"`` is called BEFORE
    compose-up on the spinup side, when no gitea-db / dify-db
    container exists yet. The rendered script MUST omit the
    ``docker exec ... pg_restore`` block — otherwise the very
    first spinup after a snapshot would hit "container not found"
    and abort the pipeline. Symmetric to the postgres-only phase
    below."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="r", local_path="/var/lib/nexus-data/gitea/repos", s3_subpath="gitea/repos"
            ),
        ),
        phase="filesystem",
    )
    # Filesystem block present.
    assert "pulling filesystem trees" in script
    # Postgres block absent — neither the rclone-sync of dumps nor
    # any docker exec line should be rendered.
    assert "pulling postgres dumps" not in script
    assert "docker exec" not in script
    assert "pg_restore" not in script


def test_restore_script_phase_postgres_omits_filesystem_block() -> None:
    """Symmetric to the filesystem-only test above.
    ``phase="postgres"`` runs AFTER compose-up; the filesystem
    rsync has already happened in the earlier phase=filesystem
    call, so the postgres-only call MUST NOT re-run those
    (cheap to do twice but breaks the test contract that the
    function honors its phase parameter)."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="r", local_path="/var/lib/nexus-data/gitea/repos", s3_subpath="gitea/repos"
            ),
        ),
        phase="postgres",
    )
    # Postgres block present.
    assert "pulling postgres dumps" in script
    assert "docker exec gitea-db" in script
    # Filesystem block absent.
    assert "pulling filesystem trees" not in script
    # The latest.txt lookup prelude is still present in both phases —
    # it gates the fresh-start short-circuit.
    assert "snapshots/latest.txt" in script


def test_restore_script_phase_all_is_the_default_and_includes_both() -> None:
    """Backward-compat: ``phase="all"`` is the default (preserved
    for the snapshot-replay paths and any caller that runs both
    halves in one shot). Must render BOTH halves."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(
                name="r", local_path="/var/lib/nexus-data/gitea/repos", s3_subpath="gitea/repos"
            ),
        ),
    )
    assert "pulling filesystem trees" in script
    assert "pulling postgres dumps" in script


def test_restore_script_validates_timestamp_from_s3() -> None:
    """``snapshots/latest.txt`` is operator-influenced (an admin
    could in theory write it) — the script must validate the
    contents before substituting it into a path."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    assert '[[ ! "$TIMESTAMP" =~ ^[0-9A-Za-z_-]+$ ]]' in script
    assert "restore-failed: latest.txt has invalid timestamp" in script


def test_restore_script_rejects_unknown_phase() -> None:
    """A typo like ``phase="fs"`` would make BOTH include_fs +
    include_pg false and silently produce a no-op restore script
    (exit 0 after the latest.txt lookup). Fail loud at render time."""
    with pytest.raises(ValueError, match="phase must be one of"):
        render_restore_script(
            endpoint=_endpoint(),
            postgres_targets=(),
            rsync_targets=(),
            phase="fs",  # type: ignore[arg-type]
        )


def test_restore_script_detects_missing_latest_via_lsf_stdout_not_exit_code() -> None:
    """Older apt rclone (Ubuntu 24.04 shipped v1.60.1) returns rc=0 with empty
    stdout for a missing remote object, so an ``if ! rclone lsf ...``
    check NEVER fires the fresh-start branch on that version — the
    script falls through to ``copyto`` (also rc=0, no local file
    created), and the first observable failure is the kernel-level
    ``tr -d < missing-file`` line ("No such file or directory")
    masquerading as rc=1. Use lsf's STDOUT instead: empty = missing.

    This is the bug that broke PR #556's first-real-spinup test —
    the rcfix unblocked the install, but the rclone-1.60.1 lsf
    behaviour made every fresh bucket fail-instead-of-fresh-start."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    # The fresh-start guard must list the PARENT prefix (so empty
    # listing = empty bucket = fresh-start) and treat a non-zero
    # exit from the listing as a HARD ERROR (not fresh-start) —
    # otherwise a transient S3 blip after the bucket-reachability
    # probe would silently empty local state, and the next teardown
    # would overwrite real R2 data. Pin the exact bash shape so a
    # future "simplification" can't regress us into any of the
    # previous broken forms:
    #   - ``if ! rclone lsf .../latest.txt >/dev/null`` (rclone-1.60
    #     returns rc=0 on missing → never enters branch)
    #   - ``[ -z "$(rclone lsf ...)" ]`` (depends on errexit-in-
    #     cmd-sub semantics that flip with inherit_errexit)
    #   - ``if ! VAR=$(rclone lsf .../latest.txt); then VAR=""`` →
    #     treats transient errors as fresh-start (round-2 form)
    assert 'SNAPSHOT_LISTING=$(rclone lsf "$BUCKET/snapshots/")' in script, (
        "fresh-start guard must list the parent prefix, not the file directly"
    )
    assert 'grep -qxF "latest.txt"' in script, (
        "fresh-start guard must check for latest.txt as a whole-line fixed match"
    )
    # Hard error path — listing failure must exit 2, NOT fresh-start.
    assert "cannot list" in script
    # And a defence-in-depth check: even if listing passed and
    # copyto ran but copyto didn't actually produce the file, fail
    # loud (exit 2) rather than letting the next ``tr -d`` leak
    # its kernel error.
    assert '[ ! -s "$WORKDIR/latest.txt" ]' in script


def test_restore_script_probes_bucket_reachability_before_fresh_start() -> None:
    """A bare ``rclone lsf latest.txt`` failure is ambiguous: missing
    object OR auth/network error. Treating both as "fresh-start"
    would silently empty local state on a credentials problem; the
    next teardown then snapshots the empty state over real R2 data.
    Render must emit a ``rclone lsd "$BUCKET"`` probe FIRST and
    exit 2 if that fails — only then check ``latest.txt``."""
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    probe_pos = script.find('rclone lsd "$BUCKET"')
    fresh_check_pos = script.find('rclone lsf "$BUCKET/snapshots/"')
    assert 0 < probe_pos < fresh_check_pos, (
        "bucket reachability probe must precede the snapshot-prefix listing"
    )
    assert "not reachable" in script
    # The probe failure path must exit non-zero (clear error), the
    # latest.txt failure path must exit 0 (legitimate fresh-start).
    assert "exit 2" in script
    assert "exit 0" in script


# ---------------------------------------------------------------------------
# Smoke: the rendered scripts are syntactically valid bash
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _bash_can_be_invoked(), reason="bash not available")
def test_rendered_snapshot_script_is_syntactically_valid_bash(tmp_path: Path) -> None:
    """``bash -n`` parses the rendered text without complaint.
    Catches dangling heredocs, unmatched quotes, etc. — the kind
    of bug that doesn't show up in a string-comparison test but
    breaks at runtime on the server."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.56.0",
        timestamp="20260510T120000Z",
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(name="r", local_path="/var/lib/nexus-data/gitea", s3_subpath="gitea"),
        ),
        stop_compose_files=("/opt/docker-server/stacks/gitea/docker-compose.yml",),
    )
    script_path = tmp_path / "snapshot.sh"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


@pytest.mark.skipif(not _bash_can_be_invoked(), reason="bash not available")
def test_rendered_restore_script_is_syntactically_valid_bash(tmp_path: Path) -> None:
    script = render_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(
            PostgresDumpTarget(container="gitea-db", database="gitea", user="nexus-gitea"),
        ),
        rsync_targets=(
            RsyncTarget(name="r", local_path="/var/lib/nexus-data/gitea", s3_subpath="gitea"),
        ),
    )
    script_path = tmp_path / "restore.sh"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"

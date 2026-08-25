"""Tests for nexus_deploy.s3_restore (RFC 0001 PR-2 pipeline-side).

Pipeline-side orchestration tests. ``s3_persistence.py`` is the
pure-rendering module already covered by ``test_s3_persistence.py``;
this file tests the *caller* — env-var parsing, feature-flag
gating, target-list correctness, the combined-script render shape,
and the orchestration outcome classes.

Coverage focus:

* :func:`build_endpoint_from_env` — all five env vars required;
  any missing → ``None``; charset gating inherited from
  :class:`S3Endpoint`.
* :func:`is_enabled` — strict ``"true"`` match, rejects ``"1"`` /
  ``"True"`` / ``"yes"``.
* :func:`standard_targets` — canonical fixture for v1.0 stacks;
  asserts the user/db identifiers match the values in
  ``stacks/{gitea,dify}/docker-compose.yml`` so a future
  POSTGRES_USER rename breaks the test (and gets caught here
  rather than at runtime).
* :func:`render_combined_restore_script` — single combined script
  contains both the rclone config write and the restore body, in
  that order, with ``mode 600`` on the config file.
* :func:`restore_from_s3` — outcome-class dispatch using a fake
  SSHClient.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from nexus_deploy import s3_persistence as _s3
from nexus_deploy.s3_restore import (
    _STANDARD_STOP_COMPOSE_FILES,
    FEATURE_FLAG_ENV,
    S3RestoreApplied,
    S3RestoreSkipped,
    S3SnapshotApplied,
    S3SnapshotSkipped,
    build_endpoint_from_env,
    is_enabled,
    render_combined_restore_script,
    render_combined_snapshot_script,
    restore_from_s3,
    snapshot_to_s3,
    standard_targets,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _good_env() -> dict[str, str]:
    """Canonical "all five env vars populated" map used by most
    tests. R2-style endpoint per the v1.0 default."""
    return {
        "NEXUS_S3_PERSISTENCE": "true",
        "PERSISTENCE_S3_ENDPOINT": "https://abc123.r2.cloudflarestorage.com",
        "PERSISTENCE_S3_REGION": "auto",
        "PERSISTENCE_S3_BUCKET": "nexus-stefan-hslu",
        "R2_ACCESS_KEY_ID": "AKIA1234",
        "R2_SECRET_ACCESS_KEY": "secret/key+abc=",
    }


# ---------------------------------------------------------------------------
# Feature-flag gating
# ---------------------------------------------------------------------------


def _executable_lines(script: str) -> list[str]:
    """Script lines that bash will actually run — comments stripped.

    Needed because the rendered header *explains* why it no longer
    uses ``install -m 600 /dev/stdin``, so a naive substring check
    would match the explanation rather than a real invocation.
    """
    return [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]


@pytest.mark.parametrize(
    "value",
    ["true"],
)
def test_is_enabled_accepts_lowercase_true_only(value: str) -> None:
    """Strict ``"true"`` match — ensures operators can't get a
    half-enabled state from shell-truthy variants."""
    assert is_enabled({FEATURE_FLAG_ENV: value}) is True


@pytest.mark.parametrize(
    "value",
    ["", "True", "TRUE", "1", "yes", "Y", "false", "off"],
)
def test_is_enabled_rejects_non_canonical_truthy(value: str) -> None:
    """Anything that isn't literal ``"true"`` returns False —
    intentionally strict so a misspelled env var produces a
    clean skip rather than a silent-flip."""
    assert is_enabled({FEATURE_FLAG_ENV: value}) is False


def test_is_enabled_returns_false_when_var_missing() -> None:
    assert is_enabled({}) is False


# ---------------------------------------------------------------------------
# Env-var parsing
# ---------------------------------------------------------------------------


def test_build_endpoint_from_env_happy_path() -> None:
    """All five env vars present → populated :class:`S3Endpoint`."""
    endpoint = build_endpoint_from_env(_good_env())
    assert endpoint is not None
    assert endpoint.bucket == "nexus-stefan-hslu"
    assert endpoint.region == "auto"
    assert endpoint.endpoint == "https://abc123.r2.cloudflarestorage.com"


@pytest.mark.parametrize(
    "missing_var",
    [
        "PERSISTENCE_S3_ENDPOINT",
        "PERSISTENCE_S3_REGION",
        "PERSISTENCE_S3_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ],
)
def test_build_endpoint_from_env_returns_none_on_any_missing(missing_var: str) -> None:
    """Strict all-or-nothing — any missing env var returns ``None``
    so a half-configured stack falls back to the legacy path
    instead of silently picking up only some of the values."""
    env = _good_env()
    del env[missing_var]
    assert build_endpoint_from_env(env) is None


@pytest.mark.parametrize(
    "missing_var",
    [
        "PERSISTENCE_S3_ENDPOINT",
        "PERSISTENCE_S3_REGION",
        "PERSISTENCE_S3_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ],
)
def test_build_endpoint_from_env_treats_empty_as_missing(missing_var: str) -> None:
    """Empty-string env var is the same as missing — guards against
    operators accidentally setting ``EXPORT VAR=`` (no value).
    Parametrized over ALL five required vars so a regression that
    treats any single one differently (e.g. ``REGION`` having a
    fallback default) gets caught."""
    env = _good_env()
    env[missing_var] = ""
    assert build_endpoint_from_env(env) is None


def test_build_endpoint_from_env_charset_error_bubbles_up() -> None:
    """If env contains a value that fails the S3Endpoint constructor
    charset gate, the error propagates so the operator sees what
    they misconfigured — we don't quietly swallow it as None."""
    env = _good_env()
    env["PERSISTENCE_S3_BUCKET"] = "Bad Bucket With Spaces"
    with pytest.raises(_s3.S3PersistenceError, match="bucket"):
        build_endpoint_from_env(env)


# ---------------------------------------------------------------------------
# Canonical targets
# ---------------------------------------------------------------------------


def test_standard_targets_returns_canonical_pair() -> None:
    """Smoke + locks the v1.0 fixture. If the
    ``stacks/{gitea,dify}/docker-compose.yml`` files change the
    POSTGRES_USER or POSTGRES_DB values, this test starts failing
    and a future maintainer knows to align the fixture."""
    postgres, rsync = standard_targets()
    pg_by_container = {p.container: p for p in postgres}

    # Gitea — matches stacks/gitea/docker-compose.yml line 67/68
    assert pg_by_container["gitea-db"].database == "gitea"
    assert pg_by_container["gitea-db"].user == "nexus-gitea"
    # Dify — matches stacks/dify/docker-compose.yml line 180/182
    assert pg_by_container["dify-db"].database == "dify"
    assert pg_by_container["dify-db"].user == "nexus-dify"
    # HedgeDoc — matches stacks/hedgedoc/docker-compose.yml. Added in
    # issue #618 alongside the admin-auth fix because a teardown
    # without persistence would discard every note + upload.
    assert pg_by_container["hedgedoc-db"].database == "hedgedoc"
    assert pg_by_container["hedgedoc-db"].user == "nexus-hedgedoc"

    rsync_by_name = {r.name: r for r in rsync}
    # All seven rsync targets returned by standard_targets() — gitea x2
    # + dify x3 are the original RFC 0001 set; metabase x1 was added
    # for issue #528, hedgedoc-uploads x1 for issue #618. The RFC
    # document itself still lists only gitea + dify until a future
    # storage-layout revision lands.
    for required in (
        "gitea-repos",
        "gitea-lfs",
        "dify-storage",
        "dify-weaviate",
        "dify-plugins",
        "metabase-data",
        "hedgedoc-uploads",
    ):
        assert required in rsync_by_name, f"missing required rsync target: {required}"

    # db/ and redis/ subdirs deliberately NOT in the list — they're
    # captured via pg_dump / regeneratable. Regression for the
    # "exclude" theme that's appeared in multiple Copilot rounds.
    for name in rsync_by_name:
        assert not name.endswith("-db"), f"db/ subdir wrongly in rsync list: {name}"
        assert "redis" not in name, f"redis/ subdir wrongly in rsync list: {name}"


def test_standard_targets_s3_subpaths_match_rfc_layout() -> None:
    """The S3 subpaths must match the established storage-layout
    convention: ``gitea/repos``, ``gitea/lfs``, ``dify/storage``,
    ``dify/weaviate``, ``dify/plugins`` (RFC 0001 §"Storage layout"),
    and ``metabase/data`` (extends the same convention, added in
    issue #528). Mismatch would put data under the wrong prefix and
    break restore."""
    _, rsync = standard_targets()
    sub_by_name = {r.name: r.s3_subpath for r in rsync}
    assert sub_by_name["gitea-repos"] == "gitea/repos"
    assert sub_by_name["gitea-lfs"] == "gitea/lfs"
    assert sub_by_name["dify-storage"] == "dify/storage"
    assert sub_by_name["dify-weaviate"] == "dify/weaviate"
    assert sub_by_name["dify-plugins"] == "dify/plugins"
    assert sub_by_name["metabase-data"] == "metabase/data"
    assert sub_by_name["hedgedoc-uploads"] == "hedgedoc/uploads"


def test_standard_targets_metabase_has_no_postgres_dump() -> None:
    """Metabase uses an internal H2 DB stored under /metabase-data,
    captured via rsync. The OSS image deliberately does NOT run a
    sidecar Postgres — pinning that here so a future 'switch metabase
    to Postgres' refactor remembers to ALSO add a PostgresDumpTarget."""
    postgres, _ = standard_targets()
    pg_containers = {p.container for p in postgres}
    assert "metabase-db" not in pg_containers
    assert "metabase" not in pg_containers


def test_standard_stop_compose_files_matches_rsync_targets() -> None:
    """Symmetry invariant: every stack with an RsyncTarget in
    standard_targets() MUST be stopped before the snapshot, otherwise
    rsync sees torn writes / half-uploaded files. The reverse is also
    enforced — no stop entry without a matching rsync consumer, so the
    stop list doesn't quietly accumulate dead entries.

    Postgres-only stacks (no rsync target) are intentionally NOT in
    the stop list — pg_dump is MVCC-safe against live writers.

    Regression guard for #619: HedgeDoc was added to standard_targets()
    with an `hedgedoc-uploads` RsyncTarget but the corresponding stop
    entry was missed in the first commit, leaving the uploads dir
    racing with rsync on every snapshot."""
    _, rsync = standard_targets()

    # Each rsync target's name is `<stack>-<subdir>` (gitea-repos,
    # hedgedoc-uploads, ...). Stack name = first segment.
    stacks_with_rsync = {r.name.split("-", 1)[0] for r in rsync}

    # Each compose-file path is `/opt/docker-server/stacks/<stack>/docker-compose.yml`.
    stacks_in_stop_list = {
        path.removeprefix("/opt/docker-server/stacks/").removesuffix("/docker-compose.yml")
        for path in _STANDARD_STOP_COMPOSE_FILES
    }

    missing_from_stop = stacks_with_rsync - stacks_in_stop_list
    assert not missing_from_stop, (
        f"Stacks have an RsyncTarget but no stop entry — "
        f"snapshot will race against live writes: {sorted(missing_from_stop)}"
    )

    dead_stop_entries = stacks_in_stop_list - stacks_with_rsync
    assert not dead_stop_entries, (
        f"Stop list contains stacks with no RsyncTarget — "
        f"unnecessary downtime during snapshot: {sorted(dead_stop_entries)}"
    )


# ---------------------------------------------------------------------------
# Combined-script render
# ---------------------------------------------------------------------------


def _endpoint() -> _s3.S3Endpoint:
    return _s3.S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="AKIA1234",
        secret_key="secret123",
        bucket="nexus-test",
    )


def test_combined_script_contains_both_config_and_body() -> None:
    """The combined script must include the rclone config block AND
    the restore body — caller relies on the single-script invariant
    to keep the SSH round-trip atomic."""
    postgres, rsync = standard_targets()
    script = render_combined_restore_script(
        endpoint=_endpoint(),
        postgres_targets=postgres,
        rsync_targets=rsync,
    )
    # rclone profile heading
    assert f"[{_s3.RCLONE_PROFILE}]" in script
    # restore-body landmarks
    assert "snapshots/latest.txt" in script
    assert "pg_restore" in script


def test_combined_script_writes_config_atomically_at_mode_600() -> None:
    """The rclone config file holds the R2 secret access key. Must
    land at mode 600 atomically — no chmod race window where the
    file exists with default permissions."""
    script = render_combined_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    # mktemp into the same directory, then rename. No unlink-then-
    # reopen window for a symlink to be planted in, mode 0600 by
    # mktemp's construction, and atomic for a concurrent reader.
    assert 'RCLONE_CONF_TMP=$(mktemp "$HOME/.config/rclone/.rclone.conf.XXXXXX")' in script
    assert 'cat > "$RCLONE_CONF_TMP"' in script
    # -T, not a bare mv: a destination that happens to be a DIRECTORY
    # would otherwise make mv move the credential file *into* it, and
    # the EXIT trap would then clean a path that no longer holds it.
    assert 'mv -fT "$RCLONE_CONF_TMP" "$HOME/.config/rclone/rclone.conf"' in script
    assert 'mv -f "$RCLONE_CONF_TMP"' not in script
    # A credentials-bearing temp file must not survive a mid-script exit.
    assert "trap 'rm -f \"$RCLONE_CONF_TMP\"' EXIT" in script
    # The destination is never opened directly, which is what removes
    # the symlink-follow path entirely.
    assert 'cat > "$HOME/.config/rclone/rclone.conf"' not in script
    # Regression guard for the Ubuntu 26.04 failure: `install` asking
    # uutils to resolve a path to the heredoc died with a bare
    # "install: No such file or directory" before any body output.
    executable = _executable_lines(script)
    assert not [ln for ln in executable if "/dev/stdin" in ln]
    assert not [ln for ln in executable if ln.strip().startswith("install")]


def test_combined_script_starts_with_shebang_and_safety_pragmas() -> None:
    script = render_combined_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script


def test_combined_script_orders_config_before_body() -> None:
    """Body needs the config in place to find the rclone profile.
    Config write must come first."""
    script = render_combined_restore_script(
        endpoint=_endpoint(),
        postgres_targets=(),
        rsync_targets=(),
    )
    config_pos = script.find("RCLONE_CONF_TMP=")
    body_pos = script.find("looking up latest snapshot")
    assert 0 < config_pos < body_pos


# ---------------------------------------------------------------------------
# restore_from_s3 — outcome dispatch
# ---------------------------------------------------------------------------


def _fake_ssh(stdout: str) -> MagicMock:
    """SSHClient stub whose ``run_script`` returns a
    CompletedProcess-shaped object with the given stdout."""
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        args=["ssh", "nexus", "bash", "-s"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )
    return ssh


def test_restore_from_s3_skips_when_feature_flag_off() -> None:
    """No flag → no S3 path. ``ssh.run_script`` must NOT be called
    — that's the whole point of the early skip."""
    ssh = _fake_ssh("")
    result = restore_from_s3(ssh, env={"NEXUS_S3_PERSISTENCE": "false"})
    assert isinstance(result, S3RestoreSkipped)
    assert result.reason == "feature_flag_off"
    ssh.run_script.assert_not_called()


def test_restore_from_s3_skips_when_env_incomplete(capsys: pytest.CaptureFixture[str]) -> None:
    """Flag on but a required env var missing — should warn to
    stderr (operator-actionable) and skip."""
    env = _good_env()
    del env["PERSISTENCE_S3_BUCKET"]
    ssh = _fake_ssh("")
    result = restore_from_s3(ssh, env=env)
    assert isinstance(result, S3RestoreSkipped)
    assert result.reason == "no_endpoint_env"
    ssh.run_script.assert_not_called()
    captured = capsys.readouterr()
    assert "feature flag" in captured.err
    # Message now lists the SPECIFIC missing vars (instead of dumping
    # the entire required-vars tuple) — regression for round-3 #3217012538.
    assert "PERSISTENCE_S3_BUCKET" in captured.err
    assert "Skipping S3 restore" in captured.err


def test_restore_from_s3_returns_fresh_start_when_bucket_empty() -> None:
    """Bucket has no latest.txt → restore script outputs the
    fresh-start marker → orchestration returns Skipped /
    fresh_start_empty_s3."""
    ssh = _fake_ssh("fresh-start: no snapshot in S3, leaving local state empty\n")
    result = restore_from_s3(ssh, env=_good_env())
    assert isinstance(result, S3RestoreSkipped)
    assert result.reason == "fresh_start_empty_s3"
    ssh.run_script.assert_called_once()


def test_restore_from_s3_returns_applied_with_timestamp() -> None:
    """Successful restore → ``Applied`` with the parsed timestamp."""
    ssh = _fake_ssh(
        "→ restore: looking up latest snapshot\n"
        "→ restore: using snapshot snapshots/20260511T120000Z\n"
        "→ restore: pulling filesystem trees\n"
        "→ restore: applying postgres dumps\n"
        "✓ restore complete from snapshots/20260511T120000Z\n",
    )
    result = restore_from_s3(ssh, env=_good_env())
    assert isinstance(result, S3RestoreApplied)
    assert result.snapshot_timestamp == "20260511T120000Z"


def test_restore_from_s3_returns_applied_unknown_when_log_shape_drifts() -> None:
    """If the server-side log lines change shape (we can't find the
    "using snapshot" marker), we still return Applied — rc=0 means
    the data is in place, just with a less-informative diagnostic."""
    ssh = _fake_ssh("✓ restore complete\n")  # no "using snapshot" line
    result = restore_from_s3(ssh, env=_good_env())
    assert isinstance(result, S3RestoreApplied)
    assert result.snapshot_timestamp == "(unknown)"


def test_restore_from_s3_propagates_called_process_error() -> None:
    """If the remote script exits non-zero, the underlying
    CalledProcessError must propagate — pipeline.py should hard-fail
    rather than let the spinup proceed with half-populated data."""
    ssh = MagicMock()
    ssh.run_script.side_effect = subprocess.CalledProcessError(
        returncode=2,
        cmd=["ssh", "nexus", "bash", "-s"],
        output="✗ restore-failed: latest.txt has invalid timestamp\n",
    )
    with pytest.raises(subprocess.CalledProcessError):
        restore_from_s3(ssh, env=_good_env())


# ---------------------------------------------------------------------------
# render_combined_snapshot_script — shape contract (PR-4)
# ---------------------------------------------------------------------------


def test_combined_snapshot_script_writes_config_and_body() -> None:
    """Snapshot-side counterpart to
    :func:`test_combined_script_contains_both_config_and_body` for
    the restore direction. Single rendered script must:

    1. Write the rclone config at mode 600 to
       ``~/.config/rclone/rclone.conf`` atomically via same-dir mktemp.
    2. Then include the snapshot body — namespaced ``STACK`` /
       ``TEMPLATE_VERSION`` envs, the timestamp, the per-source
       rclone-sync invocations, and the latest.txt pointer write.
    """
    endpoint = _endpoint()
    postgres_targets, rsync_targets = standard_targets()
    script = render_combined_snapshot_script(
        endpoint=endpoint,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        timestamp="20260511T120000Z",
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
    )
    assert 'mv -fT "$RCLONE_CONF_TMP"' in script
    executable = _executable_lines(script)
    assert not [ln for ln in executable if "/dev/stdin" in ln]
    assert not [ln for ln in executable if ln.strip().startswith("install")]
    assert ".config/rclone/rclone.conf" in script
    assert "STACK=nexus-test" in script
    assert "TEMPLATE_VERSION=v1.0.0" in script
    assert "20260511T120000Z" in script


def test_combined_snapshot_script_orders_config_before_body() -> None:
    """rclone config write must precede the snapshot body — body
    invokes ``rclone`` which reads that config file."""
    endpoint = _endpoint()
    postgres_targets, rsync_targets = standard_targets()
    script = render_combined_snapshot_script(
        endpoint=endpoint,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        timestamp="20260511T120000Z",
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
    )
    config_pos = script.index("RCLONE_CONF_TMP=")
    body_pos = script.index("STACK=nexus-test")
    assert 0 < config_pos < body_pos


def test_combined_snapshot_script_starts_with_safety_pragmas() -> None:
    """First lines must be shebang + ``set -euo pipefail`` so a
    failure in the rclone-config write aborts before the snapshot
    body runs against a missing/empty config."""
    endpoint = _endpoint()
    postgres_targets, rsync_targets = standard_targets()
    script = render_combined_snapshot_script(
        endpoint=endpoint,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        timestamp="20260511T120000Z",
        postgres_targets=postgres_targets,
        rsync_targets=rsync_targets,
    )
    lines = script.splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert "set -euo pipefail" in lines[:5]


# ---------------------------------------------------------------------------
# snapshot_to_s3 — outcome dispatch (PR-4)
# ---------------------------------------------------------------------------


def test_snapshot_to_s3_skips_when_feature_flag_off() -> None:
    """No flag → no SSH round-trip. The teardown caller treats this
    as "stack hasn't opted in" and proceeds with the legacy path."""
    ssh = _fake_ssh("")
    result = snapshot_to_s3(
        ssh,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        env={"NEXUS_S3_PERSISTENCE": "false"},
    )
    assert isinstance(result, S3SnapshotSkipped)
    assert result.reason == "feature_flag_off"
    ssh.run_script.assert_not_called()


def test_snapshot_to_s3_skips_with_warning_on_missing_env(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Flag on but a required env var missing — must warn loudly
    (operator opted in to S3 but config is broken) and refuse to
    proceed. CLI maps this to rc=2 → teardown aborts."""
    env = _good_env()
    del env["PERSISTENCE_S3_BUCKET"]
    ssh = _fake_ssh("")
    result = snapshot_to_s3(
        ssh,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        env=env,
    )
    assert isinstance(result, S3SnapshotSkipped)
    assert result.reason == "no_endpoint_env"
    ssh.run_script.assert_not_called()
    captured = capsys.readouterr()
    # Must name the specific missing var so the operator doesn't
    # have to grep their secret store for the full list.
    assert "PERSISTENCE_S3_BUCKET" in captured.err
    # Must surface the abort intent — "Refusing to teardown" is the
    # phrase the CLI consumer relies on for log triage.
    assert "Refusing to teardown" in captured.err


def test_snapshot_to_s3_returns_applied_with_factory_timestamp() -> None:
    """Successful snapshot → ``Applied`` carrying the timestamp
    produced by ``timestamp_factory``. Tests inject a deterministic
    factory so the assertion isn't time-dependent."""
    ssh = _fake_ssh("✓ snapshot complete: snapshots/20260511T120000Z\n")
    result = snapshot_to_s3(
        ssh,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        env=_good_env(),
        timestamp_factory=lambda: "20260511T120000Z",
    )
    assert isinstance(result, S3SnapshotApplied)
    assert result.timestamp == "20260511T120000Z"
    ssh.run_script.assert_called_once()


def test_snapshot_to_s3_passes_stack_slug_into_rendered_script() -> None:
    """The stack_slug + template_version provided by the caller
    must reach the rendered bash — they end up in the manifest
    written next to the snapshot, which is what the v1.1 "latest by
    sort order" cleanup cron uses to identify same-stack snapshots."""
    ssh = _fake_ssh("✓ snapshot complete\n")
    snapshot_to_s3(
        ssh,
        stack_slug="nexus-stefan-hslu",
        template_version="v1.4.2",
        env=_good_env(),
        timestamp_factory=lambda: "20260511T120000Z",
    )
    rendered_script = ssh.run_script.call_args.args[0]
    assert "STACK=nexus-stefan-hslu" in rendered_script
    assert "TEMPLATE_VERSION=v1.4.2" in rendered_script


def test_snapshot_to_s3_propagates_called_process_error() -> None:
    """Atomicity contract: any non-zero exit from the rendered bash
    must propagate as CalledProcessError so the teardown caller
    aborts before ``tofu destroy``. Without this, a partial
    snapshot followed by a destroy would lose data."""
    ssh = MagicMock()
    ssh.run_script.side_effect = subprocess.CalledProcessError(
        returncode=2,
        cmd=["ssh", "nexus", "bash", "-s"],
        output="✗ snapshot-failed: rclone check drift on gitea-data\n",
    )
    with pytest.raises(subprocess.CalledProcessError):
        snapshot_to_s3(
            ssh,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            env=_good_env(),
            timestamp_factory=lambda: "20260511T120000Z",
        )


def test_snapshot_to_s3_uses_default_timestamp_factory_when_none() -> None:
    """Production caller passes ``timestamp_factory=None`` →
    snapshot_to_s3 falls back to the real
    ``_build_snapshot_timestamp``. The fallback must produce a
    string matching the ``YYYYMMDDTHHMMSSZ`` shape (the s3_persistence
    snapshot script's strict charset accepts only ``[0-9A-Za-z_-]+``,
    no colons)."""
    import re

    ssh = _fake_ssh("✓ snapshot complete\n")
    result = snapshot_to_s3(
        ssh,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        env=_good_env(),
    )
    assert isinstance(result, S3SnapshotApplied)
    assert re.fullmatch(r"\d{8}T\d{6}Z", result.timestamp)


def test_forgejo_is_persisted_because_it_is_a_core_service() -> None:
    """A git forge on every server must not lose its repositories to a
    scheduled teardown.

    While Forgejo was opt-in, an operator enabling it accepted that the
    default `rebuild` lifecycle destroys unlisted bind mounts. As a core
    service it is deployed everywhere, so the coverage is not optional
    any more — and the mapping must match
    `stacks/forgejo/docker-compose.yml`, which is what this asserts.
    """
    postgres, rsync = standard_targets()

    pg = {p.container: p for p in postgres}
    assert pg["forgejo-db"].database == "forgejo"
    assert pg["forgejo-db"].user == "nexus-forgejo"

    paths = {r.name: r.local_path for r in rsync}
    assert paths["forgejo-repos"] == "/mnt/nexus-data/forgejo/repos"
    assert paths["forgejo-lfs"] == "/mnt/nexus-data/forgejo/lfs"

    # Stopping the stack before the rsync is what makes the copy
    # consistent; the invariant test pairs this with the targets above.
    assert "/opt/docker-server/stacks/forgejo/docker-compose.yml" in _STANDARD_STOP_COMPOSE_FILES


def test_the_runner_stack_is_deliberately_not_persisted() -> None:
    """Its `.runner` file is regenerated from the shared secret on every
    start and the rest is a build cache. Snapshotting either would cost
    bandwidth to restore something reproducible or worthless."""
    postgres, rsync = standard_targets()

    assert not [p for p in postgres if "runner" in p.container]
    assert not [r for r in rsync if "runner" in r.name]
    assert not [f for f in _STANDARD_STOP_COMPOSE_FILES if "forgejo-runner" in f]

"""Tests for the ``nexus-deploy s3-snapshot`` CLI dispatcher.

Focused on the exit-code mapping in ``_s3_snapshot``: every
``S3SnapshotSkipped`` reason must map to a deliberate rc, not fall
through to a default. PR #600 added ``no_snapshot_source`` as a new
graceful (rc=0) skip reason — the original PR forgot to add the
dispatcher branch, so it silently fell through to rc=2 and made
scheduled teardowns red on the exact deads7-fork case the skip was
meant to handle. These tests pin the contract.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from nexus_deploy import s3_restore as _s3_restore
from nexus_deploy.__main__ import _s3_snapshot
from nexus_deploy.pipeline import SnapshotResult


@pytest.fixture(autouse=True)
def feature_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the top-of-handler feature-flag + stack-slug checks
    so each test exercises the post-run_snapshot exit-code dispatcher.

    Env-var names match what the snapshot code ACTUALLY reads (see
    s3_restore._ENV_*): three ``PERSISTENCE_S3_*`` for the persistence
    bucket coords, plus the project-wide ``R2_ACCESS_KEY_ID`` /
    ``R2_SECRET_ACCESS_KEY``. PERSISTENCE_STACK_SLUG + PERSISTENCE_TEMPLATE_VERSION
    are required by the dispatcher itself before it calls run_snapshot."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    monkeypatch.setenv("PERSISTENCE_S3_ENDPOINT", "https://r2.example.com")
    monkeypatch.setenv("PERSISTENCE_S3_BUCKET", "snapshots")
    monkeypatch.setenv("PERSISTENCE_S3_REGION", "auto")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("PERSISTENCE_STACK_SLUG", "nexus-test")
    monkeypatch.setenv("PERSISTENCE_TEMPLATE_VERSION", "v1.0.0")


def test_s3_snapshot_rc0_when_snapshot_source_missing() -> None:
    """The deads7-fork case: partial state exists but neither the
    server nor the ssh_service_token are in it. ``run_snapshot``
    returns ``S3SnapshotSkipped(reason='no_snapshot_source')`` and
    the CLI must return 0 so the scheduled teardown stays green and
    proceeds to ``tofu destroy``. Regression guard for the original
    PR #600 dispatcher fall-through bug — the branch landed in
    pipeline.py but not in __main__.py, so the rc was 2 instead of 0."""
    with patch(
        "nexus_deploy.__main__._pipeline.run_snapshot",
        return_value=SnapshotResult(
            outcome=_s3_restore.S3SnapshotSkipped(reason="no_snapshot_source"),
        ),
    ):
        rc = _s3_snapshot([])
    assert rc == 0


def test_s3_snapshot_rc0_when_no_state_to_snapshot() -> None:
    """Issue #564 case: state file is entirely empty (setup ran but
    spin-up never executed any tofu apply). Same rc=0 contract."""
    with patch(
        "nexus_deploy.__main__._pipeline.run_snapshot",
        return_value=SnapshotResult(
            outcome=_s3_restore.S3SnapshotSkipped(reason="no_state_to_snapshot"),
        ),
    ):
        rc = _s3_snapshot([])
    assert rc == 0


def test_s3_snapshot_rc2_when_run_snapshot_reports_no_endpoint_env() -> None:
    """no_endpoint_env is a run_snapshot-reported skip reason (the
    feature flag is on but the S3 endpoint/bucket/creds env vars are
    missing) — the dispatcher must map it to rc=2 because proceeding
    to tofu destroy without a verified snapshot risks data loss.

    Exercises the dispatcher branch directly via a patched
    run_snapshot return value. The previous version of this test
    deleted PERSISTENCE_S3_ENDPOINT and called _s3_snapshot([]) — but
    the dispatcher doesn't read that env var itself; the check lives
    inside snapshot_to_s3 (which run_snapshot calls). With
    run_snapshot unpatched the test was effectively testing whatever
    happened to fail first in the real preflight (local tofu state,
    R2 access), not the no_endpoint_env mapping. Patch it explicitly
    so the assertion lines up with the contract."""
    with patch(
        "nexus_deploy.__main__._pipeline.run_snapshot",
        return_value=SnapshotResult(
            outcome=_s3_restore.S3SnapshotSkipped(reason="no_endpoint_env"),
        ),
    ):
        rc = _s3_snapshot([])
    assert rc == 2


def test_s3_snapshot_rc2_when_stack_slug_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dispatcher's OWN env check (PERSISTENCE_STACK_SLUG +
    PERSISTENCE_TEMPLATE_VERSION) must fire before run_snapshot is
    invoked — these are required to construct the snapshot path.
    Missing → rc=2 + stderr diagnostic listing the missing names."""
    monkeypatch.delenv("PERSISTENCE_STACK_SLUG", raising=False)
    # No patch on run_snapshot: this assertion must hold without
    # the dispatcher ever reaching that call.
    rc = _s3_snapshot([])
    assert rc == 2


def test_s3_snapshot_rc0_when_snapshot_applied() -> None:
    """Happy path: snapshot succeeded → rc=0, teardown proceeds."""
    with patch(
        "nexus_deploy.__main__._pipeline.run_snapshot",
        return_value=SnapshotResult(
            outcome=_s3_restore.S3SnapshotApplied(
                timestamp="2026-05-18T05-00-00Z",
            ),
        ),
    ):
        rc = _s3_snapshot([])
    assert rc == 0

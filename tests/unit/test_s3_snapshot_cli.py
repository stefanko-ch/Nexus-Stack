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
    """Bypass the top-of-handler feature-flag check so we exercise
    the post-run_snapshot exit-code dispatcher."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    monkeypatch.setenv("PERSISTENCE_S3_ENDPOINT", "https://r2.example.com")
    monkeypatch.setenv("PERSISTENCE_S3_BUCKET", "snapshots")
    monkeypatch.setenv("PERSISTENCE_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("PERSISTENCE_S3_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("PERSISTENCE_S3_REGION", "auto")
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


def test_s3_snapshot_rc2_when_endpoint_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the feature flag is on but credentials/endpoint env vars
    are missing, the dispatcher returns rc=2 so the teardown aborts.
    Verifies the only-known-good-reasons-are-rc=0 contract: any new
    skip reason added in the future must be EXPLICITLY enumerated in
    the dispatcher (don't accidentally bucket it as rc=0 either)."""
    # Drop one env var so the handler's own check fires before
    # run_snapshot would.
    monkeypatch.delenv("PERSISTENCE_S3_ENDPOINT", raising=False)
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

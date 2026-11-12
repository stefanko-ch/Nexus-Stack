"""Shared pytest fixtures for nexus_deploy tests.

Deliberately kept small — most fixtures (mock Infisical API, mock
SSH server, fake SECRETS_JSON shapes, etc.) live alongside the
modules that need them in per-module test files, since pytest
auto-discovers fixtures from any ``conftest.py`` on the test path.
This file holds only the cross-cutting helpers used by enough
modules that defining them once is worth the indirection.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory as Path.

    Wrapper around pytest's built-in `tmp_path` for typing clarity
    and to make it explicit at the test-call site that we're using
    isolated filesystem state.
    """
    return tmp_path


@pytest.fixture
def fake_secrets_json() -> dict[str, str]:
    """Minimal valid SECRETS_JSON shape — used as a starter fixture
    by tests that don't care about the specific field set.

    Tests that exercise field-level behaviour (most of
    ``test_config.py``, ``test_orchestrator.py``, etc.) define their
    own richer fixtures locally so this stays a stable cross-cutting
    minimum.
    """
    return {
        "domain": "example.com",
        "admin_email": "admin@example.com",
        # Match the production default in tofu/stack/variables.tf — never
        # bake "admin"/"root"/"postgres" into examples (CLAUDE.md service-
        # account naming rule).
        "admin_username": "nexus",
    }


@pytest.fixture(autouse=True)
def _no_transport_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dropped connection is retried after a pause; tests do not wait for it.

    Every test that simulates `ssh` exiting 255 would otherwise sleep
    through each retry (`_remote._retry_transport`).
    """
    monkeypatch.setattr("nexus_deploy._remote._TRANSPORT_RETRY_DELAY_S", 0.0)

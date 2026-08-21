"""Tests for the `nexus-deploy snapshot-*` / `server-poweroff` handlers.

The module functions are monkeypatched, so nothing here touches the
network; what is under test is the CLI contract the workflows depend
on:

* **Exit codes.** ``snapshot-resolve`` is three-valued and the
  workflow branches on it — 1 means "build fresh", 2 means "stop".
  Collapsing those would either discard a good snapshot or hide an
  outage.
* **stdout is machine-readable and stdout-only.** The workflow evals
  ``KEY=value`` lines; a stray human message on stdout would break it.
* **Prune is dry-run by default.** Deleting a snapshot is
  irreversible and may be the only copy of most stacks' data.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_deploy import __main__ as cli
from nexus_deploy import hetzner_snapshot as _hsnap
from nexus_deploy.hetzner_snapshot import HetznerSnapshotError, Snapshot

EPOCH = "0123456789abcdef0123456789abcdef"


def _snap(image_id: int = 99, created: str = "2026-08-05T21:00:00+00:00") -> Snapshot:
    return Snapshot(
        image_id=image_id,
        description=f"nexus-example-com-{image_id}",
        created=created,
        disk_gb=160,
        architecture="x86",
        epoch=EPOCH,
        server_type="cx43",
    )


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HCLOUD_TOKEN", "tok")


def _kv(capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    """Parse the KEY=value lines a handler wrote to stdout."""
    out = capsys.readouterr().out
    pairs: dict[str, str] = {}
    for line in out.splitlines():
        assert "=" in line, f"non-machine-readable line on stdout: {line!r}"
        key, _, value = line.partition("=")
        pairs[key] = value
    return pairs


# ---------------------------------------------------------------------------
# server-poweroff
# ---------------------------------------------------------------------------


def test_poweroff_success(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(server_id: int, token: str) -> None:
        seen["server_id"] = server_id
        seen["token"] = token

    monkeypatch.setattr(_hsnap, "poweroff_server", _fake)
    assert cli._server_poweroff(["--server-id", "42"]) == 0
    assert seen == {"server_id": 42, "token": "tok"}


def test_poweroff_failure_is_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake(server_id: int, token: str) -> None:
        raise HetznerSnapshotError("still running")

    monkeypatch.setattr(_hsnap, "poweroff_server", _fake)
    assert cli._server_poweroff(["--server-id", "42"]) == 2


def test_poweroff_requires_server_id() -> None:
    assert cli._server_poweroff([]) == 2


def test_poweroff_rejects_non_integer_server_id() -> None:
    assert cli._server_poweroff(["--server-id", "abc"]) == 2


def test_poweroff_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HCLOUD_TOKEN", raising=False)
    assert cli._server_poweroff(["--server-id", "42"]) == 2


# ---------------------------------------------------------------------------
# snapshot-create
# ---------------------------------------------------------------------------


def test_create_emits_machine_readable_coordinates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 3)
    monkeypatch.setattr(_hsnap, "create_snapshot", lambda *a, **k: _snap())
    rc = cli._snapshot_create(
        [
            "--server-id",
            "42",
            "--domain-slug",
            "example-com",
            "--timestamp",
            "20260805T210000Z",
            "--epoch",
            EPOCH,
            "--server-type",
            "cx43",
        ],
    )
    assert rc == 0
    assert _kv(capsys) == {
        "SNAPSHOT_IMAGE_ID": "99",
        "SNAPSHOT_DISK_GB": "160",
        "SNAPSHOT_ARCH": "x86",
    }


def test_create_passes_epoch_and_timestamp_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(server_id: int, token: str, **kwargs: Any) -> Snapshot:
        seen.update(kwargs)
        seen["server_id"] = server_id
        return _snap()

    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 0)
    monkeypatch.setattr(_hsnap, "create_snapshot", _fake)
    cli._snapshot_create(
        [
            "--server-id",
            "42",
            "--domain-slug",
            "example-com",
            "--timestamp",
            "20260805T210000Z",
            "--epoch",
            EPOCH,
            "--server-type",
            "cx43",
        ],
    )
    assert seen["epoch"] == EPOCH
    assert seen["timestamp"] == "20260805T210000Z"
    assert seen["domain_slug"] == "example-com"
    assert seen["server_type"] == "cx43"


def test_create_warns_near_the_project_cap(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The cap is project-wide, so a sibling stack can block this one."""
    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 29)
    monkeypatch.setattr(_hsnap, "create_snapshot", lambda *a, **k: _snap())
    cli._snapshot_create(
        [
            "--server-id",
            "42",
            "--domain-slug",
            "example-com",
            "--timestamp",
            "20260805T210000Z",
        ],
    )
    assert "snapshots exist project-wide" in capsys.readouterr().err


def test_create_epoch_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stack predating credential_fingerprint must still snapshot."""
    seen: dict[str, Any] = {}

    def _fake(server_id: int, token: str, **kwargs: Any) -> Snapshot:
        seen.update(kwargs)
        return _snap()

    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 0)
    monkeypatch.setattr(_hsnap, "create_snapshot", _fake)
    rc = cli._snapshot_create(
        [
            "--server-id",
            "42",
            "--domain-slug",
            "example-com",
            "--timestamp",
            "20260805T210000Z",
        ],
    )
    assert rc == 0
    assert seen["epoch"] == ""


def test_create_failure_is_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed create must not let the teardown proceed to destroy."""

    def _fake(*_a: Any, **_k: Any) -> Snapshot:
        raise HetznerSnapshotError("action failed")

    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 0)
    monkeypatch.setattr(_hsnap, "create_snapshot", _fake)
    assert (
        cli._snapshot_create(
            [
                "--server-id",
                "42",
                "--domain-slug",
                "example-com",
                "--timestamp",
                "20260805T210000Z",
            ],
        )
        == 2
    )


def test_create_requires_domain_slug() -> None:
    assert cli._snapshot_create(["--server-id", "42", "--timestamp", "x"]) == 2


def test_create_flag_without_value_is_rc2() -> None:
    assert cli._snapshot_create(["--server-id"]) == 2


# ---------------------------------------------------------------------------
# snapshot-resolve — the three-valued contract
# ---------------------------------------------------------------------------


def test_resolve_found_is_rc0(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_hsnap, "resolve_latest", lambda *a, **k: _snap())
    assert cli._snapshot_resolve(["--domain-slug", "example-com"]) == 0
    assert _kv(capsys)["SNAPSHOT_IMAGE_ID"] == "99"


def test_resolve_not_found_is_rc1_not_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    """No snapshot is a normal state, not a failure.

    First-ever spin-up, pruned image, rotated epoch — all land here and
    all must degrade to a fresh ubuntu-24.04 build. Returning 2 would
    fail the workflow on a perfectly ordinary first deploy.
    """
    monkeypatch.setattr(_hsnap, "resolve_latest", lambda *a, **k: None)
    assert cli._snapshot_resolve(["--domain-slug", "example-com"]) == 1


def test_resolve_api_failure_is_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "Cannot tell" must not be treated as "there is none".

    Rebuilding fresh on an API outage would discard a snapshot that
    holds the only copy of most stacks' data.
    """

    def _fake(*_a: Any, **_k: Any) -> Snapshot | None:
        raise HetznerSnapshotError("HTTP 503")

    monkeypatch.setattr(_hsnap, "resolve_latest", _fake)
    assert cli._snapshot_resolve(["--domain-slug", "example-com"]) == 2


def test_resolve_forwards_expected_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(token: str, **kwargs: Any) -> Snapshot:
        seen.update(kwargs)
        return _snap()

    monkeypatch.setattr(_hsnap, "resolve_latest", _fake)
    cli._snapshot_resolve(
        ["--domain-slug", "example-com", "--expect-epoch", EPOCH],
    )
    assert seen["expect_epoch"] == EPOCH


def test_resolve_without_epoch_passes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(token: str, **kwargs: Any) -> Snapshot:
        seen.update(kwargs)
        return _snap()

    monkeypatch.setattr(_hsnap, "resolve_latest", _fake)
    cli._snapshot_resolve(["--domain-slug", "example-com"])
    assert seen["expect_epoch"] is None


def test_resolve_requires_domain_slug() -> None:
    assert cli._snapshot_resolve([]) == 2


# ---------------------------------------------------------------------------
# snapshot-prune
# ---------------------------------------------------------------------------


def test_prune_is_dry_run_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --apply nothing is deleted. Deletion is irreversible."""
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2), _snap(3)))
    monkeypatch.setattr(_hsnap, "select_prunable", lambda s, keep: (s[2],))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_prune(["--domain-slug", "example-com"]) == 0
    assert deleted == []
    err = capsys.readouterr().err
    assert "would delete" in err
    assert "--apply" in err


def test_prune_apply_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2), _snap(3)))
    monkeypatch.setattr(_hsnap, "select_prunable", lambda s, keep: (s[2],))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_prune(["--domain-slug", "example-com", "--apply"]) == 0
    assert deleted == [3]


def test_prune_forwards_keep(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake_select(snapshots: Any, keep: int) -> tuple[Snapshot, ...]:
        seen["keep"] = keep
        return ()

    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1),))
    monkeypatch.setattr(_hsnap, "select_prunable", _fake_select)
    cli._snapshot_prune(["--domain-slug", "example-com", "--keep", "1"])
    assert seen["keep"] == 1


def test_prune_defaults_to_keep_two(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake_select(snapshots: Any, keep: int) -> tuple[Snapshot, ...]:
        seen["keep"] = keep
        return ()

    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1),))
    monkeypatch.setattr(_hsnap, "select_prunable", _fake_select)
    cli._snapshot_prune(["--domain-slug", "example-com"])
    assert seen["keep"] == 2


def test_prune_nothing_to_do_is_rc0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1),))
    monkeypatch.setattr(_hsnap, "select_prunable", lambda s, keep: ())
    assert cli._snapshot_prune(["--domain-slug", "example-com"]) == 0


def test_prune_delete_failure_is_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(image_id: int, token: str) -> None:
        raise HetznerSnapshotError("HTTP 409")

    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2)))
    monkeypatch.setattr(_hsnap, "select_prunable", lambda s, keep: (s[1],))
    monkeypatch.setattr(_hsnap, "delete_snapshot", _fail)
    assert cli._snapshot_prune(["--domain-slug", "example-com", "--apply"]) == 2


def test_prune_list_failure_is_rc2(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_a: Any, **_k: Any) -> tuple[Snapshot, ...]:
        raise HetznerSnapshotError("HTTP 503")

    monkeypatch.setattr(_hsnap, "list_snapshots", _fail)
    assert cli._snapshot_prune(["--domain-slug", "example-com"]) == 2


def test_prune_requires_domain_slug() -> None:
    assert cli._snapshot_prune([]) == 2


def test_prune_rejects_non_integer_keep() -> None:
    assert cli._snapshot_prune(["--domain-slug", "example-com", "--keep", "many"]) == 2


# ---------------------------------------------------------------------------
# Dispatcher wiring
#
# The tests above call the handlers directly, which does not prove the
# subcommand names are actually routed. A typo in the dispatcher would
# otherwise only surface in a workflow run.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "handler"),
    [
        (["server-poweroff", "--server-id", "1"], "_server_poweroff"),
        (["snapshot-create", "--server-id", "1"], "_snapshot_create"),
        (["snapshot-resolve", "--domain-slug", "x"], "_snapshot_resolve"),
        (["snapshot-prune", "--domain-slug", "x"], "_snapshot_prune"),
    ],
)
def test_dispatcher_routes_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    handler: str,
) -> None:
    called: dict[str, list[str]] = {}

    def _fake(args: list[str]) -> int:
        called["args"] = args
        return 0

    monkeypatch.setattr(cli, handler, _fake)
    monkeypatch.setattr("sys.argv", ["nexus-deploy", *argv])
    assert cli.main() == 0
    # The subcommand name itself must be stripped before the handler
    # sees the flags.
    assert called["args"] == argv[1:]

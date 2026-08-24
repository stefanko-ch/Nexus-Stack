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
        status="available",
        image_gb=12.5,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the environment these handlers read.

    NEXUS_SNAPSHOT_LIMIT is cleared for every test, not just the ones
    that care. An operator running the suite on a machine where it is
    exported — which is now a normal thing to have, since the variable
    exists precisely so people set it — would otherwise see failures
    that have nothing to do with their change. Tests that need a value
    set it themselves; monkeypatch.setenv wins over this.
    """
    monkeypatch.setenv("HCLOUD_TOKEN", "tok")
    monkeypatch.delenv("NEXUS_SNAPSHOT_LIMIT", raising=False)


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
        # The billed size, so a retention policy's cost is visible in
        # the workflow log rather than guessed at.
        "SNAPSHOT_IMAGE_GB": "12.50",
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


def test_create_warns_near_the_cap(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The cap is shared, so a sibling stack can block this one.

    The message must not claim more than the number covers: an
    HCLOUD_TOKEN sees one project, the limit counts every project.
    """
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
    err = capsys.readouterr().err
    assert "in this project" in err
    assert "across ALL projects" in err
    # Against the constant, not a literal: if the documented default
    # ever changes, this should follow rather than fail.
    assert f"limit {_hsnap.DEFAULT_SNAPSHOT_LIMIT}" in err
    assert "SNAPSHOT_LIMIT" in err


def test_create_cap_warning_respects_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """29 snapshots against a raised limit of 100 is not noteworthy.

    The regression this guards: the threshold used to be the hardcoded
    default of 30, so every teardown from the 28th snapshot onwards
    advised the operator to raise a limit they had already raised.
    A warning that fires when nothing is wrong trains people to ignore
    warnings.
    """
    monkeypatch.setenv("NEXUS_SNAPSHOT_LIMIT", "100")
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
    assert "⚠" not in capsys.readouterr().err


def test_create_does_not_warn_on_an_empty_project(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A limit of 1 or 2 must not warn when nothing exists yet.

    `total >= limit - 2` is <= 0 for those limits, so the bare form
    held at zero snapshots and warned forever on a stack that had
    taken none. Rejecting small limits instead would be worse: an
    operator whose real cap IS 2 would be moved to 30 and warned never.
    """
    monkeypatch.setenv("NEXUS_SNAPSHOT_LIMIT", "2")
    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 0)
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
    assert "⚠" not in capsys.readouterr().err


def test_create_still_warns_at_a_small_limit_once_snapshots_exist(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The floor must not silence a genuinely tight limit."""
    monkeypatch.setenv("NEXUS_SNAPSHOT_LIMIT", "2")
    monkeypatch.setattr(_hsnap, "count_snapshots", lambda _t: 1)
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
    assert "⚠" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 30),
        ("", 30),
        ("100", 100),
        ("  100  ", 100),
        ("abc", 30),
        ("0", 30),
        ("-5", 30),
    ],
)
def test_snapshot_limit_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str | None,
    expected: int,
) -> None:
    """Unset or malformed falls back to Hetzner's documented default.

    Falling back rather than failing is deliberate: this runs inside
    snapshot-create during a teardown, and the value only governs a
    warning threshold. Aborting a teardown over a typo in an advisory
    setting would be wildly disproportionate.
    """
    if value is None:
        monkeypatch.delenv("NEXUS_SNAPSHOT_LIMIT", raising=False)
    else:
        monkeypatch.setenv("NEXUS_SNAPSHOT_LIMIT", value)
    assert cli._snapshot_limit() == expected

    # A silent fallback is the failure mode to guard against: the
    # operator set the variable, it was rejected, and nothing said so.
    err = capsys.readouterr().err
    supplied = "" if value is None else value.strip()
    default = str(_hsnap.DEFAULT_SNAPSHOT_LIMIT)
    rejected = supplied not in ("", default) and expected == _hsnap.DEFAULT_SNAPSHOT_LIMIT
    assert ("⚠" in err) is rejected


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


# ---------------------------------------------------------------------------
# Error logging (PR #651 review)
#
# HetznerSnapshotError messages embed up to 400 characters of the upstream
# HTTP response body (see _default_http_request), so they must never be
# printed verbatim. Our own _FlagError messages are a different case: they
# are text we wrote, and they are the diagnostic — "--server-id is
# required" has to stay readable.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("handler", "argv", "patch_target"),
    [
        ("_server_poweroff", ["--server-id", "42"], "poweroff_server"),
        ("_snapshot_resolve", ["--domain-slug", "example-com"], "resolve_latest"),
        ("_snapshot_prune", ["--domain-slug", "example-com"], "list_snapshots"),
        ("_snapshot_purge", ["--domain-slug", "example-com"], "list_snapshots"),
    ],
)
def test_api_errors_are_logged_by_type_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    handler: str,
    argv: list[str],
    patch_target: str,
) -> None:
    def _raise(*_a: Any, **_k: Any) -> Any:
        raise HetznerSnapshotError("HTTP 403 body={'token': 'SUPERSECRET'}")

    monkeypatch.setattr(_hsnap, patch_target, _raise)
    assert getattr(cli, handler)(argv) == 2

    out = capsys.readouterr()
    combined = out.err + out.out
    assert "HetznerSnapshotError" in combined
    assert "SUPERSECRET" not in combined
    assert "HTTP 403" not in combined


def test_flag_errors_keep_their_message(capsys: pytest.CaptureFixture[str]) -> None:
    """Our own messages are the diagnostic and must survive.

    Redacting these too would turn every misuse into an unhelpful
    "_FlagError" with no indication of which flag was wrong.
    """
    assert cli._snapshot_create(["--server-id", "42"]) == 2
    assert "--domain-slug is required" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# snapshot-purge — destroy-all's cleanup
#
# A Hetzner snapshot survives `tofu destroy` by design, so destroy-all
# leaves one behind unless something deletes it explicitly. What makes
# that worse than a stray euro: the destroy takes all 81 random_*
# resources with it, the next initial-setup mints a new credential
# epoch, and the epoch guard then refuses the old image forever. It is
# unusable AND it occupies one of the 30 per-account snapshot slots.
# ---------------------------------------------------------------------------


def test_purge_is_dry_run_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same guarantee as prune: deletion is irreversible, so opt in."""
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2)))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_purge(["--domain-slug", "example-com"]) == 0
    assert deleted == []
    err = capsys.readouterr().err
    assert "would delete" in err
    assert "--apply" in err


def test_purge_apply_deletes_every_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of the command: nothing is kept back.

    This is what separates it from prune, whose `select_prunable`
    refuses `keep < 1` precisely so a retention pass can never empty a
    stack out.
    """
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2), _snap(3)))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_purge(["--domain-slug", "example-com", "--apply"]) == 0
    assert deleted == [1, 2, 3]


def test_purge_is_scoped_to_the_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never a project-wide wipe — other tenants share the account.

    The 30-snapshot limit is per account, so a multi-tenant project has
    other stacks' images sitting right next to these ones.
    """
    seen: dict[str, Any] = {}

    def _fake_list(_token: str, *, domain_slug: str) -> tuple[Snapshot, ...]:
        seen["domain_slug"] = domain_slug
        return ()

    monkeypatch.setattr(_hsnap, "list_snapshots", _fake_list)
    assert cli._snapshot_purge(["--domain-slug", "example-com", "--apply"]) == 0
    assert seen["domain_slug"] == "example-com"


def test_purge_on_empty_listing_is_a_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A stack that never took a snapshot must not fail destroy-all."""
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: ())
    assert cli._snapshot_purge(["--domain-slug", "example-com", "--apply"]) == 0
    assert "nothing to do" in capsys.readouterr().err


def test_purge_reports_images_it_cannot_delete(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A `creating` image is skipped loudly, not silently.

    The API cannot delete one mid-creation. Staying quiet would leave
    exactly the orphan this command exists to prevent — and nobody
    would know to go looking for it.
    """
    stuck = Snapshot(
        image_id=7,
        description="nexus-example-com-7",
        created="2026-08-05T21:00:00+00:00",
        disk_gb=160,
        architecture="x86",
        epoch=EPOCH,
        server_type="cx43",
        status="creating",
        image_gb=0.0,
    )
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), stuck))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_purge(["--domain-slug", "example-com", "--apply"]) == 0
    assert deleted == [1]
    err = capsys.readouterr().err
    assert "#7" in err
    assert "creating" in err


def test_purge_aborts_when_a_delete_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """rc=2 so destroy-all reports failure instead of a false all-clear."""
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2)))

    def _raise(image_id: int, token: str) -> None:
        raise HetznerSnapshotError("HTTP 409")

    monkeypatch.setattr(_hsnap, "delete_snapshot", _raise)
    assert cli._snapshot_purge(["--domain-slug", "example-com", "--apply"]) == 2


def test_purge_requires_domain_slug(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli._snapshot_purge([]) == 2
    assert "--domain-slug is required" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# snapshot-purge argument validation
#
# Strict, unlike the other snapshot handlers, because this one deletes and
# both ways of getting the arguments wrong are SILENT:
#
#   --keep 2   borrowed from snapshot-prune, ignored -> deletes everything
#              when the operator asked to retain two
#   --aply     a typo, ignored -> a real purge silently downgrades to a
#              dry run that exits 0, so destroy-all reports success while
#              the images it was meant to remove survive
#
# The two failures point in opposite directions, which is why neither
# default (accept-and-ignore) is defensible here.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--domain-slug", "example-com", "--apply", "--keep", "2"], "unknown argument '--keep'"),
        (["--domain-slug", "example-com", "--aply"], "unknown argument '--aply'"),
        (["--domain-slug", "example-com", "extra"], "unknown argument 'extra'"),
        (["--domain-slug", "example-com", "--apply", "--apply"], "--apply given more than once"),
        (["--domain-slug"], "--domain-slug requires a value"),
        # The slug is missing and --apply is swallowed as its value.
        # Without the flag-shaped-value check this reached the
        # DESTRUCTIVE path with domain_slug="--apply", matched no
        # snapshots, and exited 0 — reporting success while every real
        # snapshot survived. Same silent-no-op class the strict parsing
        # exists to remove.
        (["--domain-slug", "--apply"], "requires a value, got flag '--apply'"),
        (["--apply", "--domain-slug"], "--domain-slug requires a value"),
    ],
)
def test_purge_rejects_bad_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    expected: str,
) -> None:
    """rc=2 and, critically, nothing is deleted."""
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2), _snap(3)))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    assert cli._snapshot_purge(argv) == 2
    assert deleted == []
    assert expected in capsys.readouterr().err


def test_purge_rejects_keep_before_deleting_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression this validation exists for, stated on its own.

    `snapshot-purge --domain-slug X --apply --keep 2` used to delete
    every snapshot: --keep is a snapshot-prune option, it was ignored,
    and purge does not retain. An operator reaching for the flag they
    know from the sibling command got the opposite of what they asked
    for, irreversibly.
    """
    deleted: list[int] = []
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: (_snap(1), _snap(2), _snap(3)))
    monkeypatch.setattr(
        _hsnap,
        "delete_snapshot",
        lambda image_id, token: deleted.append(image_id),
    )

    rc = cli._snapshot_purge(["--domain-slug", "example-com", "--apply", "--keep", "2"])
    assert rc == 2
    assert deleted == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--domain-slug", "example-com"],
        ["--domain-slug", "example-com", "--apply"],
        ["--apply", "--domain-slug", "example-com"],
    ],
)
def test_purge_accepts_every_valid_form(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    """Validation must not reject what the workflow actually sends."""
    monkeypatch.setattr(_hsnap, "list_snapshots", lambda *a, **k: ())
    assert cli._snapshot_purge(argv) == 0


def test_purge_apply_is_read_from_the_parse_not_from_argv() -> None:
    """`"--apply" in args` cannot tell a flag from a value spelling one.

    `--domain-slug --apply` puts the literal string "--apply" in argv as
    a VALUE. A membership test sees it and switches on the destructive
    path. The handler therefore reads the validated parse instead, and
    this asserts the underlying helper reports flags only.
    """
    assert cli._validated_flags(
        ["--domain-slug", "example-com"],
        valued=("domain-slug",),
        boolean=("apply",),
    ) == {"domain-slug"}

    assert cli._validated_flags(
        ["--domain-slug", "example-com", "--apply"],
        valued=("domain-slug",),
        boolean=("apply",),
    ) == {"domain-slug", "apply"}

"""Tests for nexus_deploy.hetzner_snapshot.

Every network call goes through the ``http_request`` DI seam, so all of
this runs offline against hard-coded fixture payloads shaped like the
real Hetzner responses. A future API schema change therefore shows up
as a focused failure rather than a runtime surprise during a teardown.

The tests are weighted towards the paths where a bug costs data rather
than time:

* :func:`select_prunable` deleting the snapshot the next spin-up needs.
* :func:`resolve_latest` accepting a snapshot from a different
  credential epoch, which restores a stack that cannot authenticate.
* :func:`create_snapshot` returning before the image is usable, which
  would let a teardown destroy the server too early.
* :func:`poweroff_server` reporting success on a running server, which
  would snapshot a live disk.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nexus_deploy.hetzner_snapshot import (
    LABEL_DOMAIN,
    LABEL_EPOCH,
    LABEL_ROLE,
    LABEL_SERVER_TYPE,
    ROLE_VALUE,
    HetznerSnapshotError,
    Snapshot,
    can_restore_onto,
    count_snapshots,
    create_snapshot,
    delete_snapshot,
    list_snapshots,
    poweroff_server,
    resolve_latest,
    select_prunable,
    validate_label_value,
)

EPOCH_A = "0123456789abcdef0123456789abcdef"
EPOCH_B = "fedcba9876543210fedcba9876543210"


def _image(
    image_id: int,
    *,
    created: str,
    epoch: str = EPOCH_A,
    disk: int = 160,
    arch: str = "x86",
    status: str = "available",
) -> dict[str, Any]:
    """One ``/v1/images`` entry, shaped like the real API."""
    return {
        "id": image_id,
        "type": "snapshot",
        "status": status,
        "description": f"nexus-example-com-2026080{image_id}T210000Z",
        "created": created,
        "disk_size": disk,
        "image_size": 12.5,
        "architecture": arch,
        "labels": {
            LABEL_DOMAIN: "example-com",
            LABEL_EPOCH: epoch,
            LABEL_SERVER_TYPE: "cx43",
        },
    }


class _Recorder:
    """Canned-response http_request that records every call.

    ``responses`` maps a substring of the URL to either a single payload
    or a list of payloads consumed in order (for polling).
    """

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(
        self,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, url, payload))
        for fragment, response in self.responses.items():
            if fragment in url:
                if isinstance(response, list):
                    # Repeat the last entry once exhausted so a poll
                    # loop that runs long does not IndexError.
                    return response.pop(0) if len(response) > 1 else response[0]
                return response
        raise AssertionError(f"unexpected request: {method} {url}")


def _no_sleep(_seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# select_prunable — retention
# ---------------------------------------------------------------------------


def _snap(
    image_id: int,
    created: str,
    epoch: str = EPOCH_A,
    status: str = "available",
) -> Snapshot:
    return Snapshot(
        image_id=image_id,
        description=f"snap-{image_id}",
        created=created,
        disk_gb=160,
        architecture="x86",
        epoch=epoch,
        server_type="cx43",
        status=status,
    )


def test_select_prunable_keeps_newest() -> None:
    """keep=2 drops everything older than the two newest."""
    snaps = (
        _snap(1, "2026-08-01T21:00:00+00:00"),
        _snap(2, "2026-08-02T21:00:00+00:00"),
        _snap(3, "2026-08-03T21:00:00+00:00"),
    )
    prunable = select_prunable(snaps, keep=2)
    assert [s.image_id for s in prunable] == [1]


def test_select_prunable_ignores_input_order() -> None:
    """Retention must not depend on the order the API returned.

    This is the one that costs data: if the caller passes an
    oldest-first list and prune trusted it, keep=2 would delete the two
    NEWEST snapshots and leave the stack restoring from an ancient one.
    """
    snaps = (
        _snap(3, "2026-08-03T21:00:00+00:00"),
        _snap(1, "2026-08-01T21:00:00+00:00"),
        _snap(2, "2026-08-02T21:00:00+00:00"),
    )
    prunable = select_prunable(snaps, keep=2)
    assert [s.image_id for s in prunable] == [1]


def test_select_prunable_nothing_to_drop() -> None:
    snaps = (_snap(1, "2026-08-01T21:00:00+00:00"),)
    assert select_prunable(snaps, keep=2) == ()


def test_select_prunable_rejects_keep_zero() -> None:
    """keep=0 would delete every snapshot including the one just made."""
    with pytest.raises(HetznerSnapshotError, match="keep must be >= 1"):
        select_prunable((_snap(1, "2026-08-01T21:00:00+00:00"),), keep=0)


# ---------------------------------------------------------------------------
# list_snapshots / count_snapshots
# ---------------------------------------------------------------------------


def test_list_snapshots_parses_and_sorts_newest_first() -> None:
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(1, created="2026-08-01T21:00:00+00:00"),
                    _image(3, created="2026-08-03T21:00:00+00:00"),
                    _image(2, created="2026-08-02T21:00:00+00:00"),
                ],
            },
        },
    )
    snaps = list_snapshots("tok", domain_slug="example-com", http_request=http)
    assert [s.image_id for s in snaps] == [3, 2, 1]
    assert snaps[0].disk_gb == 160
    assert snaps[0].architecture == "x86"
    assert snaps[0].epoch == EPOCH_A


def test_list_snapshots_scopes_by_label_selector() -> None:
    """Multi-tenant safety: one stack must not see another's images."""
    http = _Recorder({"/images": {"images": []}})
    list_snapshots("tok", domain_slug="example-com", http_request=http)
    _method, url, _payload = http.calls[0]
    assert f"{LABEL_ROLE}%3D{ROLE_VALUE}" in url
    assert f"{LABEL_DOMAIN}%3Dexample-com" in url
    assert "type=snapshot" in url


def test_list_snapshots_skips_malformed_entries() -> None:
    """One odd image must not take down a prune or a resolve."""
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(1, created="2026-08-01T21:00:00+00:00"),
                    {"no_id": True},
                    "not-a-dict",
                ],
            },
        },
    )
    snaps = list_snapshots("tok", domain_slug="example-com", http_request=http)
    assert [s.image_id for s in snaps] == [1]


def test_list_snapshots_rejects_bad_slug() -> None:
    http = _Recorder({"/images": {"images": []}})
    with pytest.raises(HetznerSnapshotError, match="domain_slug"):
        list_snapshots("tok", domain_slug="Example Com", http_request=http)


def test_list_snapshots_schema_drift_raises() -> None:
    http = _Recorder({"/images": {"unexpected": []}})
    with pytest.raises(HetznerSnapshotError, match="missing 'images' list"):
        list_snapshots("tok", http_request=http)


def test_count_snapshots_counts_project_wide() -> None:
    """The cap is per project, so the count must not be label-scoped."""
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(1, created="2026-08-01T21:00:00+00:00"),
                    _image(2, created="2026-08-02T21:00:00+00:00"),
                ],
            },
        },
    )
    assert count_snapshots("tok", http_request=http) == 2
    _method, url, _payload = http.calls[0]
    # Role-scoped (only ours count against our retention decisions) but
    # deliberately NOT domain-scoped: the cap is project-wide.
    assert f"{LABEL_ROLE}%3D{ROLE_VALUE}" in url
    assert LABEL_DOMAIN not in url


# ---------------------------------------------------------------------------
# resolve_latest — the credential-epoch guard
# ---------------------------------------------------------------------------


def test_resolve_latest_returns_newest_matching_epoch() -> None:
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(1, created="2026-08-01T21:00:00+00:00"),
                    _image(2, created="2026-08-02T21:00:00+00:00"),
                ],
            },
        },
    )
    snap = resolve_latest(
        "tok",
        domain_slug="example-com",
        expect_epoch=EPOCH_A,
        http_request=http,
    )
    assert snap is not None
    assert snap.image_id == 2


def test_resolve_latest_rejects_rotated_epoch() -> None:
    """The guard against the legacy untargeted `tofu destroy`.

    That path regenerates all 81 credentials, so an older snapshot's
    Postgres roles and admin accounts no longer match the state the
    pipeline will use. Restoring it yields a stack that boots and then
    fails to authenticate anywhere — returning None sends the workflow
    down the fresh path instead.
    """
    http = _Recorder(
        {"/images": {"images": [_image(1, created="2026-08-01T21:00:00+00:00", epoch=EPOCH_A)]}},
    )
    assert (
        resolve_latest(
            "tok",
            domain_slug="example-com",
            expect_epoch=EPOCH_B,
            http_request=http,
        )
        is None
    )


def test_resolve_latest_skips_mismatched_but_takes_older_match() -> None:
    """A newer foreign-epoch image must not hide an older valid one."""
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(9, created="2026-08-09T21:00:00+00:00", epoch=EPOCH_B),
                    _image(4, created="2026-08-04T21:00:00+00:00", epoch=EPOCH_A),
                ],
            },
        },
    )
    snap = resolve_latest(
        "tok",
        domain_slug="example-com",
        expect_epoch=EPOCH_A,
        http_request=http,
    )
    assert snap is not None
    assert snap.image_id == 4


def test_resolve_latest_none_when_no_snapshots() -> None:
    """First-ever spin-up: not an error, just the fresh path."""
    http = _Recorder({"/images": {"images": []}})
    assert resolve_latest("tok", domain_slug="example-com", http_request=http) is None


def test_resolve_latest_without_expected_epoch_accepts_any() -> None:
    http = _Recorder(
        {"/images": {"images": [_image(1, created="2026-08-01T21:00:00+00:00", epoch=EPOCH_B)]}},
    )
    snap = resolve_latest("tok", domain_slug="example-com", http_request=http)
    assert snap is not None
    assert snap.image_id == 1


# ---------------------------------------------------------------------------
# poweroff_server
# ---------------------------------------------------------------------------


def test_poweroff_returns_when_status_off() -> None:
    http = _Recorder(
        {
            "actions/shutdown": {"action": {"id": 1, "status": "running"}},
            "/servers/42": [
                {"server": {"id": 42, "status": "running"}},
                {"server": {"id": 42, "status": "off"}},
            ],
        },
    )
    poweroff_server(42, "tok", http_request=http, sleep=_no_sleep, poll_attempts=6)
    methods = [c[0] for c in http.calls]
    assert methods[0] == "POST"
    assert any("actions/shutdown" in c[1] for c in http.calls)


def test_poweroff_escalates_to_hard_poweroff() -> None:
    """A guest that ignores ACPI must not keep a paid server alive."""
    http = _Recorder(
        {
            "actions/shutdown": {"action": {"id": 1, "status": "running"}},
            "actions/poweroff": {"action": {"id": 2, "status": "running"}},
            "/servers/42": [
                {"server": {"id": 42, "status": "running"}},
                {"server": {"id": 42, "status": "running"}},
                {"server": {"id": 42, "status": "off"}},
            ],
        },
    )
    poweroff_server(42, "tok", http_request=http, sleep=_no_sleep, poll_attempts=4)
    assert any("actions/poweroff" in c[1] for c in http.calls)


def test_poweroff_raises_when_never_off() -> None:
    """Refuse to snapshot a running disk rather than risk corruption."""
    http = _Recorder(
        {
            "actions/shutdown": {"action": {"id": 1, "status": "running"}},
            "actions/poweroff": {"action": {"id": 2, "status": "running"}},
            "/servers/42": {"server": {"id": 42, "status": "running"}},
        },
    )
    with pytest.raises(HetznerSnapshotError, match="did not reach status 'off'"):
        poweroff_server(42, "tok", http_request=http, sleep=_no_sleep, poll_attempts=4)


# ---------------------------------------------------------------------------
# create_snapshot
# ---------------------------------------------------------------------------


def test_create_snapshot_waits_for_action_and_image() -> None:
    """Both waits matter: action success != image usable.

    Returning after only the action would let the teardown destroy the
    server while the image is still 'creating'.
    """
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "running"},
                "image": {"id": 99},
            },
            "/actions/7": [
                {"action": {"id": 7, "status": "running"}},
                {"action": {"id": 7, "status": "success"}},
            ],
            "/images/99": [
                {"image": dict(_image(99, created="2026-08-05T21:00:00+00:00"), status="creating")},
                {"image": _image(99, created="2026-08-05T21:00:00+00:00")},
            ],
        },
    )
    snap = create_snapshot(
        42,
        "tok",
        domain_slug="example-com",
        epoch=EPOCH_A,
        server_type="cx43",
        timestamp="20260805T210000Z",
        http_request=http,
        sleep=_no_sleep,
    )
    assert snap.image_id == 99
    assert snap.disk_gb == 160


def test_create_snapshot_sends_labels_and_description() -> None:
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {"image": _image(99, created="2026-08-05T21:00:00+00:00")},
        },
    )
    create_snapshot(
        42,
        "tok",
        domain_slug="example-com",
        epoch=EPOCH_A,
        server_type="cx43",
        timestamp="20260805T210000Z",
        http_request=http,
        sleep=_no_sleep,
    )
    _method, _url, payload = http.calls[0]
    assert payload is not None
    assert payload["type"] == "snapshot"
    assert payload["description"] == "nexus-example-com-20260805T210000Z"
    assert payload["labels"][LABEL_DOMAIN] == "example-com"
    assert payload["labels"][LABEL_EPOCH] == EPOCH_A
    assert payload["labels"][LABEL_SERVER_TYPE] == "cx43"


def test_create_snapshot_surfaces_action_error() -> None:
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "running"},
                "image": {"id": 99},
            },
            "/actions/7": {
                "action": {
                    "id": 7,
                    "status": "error",
                    "error": {"code": "limit", "message": "snapshot limit reached"},
                },
            },
        },
    )
    with pytest.raises(HetznerSnapshotError, match="snapshot limit reached"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=http,
            sleep=_no_sleep,
        )


def test_create_snapshot_rejects_bad_epoch() -> None:
    """A malformed epoch would compare unequal forever."""
    with pytest.raises(HetznerSnapshotError, match="32 lowercase hex"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch="not-a-fingerprint",
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=_Recorder({}),
            sleep=_no_sleep,
        )


def test_create_snapshot_raises_on_schema_drift() -> None:
    """A response without action.id/image.id must fail loudly.

    Silently continuing would leave the teardown believing a snapshot
    exists when none does.
    """
    http = _Recorder({"actions/create_image": {"action": {}, "image": {}}})
    with pytest.raises(HetznerSnapshotError, match=r"missing action\.id or image\.id"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=http,
            sleep=_no_sleep,
        )


def test_create_snapshot_without_epoch_omits_the_label() -> None:
    """An empty epoch is allowed and must not produce an empty label.

    An empty label value would still match a `nexus_epoch` selector,
    which is a surprising way to make an unguarded snapshot look
    guarded.
    """
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {"image": _image(99, created="2026-08-05T21:00:00+00:00")},
        },
    )
    create_snapshot(
        42,
        "tok",
        domain_slug="example-com",
        epoch="",
        server_type="cx43",
        timestamp="20260805T210000Z",
        http_request=http,
        sleep=_no_sleep,
    )
    _method, _url, payload = http.calls[0]
    assert payload is not None
    assert LABEL_EPOCH not in payload["labels"]
    assert payload["labels"][LABEL_DOMAIN] == "example-com"


def test_create_snapshot_raises_when_action_never_finishes() -> None:
    """A stuck action must not be mistaken for a finished snapshot."""
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "running"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "running"}},
        },
    )
    with pytest.raises(HetznerSnapshotError, match="still running after"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=http,
            sleep=_no_sleep,
            poll_attempts=2,
        )


def test_create_snapshot_raises_when_image_never_available() -> None:
    """The action can succeed while the image is still 'creating'.

    Returning here would hand the teardown an unusable image ID and let
    it destroy the server anyway.
    """
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {
                "image": dict(_image(99, created="2026-08-05T21:00:00+00:00"), status="creating"),
            },
        },
    )
    with pytest.raises(HetznerSnapshotError, match="did not become 'available'"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=http,
            sleep=_no_sleep,
            poll_attempts=2,
        )


def test_create_snapshot_raises_on_available_but_unparseable_image() -> None:
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {"image": {"status": "available"}},
        },
    )
    with pytest.raises(HetznerSnapshotError, match="unparseable"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=http,
            sleep=_no_sleep,
            poll_attempts=2,
        )


def test_create_snapshot_default_sleep_is_not_called_on_fast_path() -> None:
    """Exercises the production `sleep=None` branch.

    Safe because every poll succeeds on its first attempt, so the real
    ``time.sleep`` is never reached — the test stays instant while
    still covering the default-argument wiring.
    """
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {"image": _image(99, created="2026-08-05T21:00:00+00:00")},
        },
    )
    snap = create_snapshot(
        42,
        "tok",
        domain_slug="example-com",
        epoch=EPOCH_A,
        server_type="cx43",
        timestamp="20260805T210000Z",
        http_request=http,
    )
    assert snap.image_id == 99


def test_poweroff_default_sleep_is_not_called_when_already_off() -> None:
    http = _Recorder(
        {
            "actions/shutdown": {"action": {"id": 1, "status": "success"}},
            "/servers/42": {"server": {"id": 42, "status": "off"}},
        },
    )
    poweroff_server(42, "tok", http_request=http)


def test_snapshot_str_is_operator_readable() -> None:
    snap = _snap(7, "2026-08-07T21:00:00+00:00")
    assert str(snap) == "#7 snap-7 (160GB x86)"


def test_create_snapshot_rejects_bad_slug() -> None:
    with pytest.raises(HetznerSnapshotError, match="domain_slug"):
        create_snapshot(
            42,
            "tok",
            domain_slug="Example Com",
            epoch=EPOCH_A,
            server_type="cx43",
            timestamp="20260805T210000Z",
            http_request=_Recorder({}),
            sleep=_no_sleep,
        )


# ---------------------------------------------------------------------------
# delete_snapshot
# ---------------------------------------------------------------------------


def test_delete_snapshot_issues_delete() -> None:
    http = _Recorder({"/images/99": None})
    delete_snapshot(99, "tok", http_request=http)
    assert http.calls == [("DELETE", "https://api.hetzner.cloud/v1/images/99", None)]


# ---------------------------------------------------------------------------
# label validation and restore constraints
# ---------------------------------------------------------------------------


def test_validate_label_value_accepts_truncated_fingerprint() -> None:
    assert validate_label_value(EPOCH_A, field="epoch") == EPOCH_A


def test_validate_label_value_rejects_full_sha256() -> None:
    """64 hex chars exceed Hetzner's 63-char label limit.

    This is exactly why tofu's credential_fingerprint output is
    truncated to 32; the test pins the reason so nobody "fixes" the
    truncation later.
    """
    with pytest.raises(HetznerSnapshotError, match="valid Hetzner label value"):
        validate_label_value("a" * 64, field="epoch")


@pytest.mark.parametrize("bad", ["-leading", "trailing-", "has space", "has/slash", ""])
def test_validate_label_value_rejects_malformed(bad: str) -> None:
    with pytest.raises(HetznerSnapshotError):
        validate_label_value(bad, field="epoch")


def test_can_restore_onto_requires_equal_or_larger_disk() -> None:
    """Hetzner rejects a target disk smaller than the image's."""
    snap = _snap(1, "2026-08-01T21:00:00+00:00")
    assert can_restore_onto(snap, disk_gb=160, architecture="x86") is True
    assert can_restore_onto(snap, disk_gb=240, architecture="x86") is True
    assert can_restore_onto(snap, disk_gb=80, architecture="x86") is False


def test_can_restore_onto_requires_matching_architecture() -> None:
    snap = _snap(1, "2026-08-01T21:00:00+00:00")
    assert can_restore_onto(snap, disk_gb=160, architecture="arm") is False


def test_can_restore_onto_tolerates_unknown_architecture() -> None:
    """An image without an architecture field must not be excluded.

    Only the disk constraint is enforceable in that case; failing shut
    would make a legitimate snapshot permanently unusable.
    """
    snap = Snapshot(
        image_id=1,
        description="d",
        created="2026-08-01T21:00:00+00:00",
        disk_gb=160,
        architecture="",
        epoch=EPOCH_A,
        server_type="cx43",
    )
    assert can_restore_onto(snap, disk_gb=160, architecture="x86") is True


# ---------------------------------------------------------------------------
# _default_http_request — the real urllib path
#
# Mirrors the _default_http_get tests in test_hetzner_capacity.py: the
# production HTTP seam is exercised by monkeypatching urlopen, not left
# uncovered. This module adds POST/DELETE and an error-body read on top
# of that, so those get their own cases.
# ---------------------------------------------------------------------------


class _FakeUrlopenContext:
    """Stand-in for ``urllib.request.urlopen()`` — the ``with ... as
    resp`` pattern needs both ``__enter__`` and ``__exit__``."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeUrlopenContext:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_default_http_request_get(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.hetzner_snapshot import _default_http_request

    captured: dict[str, Any] = {}

    def _fake_urlopen(req: Any, timeout: float = 0) -> _FakeUrlopenContext:
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.headers.get("Authorization")
        captured["timeout"] = timeout
        captured["data"] = req.data
        return _FakeUrlopenContext(b'{"ok": true}')

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    result = _default_http_request("GET", "https://api.hetzner.cloud/v1/images/1", "tok")
    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["auth"] == "Bearer tok"
    assert captured["timeout"] == 30.0
    assert captured["data"] is None


def test_default_http_request_post_sends_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.hetzner_snapshot import _default_http_request

    captured: dict[str, Any] = {}

    def _fake_urlopen(req: Any, timeout: float = 0) -> _FakeUrlopenContext:
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        captured["content_type"] = req.headers.get("Content-type")
        return _FakeUrlopenContext(b'{"action": {"id": 1}}')

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    _default_http_request(
        "POST",
        "https://api.hetzner.cloud/v1/servers/1/actions/create_image",
        "tok",
        {"type": "snapshot"},
    )
    assert captured["method"] == "POST"
    assert captured["body"] == {"type": "snapshot"}
    assert captured["content_type"] == "application/json"


def test_default_http_request_empty_body_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE returns 204 No Content — must not raise a JSON error."""
    from nexus_deploy.hetzner_snapshot import _default_http_request

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout=0: _FakeUrlopenContext(b""),
    )
    assert _default_http_request("DELETE", "https://api.hetzner.cloud/v1/images/1", "tok") is None


def test_default_http_request_wraps_http_error_with_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hetzner puts a machine-readable reason in the error body.

    Surfacing it is what turns a bare "HTTP 403" into something an
    operator can act on — a missing token scope reads very differently
    from resource_limit_exceeded.
    """
    import io
    import urllib.error

    from nexus_deploy.hetzner_snapshot import _default_http_request

    def _fake_urlopen(_req: Any, timeout: float = 0) -> _FakeUrlopenContext:
        raise urllib.error.HTTPError(
            url="https://api.hetzner.cloud/v1/images",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":{"code":"resource_limit_exceeded"}}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerSnapshotError, match=r"HTTP 403.*resource_limit_exceeded"):
        _default_http_request("GET", "https://api.hetzner.cloud/v1/images", "tok")


def test_default_http_request_survives_unreadable_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading the body is best-effort and must never mask the HTTP error."""
    import urllib.error

    from nexus_deploy.hetzner_snapshot import _default_http_request

    class _Exploding:
        def read(self) -> bytes:
            raise OSError("socket gone")

    def _fake_urlopen(_req: Any, timeout: float = 0) -> _FakeUrlopenContext:
        err = urllib.error.HTTPError(
            url="https://api.hetzner.cloud/v1/images",
            code=500,
            msg="Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        err.read = _Exploding().read  # type: ignore[assignment]
        raise err

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerSnapshotError, match=r"HTTP 500"):
        _default_http_request("GET", "https://api.hetzner.cloud/v1/images", "tok")


def test_default_http_request_wraps_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from nexus_deploy.hetzner_snapshot import _default_http_request

    def _fake_urlopen(_req: Any, timeout: float = 0) -> _FakeUrlopenContext:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerSnapshotError, match=r"request failed.*URLError"):
        _default_http_request("GET", "https://api.hetzner.cloud/v1/images", "tok")


def test_default_http_request_wraps_non_utf8_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.hetzner_snapshot import _default_http_request

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout=0: _FakeUrlopenContext(b"\xff\xfe\x00binary"),
    )
    with pytest.raises(HetznerSnapshotError, match=r"non-UTF-8"):
        _default_http_request("GET", "https://api.hetzner.cloud/v1/images", "tok")


def test_default_http_request_wraps_non_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.hetzner_snapshot import _default_http_request

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout=0: _FakeUrlopenContext(b"<html>502 Bad Gateway</html>"),
    )
    with pytest.raises(HetznerSnapshotError, match=r"non-JSON"):
        _default_http_request("GET", "https://api.hetzner.cloud/v1/images", "tok")


# ---------------------------------------------------------------------------
# Non-available images (PR #649 review)
#
# /v1/images lists snapshots that are still `creating` — e.g. from a
# teardown interrupted between create_image and completion. Such an
# image sorts newest, so anything that trusts the ordering blindly will
# pick it.
# ---------------------------------------------------------------------------


def test_resolve_latest_skips_creating_image() -> None:
    """A half-finished image must not shadow a good older one.

    Without the status check, an interrupted teardown would fail the
    NEXT spin-up: the `creating` image resolves as newest, tofu tries to
    build from an unusable image, and the perfectly good snapshot right
    behind it is never considered.
    """
    http = _Recorder(
        {
            "/images": {
                "images": [
                    _image(9, created="2026-08-09T21:00:00+00:00", status="creating"),
                    _image(4, created="2026-08-04T21:00:00+00:00"),
                ],
            },
        },
    )
    snap = resolve_latest("tok", domain_slug="example-com", http_request=http)
    assert snap is not None
    assert snap.image_id == 4


def test_resolve_latest_none_when_only_creating() -> None:
    http = _Recorder(
        {
            "/images": {
                "images": [_image(9, created="2026-08-09T21:00:00+00:00", status="creating")]
            }
        },
    )
    assert resolve_latest("tok", domain_slug="example-com", http_request=http) is None


def test_select_prunable_does_not_count_creating_towards_keep() -> None:
    """A `creating` image must not occupy a keep slot.

    If it did, keep=2 would retain one good snapshot plus one unusable
    one — halving the actual retention without saying so.
    """
    snaps = (
        _snap(9, "2026-08-09T21:00:00+00:00", status="creating"),
        _snap(3, "2026-08-03T21:00:00+00:00"),
        _snap(2, "2026-08-02T21:00:00+00:00"),
        _snap(1, "2026-08-01T21:00:00+00:00"),
    )
    prunable = select_prunable(snaps, keep=2)
    # 3 and 2 are kept; only 1 is dropped. 9 is neither kept nor pruned.
    assert [s.image_id for s in prunable] == [1]


def test_select_prunable_never_returns_creating() -> None:
    """Deleting an in-flight image is not a retention pass's job."""
    snaps = (
        _snap(3, "2026-08-03T21:00:00+00:00"),
        _snap(2, "2026-08-02T21:00:00+00:00"),
        _snap(9, "2026-07-01T21:00:00+00:00", status="creating"),
    )
    prunable = select_prunable(snaps, keep=2)
    assert prunable == ()


def test_parse_carries_status() -> None:
    http = _Recorder(
        {
            "/images": {
                "images": [_image(1, created="2026-08-01T21:00:00+00:00", status="creating")]
            }
        },
    )
    snaps = list_snapshots("tok", domain_slug="example-com", http_request=http)
    assert snaps[0].status == "creating"
    assert snaps[0].is_available is False


# ---------------------------------------------------------------------------
# Label-selector scoping and server_type validation (PR #649 review)
# ---------------------------------------------------------------------------


def test_list_snapshots_always_scopes_by_role() -> None:
    """Without the role, prune could enumerate — and delete — a foreign
    snapshot that merely carried a matching nexus_domain label."""
    http = _Recorder({"/images": {"images": []}})
    list_snapshots("tok", http_request=http)
    _method, url, _payload = http.calls[0]
    assert f"{LABEL_ROLE}%3D{ROLE_VALUE}" in url


def test_create_snapshot_rejects_malformed_server_type() -> None:
    """server_type is grepped out of config.tfvars, so it is the one
    label value that has not already been through a regex."""
    with pytest.raises(HetznerSnapshotError, match="valid Hetzner label value"):
        create_snapshot(
            42,
            "tok",
            domain_slug="example-com",
            epoch=EPOCH_A,
            server_type="cx43 with spaces",
            timestamp="20260805T210000Z",
            http_request=_Recorder({}),
            sleep=_no_sleep,
        )


def test_create_snapshot_allows_empty_server_type() -> None:
    """Empty is fine — the label is simply dropped."""
    http = _Recorder(
        {
            "actions/create_image": {
                "action": {"id": 7, "status": "success"},
                "image": {"id": 99},
            },
            "/actions/7": {"action": {"id": 7, "status": "success"}},
            "/images/99": {"image": _image(99, created="2026-08-05T21:00:00+00:00")},
        },
    )
    create_snapshot(
        42,
        "tok",
        domain_slug="example-com",
        epoch=EPOCH_A,
        server_type="",
        timestamp="20260805T210000Z",
        http_request=http,
        sleep=_no_sleep,
    )
    _method, _url, payload = http.calls[0]
    assert payload is not None
    assert LABEL_SERVER_TYPE not in payload["labels"]

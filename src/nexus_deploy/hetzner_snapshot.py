"""Hetzner Cloud disk-snapshot lifecycle for the snapshot-based
teardown/spin-up cycle.

The default lifecycle destroys the whole stack on teardown and rebuilds
it from ``ubuntu-26.04`` on the next spin-up. Most of that rebuild is
repetition: patching Ubuntu, installing Docker, and pulling the same
container images again — the single largest block of a spin-up.

This module implements the alternative: take a Hetzner disk snapshot of
the server before destroying it, then create the next server directly
from that image. Two properties make it work:

* Hetzner snapshots **survive deletion of the server they came from**
  (unlike Hetzner *backups*, which are deleted with the server).
* Every ``stacks/*/docker-compose.yml`` uses ``restart:
  unless-stopped``, so containers come back on their own at boot.

A snapshot also captures the data of *every* stack, where the R2
persistence layer (:mod:`nexus_deploy.s3_persistence`) only covers a
hard-coded five-stack subset. The two are complements: R2 is the
portable, logically-consistent escape hatch used whenever a snapshot is
unavailable, mismatched, or unusable.

Public surface:

* :class:`Snapshot` — one snapshot image with the metadata needed to
  decide whether it can be restored.
* :class:`HetznerSnapshotError` — API/auth/network/schema failure.
* :func:`poweroff_server` — graceful ACPI shutdown, polled to ``off``.
* :func:`create_snapshot` — create an image and wait until usable.
* :func:`list_snapshots` — all snapshots for one stack, newest first.
* :func:`resolve_latest` — the newest usable snapshot, epoch-checked.
* :func:`select_prunable` — which snapshots a ``keep=N`` policy drops.
* :func:`delete_snapshot` — remove one image.
* :func:`count_snapshots` — total visible to this token, for the cap.

Every network call goes through an injectable ``http_request`` seam so
the whole module is unit-testable without touching the network, mirroring
:mod:`nexus_deploy.hetzner_capacity`.
"""

from __future__ import annotations

import contextlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_API_BASE = "https://api.hetzner.cloud/v1"
_DEFAULT_TIMEOUT = 30.0

# Hetzner's DEFAULT snapshot cap. Two properties matter and both are
# easy to get wrong:
#
# * It is counted PER CUSTOMER across every project, not per project.
#   Hetzner's Limits page says so directly: "Limits sind pro Kunde
#   festgelegt und werden über alle Projekte gezählt." Splitting a
#   fleet across projects therefore does not buy any headroom.
# * It is a default, not a ceiling. Support raises it on request via
#   the Cloud Console (Limits -> Request change -> Limit increase), so
#   the real cap is account-specific and cannot be a constant here.
#
# Callers read the effective value from NEXUS_SNAPSHOT_LIMIT and fall
# back to this. Either way it is only a warning threshold — the API is
# authoritative and rejects the create call when the real limit is hit.
DEFAULT_SNAPSHOT_LIMIT = 30

# Label keys used to make a snapshot self-describing. The Hetzner
# labels are the source of truth for "which snapshot belongs to this
# stack" — unlike a D1 row they cannot go stale relative to reality,
# and they survive a D1 loss.
LABEL_ROLE = "nexus_role"
LABEL_DOMAIN = "nexus_domain"
LABEL_EPOCH = "nexus_epoch"
LABEL_SERVER_TYPE = "nexus_server_type"

ROLE_VALUE = "stack-snapshot"

# Hetzner label values: at most 63 characters, first and last character
# alphanumeric, ``-``, ``_`` and ``.`` allowed in between. This is the
# reason `credential_fingerprint` in tofu/stack/outputs.tf is truncated
# to 32 characters — a full sha256 hex digest is 64 and would be
# rejected here.
_LABEL_VALUE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")

# The credential epoch is the truncated sha256 from tofu's
# `credential_fingerprint` output.
_EPOCH = re.compile(r"^[0-9a-f]{32}$")

# Same identifier gate as hetzner_capacity: values reach a label
# selector and a tfvars rewrite, so anything outside this character set
# is refused at the boundary rather than escaped downstream.
_IDENT = re.compile(r"^[a-z0-9-]+$")

# (method, url, token, payload) -> parsed JSON (or None for 204)
HttpRequest = Callable[[str, str, str, "dict[str, Any] | None"], Any]

# () -> None; injected so tests do not actually wait.
Sleep = Callable[[float], None]


class HetznerSnapshotError(Exception):
    """Hetzner API call failed (auth / network / schema drift / timeout)."""


@dataclass(frozen=True)
class Snapshot:
    """A Hetzner snapshot image plus what we need to judge it.

    Two sizes, and conflating them is a costly mistake in both
    directions:

    ``disk_gb`` is the image's ``disk_size`` — the **minimum** disk a
    target server type must have to restore this image. It equals the
    source server's disk, not its used space, so it is what decides
    which server types remain reachable. Verified in practice: the
    first real snapshot of this stack came off a cpx42 and reported
    320 GB.

    ``image_gb`` is ``image_size`` — the compressed used space, and the
    figure Hetzner actually bills (~EUR 0.011-0.014/GB/month). Usually
    a small fraction of ``disk_gb``. Reported so the cost of a
    retention policy is visible rather than guessed at.

    ``epoch`` is the credential fingerprint that was current when the
    snapshot was taken. A snapshot whose epoch no longer matches the
    live tofu state was taken before the credentials rotated, so
    restoring it would produce a stack that boots and then fails to
    authenticate anywhere. Empty string when the label is absent
    (a snapshot from before this mechanism existed).

    ``status`` matters because ``/v1/images`` also lists images that
    are still ``creating`` — e.g. from a teardown that was interrupted
    between ``create_image`` and completion. Such an image is the
    newest one in the listing but cannot be restored from, so
    selecting it would fail a spin-up that had a perfectly good older
    snapshot available.
    """

    image_id: int
    description: str
    created: str
    disk_gb: int
    architecture: str
    epoch: str
    server_type: str
    status: str = ""
    image_gb: float = 0.0

    @property
    def is_available(self) -> bool:
        """Whether this image can actually be used to create a server."""
        return self.status == "available"

    def __str__(self) -> str:
        # Both sizes on purpose: disk_gb is the restore constraint,
        # image_gb is what shows up on the invoice.
        return (
            f"#{self.image_id} {self.description} "
            f"(disk {self.disk_gb}GB, billed {self.image_gb:.1f}GB, {self.architecture})"
        )


def _default_http_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Production HTTP call against the Hetzner API. Returns parsed JSON.

    Raises :class:`HetznerSnapshotError` for every failure mode (HTTP
    4xx/5xx, network, timeout, non-UTF-8 body, malformed JSON) so
    callers have a single error class to handle. The original exception
    is chained via ``__cause__`` so a debugger pass keeps the detail.

    A ``204 No Content`` (what DELETE returns) yields ``None`` rather
    than a JSON parse error.
    """
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(  # noqa: S310 — URL built from literal _API_BASE
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # Hetzner puts a machine-readable reason in the body; surfacing
        # it turns "HTTP 403" into something an operator can act on
        # (missing token scope vs. resource_limit_exceeded).
        # Best-effort: reading the body must never mask the HTTP error
        # we are already reporting.
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise HetznerSnapshotError(
            f"Hetzner API HTTP {exc.code} for {method} {url}: {exc.reason}"
            + (f" — {detail}" if detail else ""),
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HetznerSnapshotError(
            f"Hetzner API request failed for {method} {url}: {type(exc).__name__}: {exc}",
        ) from exc

    if not raw:
        return None
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HetznerSnapshotError(
            f"Hetzner API returned non-UTF-8 body for {method} {url}: {exc}",
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HetznerSnapshotError(
            f"Hetzner API returned non-JSON for {method} {url}: {exc}",
        ) from exc


def _request(http_request: HttpRequest | None) -> HttpRequest:
    return http_request if http_request is not None else _default_http_request


def validate_label_value(value: str, *, field: str) -> str:
    """Gate a value that is about to become a Hetzner label.

    Raises rather than truncating: a silently shortened epoch would
    compare unequal forever and send every restore down the fresh path
    for no visible reason.
    """
    if not _LABEL_VALUE.match(value):
        raise HetznerSnapshotError(
            f"{field} {value!r} is not a valid Hetzner label value "
            "(max 63 chars, must start and end alphanumeric, "
            "only '-', '_' and '.' in between)",
        )
    return value


def _parse_snapshot(image: dict[str, Any]) -> Snapshot | None:
    """Build a :class:`Snapshot` from one ``/v1/images`` entry.

    Returns ``None`` for anything malformed rather than raising: a
    single odd image in a list response should not take down a prune or
    a resolve.
    """
    image_id = image.get("id")
    if not isinstance(image_id, int):
        return None
    labels = image.get("labels")
    labels = labels if isinstance(labels, dict) else {}

    disk = image.get("disk_size")
    # Hetzner reports disk_size in GB as a number; it has been seen as
    # both int and float across API versions.
    disk_gb = int(disk) if isinstance(disk, (int, float)) else 0

    # image_size is the billed figure and is genuinely fractional
    # (e.g. 12.5), so it must not be truncated to int the way disk_size
    # is. It is also absent while an image is still `creating`.
    billed = image.get("image_size")
    image_gb = float(billed) if isinstance(billed, (int, float)) else 0.0

    arch = image.get("architecture")
    description = image.get("description")
    created = image.get("created")

    return Snapshot(
        image_id=image_id,
        description=description if isinstance(description, str) else "",
        created=created if isinstance(created, str) else "",
        disk_gb=disk_gb,
        architecture=arch if isinstance(arch, str) else "",
        epoch=str(labels.get(LABEL_EPOCH, "")),
        server_type=str(labels.get(LABEL_SERVER_TYPE, "")),
        status=str(image.get("status", "")),
        image_gb=image_gb,
    )


def poweroff_server(
    server_id: int,
    token: str,
    *,
    http_request: HttpRequest | None = None,
    sleep: Sleep | None = None,
    poll_attempts: int = 48,
    poll_interval_s: float = 5.0,
) -> None:
    """Shut the server down gracefully and wait until it reports ``off``.

    Hetzner recommends powering off before snapshotting so the disk is
    consistent. ``shutdown`` sends ACPI, which gives systemd a chance to
    stop the Docker containers cleanly — that graceful stop is what
    makes the captured Postgres data directories trustworthy.

    Falls back to a hard ``poweroff`` if ACPI has not taken effect
    within the poll budget (default 4 minutes). A hung guest must not
    leave a paid server running forever; a hard power-off is still
    safer than snapshotting a running disk, and the R2 logical snapshot
    has already been taken at that point in the teardown.

    Raises :class:`HetznerSnapshotError` if the server never reaches
    ``off`` even after the hard power-off.
    """
    req = _request(http_request)
    if sleep is None:
        import time as _time

        sleep = _time.sleep

    req("POST", f"{_API_BASE}/servers/{server_id}/actions/shutdown", token, None)

    hard_tried = False
    for attempt in range(1, poll_attempts + 1):
        payload = req("GET", f"{_API_BASE}/servers/{server_id}", token, None)
        server = payload.get("server") if isinstance(payload, dict) else None
        status = server.get("status") if isinstance(server, dict) else None
        if status == "off":
            return
        # Halfway through the budget, stop hoping ACPI will land.
        if not hard_tried and attempt >= poll_attempts // 2:
            req("POST", f"{_API_BASE}/servers/{server_id}/actions/poweroff", token, None)
            hard_tried = True
        sleep(poll_interval_s)

    raise HetznerSnapshotError(
        f"server {server_id} did not reach status 'off' after "
        f"{poll_attempts * poll_interval_s:.0f}s (ACPI shutdown and hard "
        "poweroff both attempted) — refusing to snapshot a running disk",
    )


def create_snapshot(
    server_id: int,
    token: str,
    *,
    domain_slug: str,
    epoch: str,
    server_type: str,
    timestamp: str,
    http_request: HttpRequest | None = None,
    sleep: Sleep | None = None,
    poll_attempts: int = 120,
    poll_interval_s: float = 10.0,
) -> Snapshot:
    """Create a snapshot of ``server_id`` and wait until it is usable.

    ``timestamp`` is passed in rather than generated here so the caller
    controls it and the function stays deterministic under test.

    Waits for two separate things, which is not redundant: the *action*
    reaching ``success`` means Hetzner accepted and finished the copy,
    while the *image* reaching ``available`` means it can actually be
    used to create a server. Returning after only the first would let a
    teardown destroy the server while the image is still ``creating``.
    """
    req = _request(http_request)
    if sleep is None:
        import time as _time

        sleep = _time.sleep

    if not _IDENT.match(domain_slug):
        raise HetznerSnapshotError(
            f"domain_slug {domain_slug!r} must be lowercase alphanumeric with dashes",
        )
    if epoch and not _EPOCH.match(epoch):
        raise HetznerSnapshotError(
            f"epoch {epoch!r} must be 32 lowercase hex characters "
            "(tofu output credential_fingerprint)",
        )

    description = f"nexus-{domain_slug}-{timestamp}"
    validate_label_value(description, field="description")
    validate_label_value(domain_slug, field=LABEL_DOMAIN)
    if epoch:
        validate_label_value(epoch, field=LABEL_EPOCH)
    # server_type is grepped out of config.tfvars by the workflow, so it
    # is the one label value that has not already been through a regex.
    # A stray space there would make Hetzner reject the whole create
    # call and leave the teardown without a snapshot.
    if server_type:
        validate_label_value(server_type, field=LABEL_SERVER_TYPE)

    labels = {
        LABEL_ROLE: ROLE_VALUE,
        LABEL_DOMAIN: domain_slug,
        LABEL_EPOCH: epoch,
        LABEL_SERVER_TYPE: server_type,
    }
    # Drop empties — Hetzner accepts an empty label value but it makes
    # the selector below behave surprisingly.
    labels = {k: v for k, v in labels.items() if v}

    payload = req(
        "POST",
        f"{_API_BASE}/servers/{server_id}/actions/create_image",
        token,
        {"type": "snapshot", "description": description, "labels": labels},
    )
    action = payload.get("action") if isinstance(payload, dict) else None
    image = payload.get("image") if isinstance(payload, dict) else None
    action_id = action.get("id") if isinstance(action, dict) else None
    image_id = image.get("id") if isinstance(image, dict) else None
    if not isinstance(action_id, int) or not isinstance(image_id, int):
        raise HetznerSnapshotError(
            "Hetzner create_image response missing action.id or image.id",
        )

    _wait_for_action(action_id, token, req, sleep, poll_attempts, poll_interval_s)
    return _wait_for_image(image_id, token, req, sleep, poll_attempts, poll_interval_s)


def _wait_for_action(
    action_id: int,
    token: str,
    req: HttpRequest,
    sleep: Sleep,
    poll_attempts: int,
    poll_interval_s: float,
) -> None:
    for _ in range(poll_attempts):
        payload = req("GET", f"{_API_BASE}/actions/{action_id}", token, None)
        action = payload.get("action") if isinstance(payload, dict) else None
        status = action.get("status") if isinstance(action, dict) else None
        if status == "success":
            return
        if status == "error":
            error = action.get("error") if isinstance(action, dict) else None
            message = error.get("message") if isinstance(error, dict) else "unknown"
            raise HetznerSnapshotError(f"snapshot action {action_id} failed: {message}")
        sleep(poll_interval_s)
    raise HetznerSnapshotError(
        f"snapshot action {action_id} still running after {poll_attempts * poll_interval_s:.0f}s",
    )


def _wait_for_image(
    image_id: int,
    token: str,
    req: HttpRequest,
    sleep: Sleep,
    poll_attempts: int,
    poll_interval_s: float,
) -> Snapshot:
    for _ in range(poll_attempts):
        payload = req("GET", f"{_API_BASE}/images/{image_id}", token, None)
        image = payload.get("image") if isinstance(payload, dict) else None
        if isinstance(image, dict) and image.get("status") == "available":
            snapshot = _parse_snapshot(image)
            if snapshot is None:
                raise HetznerSnapshotError(
                    f"image {image_id} is available but its payload is unparseable",
                )
            return snapshot
        sleep(poll_interval_s)
    raise HetznerSnapshotError(
        f"image {image_id} did not become 'available' after {poll_attempts * poll_interval_s:.0f}s",
    )


def list_snapshots(
    token: str,
    *,
    domain_slug: str | None = None,
    http_request: HttpRequest | None = None,
) -> tuple[Snapshot, ...]:
    """Return this project's snapshots, newest first.

    Both label keys are always required in the selector, never just the
    domain. ``nexus_role`` is what makes an image ours; without it, any
    snapshot in the project that happened to carry a matching
    ``nexus_domain`` would be enumerated for retention — and prune
    deletes what it enumerates. Together they are also what makes the
    mechanism multi-tenant-safe: two stacks in one Hetzner project
    never see each other's images.

    Non-``available`` images are returned too. They are excluded where
    it matters (:func:`resolve_latest`, :func:`select_prunable`) rather
    than here, because :func:`count_snapshots` needs the true total —
    an image still being created counts against the project cap.
    """
    req = _request(http_request)
    url = f"{_API_BASE}/images?type=snapshot&per_page=100&sort=created:desc"
    selector = f"{LABEL_ROLE}%3D{ROLE_VALUE}"
    if domain_slug is not None:
        if not _IDENT.match(domain_slug):
            raise HetznerSnapshotError(
                f"domain_slug {domain_slug!r} must be lowercase alphanumeric with dashes",
            )
        selector += f",{LABEL_DOMAIN}%3D{domain_slug}"
    url += f"&label_selector={selector}"

    payload = req("GET", url, token, None)
    images = payload.get("images") if isinstance(payload, dict) else None
    if not isinstance(images, list):
        raise HetznerSnapshotError("Hetzner /v1/images response missing 'images' list")

    out = [s for s in (_parse_snapshot(i) for i in images if isinstance(i, dict)) if s]
    # The API is asked to sort, but do not depend on it: a wrong order
    # here would make prune() delete the newest snapshot.
    out.sort(key=lambda s: (s.created, s.image_id), reverse=True)
    return tuple(out)


def count_snapshots(token: str, *, http_request: HttpRequest | None = None) -> int:
    """Every snapshot in this project, for the pre-flight cap check.

    Deliberately does NOT go through :func:`list_snapshots`. That one
    filters on ``nexus_role``, which is exactly right for retention —
    prune deletes what it enumerates, so it must never see an image it
    does not own — and exactly wrong here. Hetzner's quota counts every
    snapshot in the project: one taken by hand in the Console, one left
    behind by another tool, one predating these labels. A count that
    skips those reports a comfortable number right up until the API
    rejects the create.

    Reads ``meta.pagination.total_entries`` rather than measuring the
    returned page. ``list_snapshots`` asks for ``per_page=100`` and does
    not paginate, so counting its result would silently cap at 100 —
    which stopped being hypothetical the moment a limit above 100 could
    be configured. ``per_page=1`` keeps the payload minimal; the images
    themselves are not wanted here, only how many there are.

    KNOWN BLIND SPOT: an ``HCLOUD_TOKEN`` is scoped to one project,
    while the limit is counted per customer across every project. With
    a single project the two are equivalent. With several, this
    under-counts, and it under-counts hardest in exactly the setup that
    needs the warning most — one project per tenant spreads the images
    out until no single project looks close to the cap. Hetzner exposes
    no account-wide count to a project token, so the caller says what
    this number actually covers rather than implying more.
    """
    req = _request(http_request)
    # No label_selector: see above. per_page=1 because only the total
    # is wanted.
    payload = req("GET", f"{_API_BASE}/images?type=snapshot&per_page=1", token, None)
    meta = payload.get("meta") if isinstance(payload, dict) else None
    pagination = meta.get("pagination") if isinstance(meta, dict) else None
    total = pagination.get("total_entries") if isinstance(pagination, dict) else None
    # `type(total) is int` rather than isinstance: bool subclasses int in
    # Python, so isinstance(True, int) passes and a `"total_entries": true`
    # would silently become a count of 1. A negative total is equally
    # meaningless. Both would suppress the warning while looking valid,
    # which is the failure mode this whole function exists to avoid.
    if type(total) is not int or total < 0:
        raise HetznerSnapshotError(
            "Hetzner /v1/images response has no usable meta.pagination.total_entries",
        )
    return total


def resolve_latest(
    token: str,
    *,
    domain_slug: str,
    expect_epoch: str | None = None,
    http_request: HttpRequest | None = None,
) -> Snapshot | None:
    """Newest usable snapshot for one stack, or ``None``.

    ``None`` is the ordinary "take the fresh path" answer, not an error:
    a first-ever spin-up, a pruned-away snapshot and a rotated
    credential epoch are all normal states that must degrade to a
    regular ``ubuntu-26.04`` build rather than fail the workflow.

    When ``expect_epoch`` is given, a snapshot whose epoch differs is
    rejected. That is the guard against the legacy untargeted ``tofu
    destroy``: it regenerates all 81 credentials, so the Postgres roles
    and admin accounts inside an older snapshot no longer match the
    state the pipeline will use.

    Images that are not ``available`` are skipped rather than returned.
    A teardown interrupted between ``create_image`` and completion
    leaves a ``creating`` image behind; it sorts newest, so without this
    it would be picked and fail the spin-up even though a perfectly
    good older snapshot was sitting right behind it.
    """
    snapshots = list_snapshots(token, domain_slug=domain_slug, http_request=http_request)
    for snapshot in snapshots:
        if not snapshot.is_available:
            continue
        if expect_epoch is not None and snapshot.epoch != expect_epoch:
            continue
        return snapshot
    return None


def select_prunable(
    snapshots: tuple[Snapshot, ...],
    *,
    keep: int,
) -> tuple[Snapshot, ...]:
    """Which snapshots a ``keep=N`` retention drops, newest kept first.

    Pure function so the retention decision is testable on its own —
    an off-by-one here deletes the snapshot the next spin-up needs.

    Only ``available`` images count towards ``keep``, and only
    ``available`` images are ever returned as prunable. Both halves
    matter: an interrupted create leaves a ``creating`` image that
    would otherwise occupy a keep slot and evict a good snapshot, while
    deleting an image mid-creation is not something to attempt from a
    retention pass.
    """
    if keep < 1:
        raise HetznerSnapshotError(f"keep must be >= 1, got {keep}")
    available = [s for s in snapshots if s.is_available]
    ordered = sorted(available, key=lambda s: (s.created, s.image_id), reverse=True)
    return tuple(ordered[keep:])


def delete_snapshot(
    image_id: int,
    token: str,
    *,
    http_request: HttpRequest | None = None,
) -> None:
    """Delete one snapshot image permanently."""
    req = _request(http_request)
    req("DELETE", f"{_API_BASE}/images/{image_id}", token, None)


def can_restore_onto(snapshot: Snapshot, *, disk_gb: int, architecture: str) -> bool:
    """Whether ``snapshot`` can be restored onto a type of this shape.

    Hetzner requires the target disk to be at least as large as the
    image's ``disk_size`` and the architecture to match exactly. Both
    constraints are silent until ``tofu apply`` fails, which is why
    capacity selection filters on them up front.
    """
    if snapshot.architecture and architecture and snapshot.architecture != architecture:
        return False
    return disk_gb >= snapshot.disk_gb

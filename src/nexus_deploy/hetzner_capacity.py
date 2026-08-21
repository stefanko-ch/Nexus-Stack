"""Hetzner Cloud capacity-aware server selection (Issue #536).

The legacy deploy used a single (server_type, server_location) pair
and failed at ``tofu apply`` time when Hetzner had no stock for that
exact combination — common during the 2025/26 capacity crunches.
This module queries the Hetzner Cloud API BEFORE tofu runs and picks
the first available pair from an operator-provided preference list,
falling through to the next entry when the preferred one is sold
out.

Public surface:

* :class:`ServerSpec` — frozen ``(server_type, location)`` pair.
* :class:`HetznerCapacityError` — API/auth/network/schema failure.
* :func:`parse_preferences` — comma-list parser with validation.
* :func:`fetch_availability` — calls ``/v1/server_types`` +
  ``/v1/datacenters`` and returns ``location -> {available type names}``.
* :func:`select` — walk preferences in order, return first match.

Default preference list lives in :data:`DEFAULT_PREFERENCES` — used
when neither config.tfvars nor the workflow override provides one.

Why two API calls instead of one: ``/v1/datacenters`` returns
server-type IDs as integers; the per-stock list is keyed by ID, not
name. We resolve names→IDs via ``/v1/server_types`` once, then walk
the datacenters response. Both endpoints are stable and the round-
trip is small (a few KB each).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Hetzner identifier shape — server-type names (``cx43``, ``ccx33``,
# ``cax31``, ``cpx51``) and location names (``fsn1``, ``nbg1``,
# ``hel1``, ``ash``, ``hil``) are all lowercase alphanumeric with
# optional dashes (no real-world example uses one but the API spec
# allows it). This regex is the safety gate at the parser boundary:
# anything outside this character set could break the downstream
# tfvars rewrite (a value containing ``"`` would close the HCL
# string early and effectively inject additional keys; embedded
# newlines would split the value across multiple HCL lines).
_HETZNER_IDENT = re.compile(r"^[a-z0-9-]+$")

_API_BASE = "https://api.hetzner.cloud/v1"
_DEFAULT_TIMEOUT = 30.0

# Default preference list — picked in Issue #536, expanded 2026-05
# (post-May-stock-crunch tiers), revised mid-2026-05 by the operator
# of the Education fork after a class-wide spin-up failed against
# the prior list (cx43 / cpx41 / cx42 / cx52). Strategy unchanged:
# shared-only (no dedicated, no ARM), five type-tiers in cost order,
# three EU regions per tier.
#
#   Tier 1: cx43 (Intel shared, 8 vCPU / 16 GB / 160 GB, project
#           default since 2026-05). The cheapest box that still fits
#           the 40+ Docker stacks workload.
#   Tier 2: cx53 (Intel shared, 16 vCPU / 32 GB / 320 GB). One step
#           up if cx43 is dry across all three EU regions — keeps
#           Intel + shared, just gives more headroom.
#   Tier 3: cpx42 (AMD shared, 8 vCPU / 16 GB / 240 GB). Same
#           8/16 class as cx43, different silicon → independent
#           stock pool. linux/amd64 images run on Intel and AMD
#           without distinction (per CLAUDE.md).
#   Tier 4: cpx52 (AMD shared, 16 vCPU / 32 GB / 360 GB). AMD
#           equivalent of cx53.
#   Tier 5: cpx62 (AMD shared, 32 vCPU / 64 GB / 720 GB). Last
#           resort when nothing else has stock — generously oversized
#           but keeps the spin-up unblocked.
#
# Region order hel1 → fsn1 → nbg1 within every tier — matches the
# historical project default ``server_location = "hel1"`` from
# ``tofu/stack/variables.tf``, so a fresh install that doesn't
# configure SERVER_PREFERENCES at all lands in the same region as
# before #537. Falkenstein and Nuremberg follow as failovers. (PR
# #537 R2 #2 — reordered so the built-in default doesn't silently
# change the region for new installs.)
#
# Deliberately excluded:
#   * ARM (cax*) — Hetzner ARM EU has been chronically constrained
#     and is no longer cheaper (per the 2026-05 note in CLAUDE.md);
#     also some Docker images we ship lack arm64 builds.
#   * Dedicated (ccx*) — gated by a separate per-account quota
#     (typically 8-16 cores total), so a class of N students
#     spinning up in parallel hits the cap immediately. Also ~2.5-3x
#     the price of the equivalent shared tier.
#   * Older shared gens (cx42, cpx41) — dropped from the default in
#     this revision; if you need them as extra fallbacks, set
#     ``SERVER_PREFERENCES`` on the repo to a longer list.
DEFAULT_PREFERENCES = (
    # Tier 1: cx43 (Intel shared, 8/16, project default)
    "cx43:hel1",
    "cx43:fsn1",
    "cx43:nbg1",
    # Tier 2: cx53 (Intel shared, 16/32, headroom)
    "cx53:hel1",
    "cx53:fsn1",
    "cx53:nbg1",
    # Tier 3: cpx42 (AMD shared, 8/16, independent stock pool)
    "cpx42:hel1",
    "cpx42:fsn1",
    "cpx42:nbg1",
    # Tier 4: cpx52 (AMD shared, 16/32)
    "cpx52:hel1",
    "cpx52:fsn1",
    "cpx52:nbg1",
    # Tier 5: cpx62 (AMD shared, 32/64) — last resort
    "cpx62:hel1",
    "cpx62:fsn1",
    "cpx62:nbg1",
)


class HetznerCapacityError(Exception):
    """Hetzner API call failed (auth / network / schema drift / timeout)."""


@dataclass(frozen=True)
class ServerSpec:
    """A ``(server_type, location)`` pair, normalised to lowercase.

    Hetzner's API returns names lowercase already (``cx43``, ``fsn1``);
    we normalise here so the in-memory match in :func:`select` is
    case-insensitive against operator input that may have a stray
    upper-case (e.g. ``CX43:FSN1`` from a copy-paste).
    """

    server_type: str
    location: str

    def __str__(self) -> str:
        return f"{self.server_type}:{self.location}"


@dataclass(frozen=True)
class ServerTypeInfo:
    """Restore-relevant shape of one Hetzner server type.

    ``disk_gb`` and ``architecture`` are the two constraints that decide
    whether a disk snapshot can be restored onto this type: Hetzner
    requires the target disk to be at least as large as the image's and
    the architecture to match exactly. Both are silent until ``tofu
    apply`` fails, which is why the snapshot spin-up filters on them
    before choosing.
    """

    name: str
    disk_gb: int
    architecture: str


def fetch_server_types(
    token: str,
    *,
    http_get: HttpGet | None = None,
) -> dict[str, ServerTypeInfo]:
    """Query ``/v1/server_types`` and return ``{name: ServerTypeInfo}``.

    Deliberately a separate call rather than extra return values on
    :func:`fetch_availability`. That function's signature is monkeypatched
    in a dozen CLI tests and consumed by the legacy spin-up path; widening
    it to serve the snapshot path would put churn on the one code path
    that must not regress. The duplicated request is a few KB against an
    endpoint we already hit, and only on the snapshot path.
    """
    if not token:
        raise HetznerCapacityError("HCLOUD_TOKEN not set")
    get = http_get if http_get is not None else _default_http_get

    payload = get(f"{_API_BASE}/server_types?per_page=200", token)
    server_types = payload.get("server_types") if isinstance(payload, dict) else None
    if not isinstance(server_types, list):
        raise HetznerCapacityError(
            "Hetzner /v1/server_types response missing 'server_types' list",
        )

    out: dict[str, ServerTypeInfo] = {}
    for st in server_types:
        if not isinstance(st, dict):
            continue
        name = st.get("name")
        if not isinstance(name, str):
            continue
        disk = st.get("disk")
        arch = st.get("architecture")
        out[name.lower()] = ServerTypeInfo(
            name=name.lower(),
            disk_gb=int(disk) if isinstance(disk, (int, float)) else 0,
            architecture=arch if isinstance(arch, str) else "",
        )
    return out


def filter_specs(
    preferences: tuple[ServerSpec, ...],
    types: dict[str, ServerTypeInfo],
    *,
    min_disk_gb: int = 0,
    arch: str | None = None,
) -> tuple[tuple[ServerSpec, ...], dict[ServerSpec, str]]:
    """Drop preferences a snapshot could not be restored onto.

    Returns ``(kept, excluded)`` where ``excluded`` maps each dropped
    spec to a human-readable reason, so the operator can see *why* a
    tier was skipped rather than just watching it vanish.

    The defaults (``min_disk_gb=0``, ``arch=None``) are a no-op: every
    preference is kept and ``excluded`` is empty. That is what keeps the
    legacy spin-up path byte-for-byte unchanged.

    A type absent from ``types`` is kept, not dropped. Hetzner
    occasionally lists a type in a datacenter's ``available`` set before
    it appears in ``/v1/server_types``; failing open leaves that case to
    :func:`select`, which is where "unknown type" is already handled.
    """
    if min_disk_gb <= 0 and arch is None:
        return preferences, {}

    kept: list[ServerSpec] = []
    excluded: dict[ServerSpec, str] = {}
    for spec in preferences:
        info = types.get(spec.server_type)
        if info is None:
            kept.append(spec)
            continue
        if arch is not None and info.architecture and info.architecture != arch:
            excluded[spec] = f"architecture {info.architecture} != {arch}"
            continue
        if min_disk_gb > 0 and info.disk_gb < min_disk_gb:
            excluded[spec] = f"disk {info.disk_gb}GB < {min_disk_gb}GB required"
            continue
        kept.append(spec)
    return tuple(kept), excluded


def parse_preferences(value: str) -> tuple[ServerSpec, ...]:
    """Parse a comma-list of ``<server_type>:<location>`` tokens.

    Whitespace around tokens / inside the colon-separated halves is
    stripped. Empty tokens (e.g. trailing comma) are skipped. The
    result is a non-empty tuple in input order.

    Raises :class:`ValueError` on:

    * empty / whitespace-only input
    * any non-empty token without ``:``
    * a token with empty type or empty location
    * a duplicate ``(type, location)`` pair (would just waste an API
      lookup; almost certainly a typo)
    """
    if not value or not value.strip():
        raise ValueError("server_preferences is empty")
    seen: set[tuple[str, str]] = set()
    specs: list[ServerSpec] = []
    for raw in value.split(","):
        token = raw.strip()
        if not token:
            continue
        # PR #537 R3 #1: reject tokens with !=1 colon. ``partition(":")``
        # silently consumes only the first colon, so ``cx43:fsn1:dc14``
        # would parse to location=``fsn1:dc14`` — a value that never
        # matches the Hetzner location-name keys, producing confusing
        # "out of stock" outcomes for the operator.
        if token.count(":") != 1:
            raise ValueError(
                f"server_preferences token must have exactly one ':' separator: {token!r}",
            )
        server_type, _, location = token.partition(":")
        server_type = server_type.strip().lower()
        location = location.strip().lower()
        if not server_type or not location:
            raise ValueError(
                f"server_preferences token has empty type or location: {token!r}",
            )
        # PR #537 R8 #1: defensive charset gate. ``server_type`` and
        # ``location`` are interpolated as ``"{value}"`` into HCL by
        # the downstream tfvars rewrite; a value containing ``"`` or
        # a newline would break the file (close the HCL string early
        # and inject extra keys). Hetzner's own identifiers are
        # lowercase ``[a-z0-9-]+`` so the gate is conservative on
        # legitimate input.
        # PR #538 R1 #1: error wording — input is already ``.lower()``'d
        # before this charset check, so saying "expected lowercase" is
        # misleading (the operator could pass ``Cx43:Fsn1`` and it would
        # pass; a Unicode-letter token like ``cx43:fsñ1`` would lowercase
        # cleanly but still fail charset). The real constraint is ASCII.
        for half_name, half_value in (("type", server_type), ("location", location)):
            if not _HETZNER_IDENT.fullmatch(half_value):
                raise ValueError(
                    f"server_preferences {half_name} has invalid characters "
                    f"(expected ASCII letters, digits, or dash): {token!r}",
                )
        key = (server_type, location)
        if key in seen:
            raise ValueError(
                f"duplicate server_preferences entry: {server_type}:{location}",
            )
        seen.add(key)
        specs.append(ServerSpec(server_type=server_type, location=location))
    if not specs:
        raise ValueError("server_preferences contained no valid entries")
    return tuple(specs)


# DI seam: production uses :func:`_default_http_get`; tests inject a
# fake. Signature: (url, bearer_token) -> parsed JSON object.
HttpGet = Callable[[str, str], Any]


def _default_http_get(url: str, token: str) -> Any:
    """Production HTTP GET. Returns parsed JSON.

    Raises :class:`HetznerCapacityError` for every failure mode
    (HTTP 4xx/5xx, network, timeout, malformed JSON) so the pipeline
    can surface a single error class. The original exception is
    chained via ``__cause__`` so a debugger pass still has the full
    detail.
    """
    req = urllib.request.Request(  # noqa: S310 — URL is hard-coded literal _API_BASE
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise HetznerCapacityError(
            f"Hetzner API HTTP {exc.code} for {url}: {exc.reason}",
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HetznerCapacityError(
            f"Hetzner API request failed for {url}: {type(exc).__name__}: {exc}",
        ) from exc
    # PR #537 R6 #4: catch UnicodeDecodeError from a non-UTF-8 body
    # (e.g. a misconfigured upstream proxy serving binary garbage on
    # what should be JSON). Without the catch, a decode failure would
    # propagate as an uncaught UnicodeDecodeError and bypass the
    # caller's HetznerCapacityError handler.
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HetznerCapacityError(
            f"Hetzner API returned non-UTF-8 body for {url}: {exc}",
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HetznerCapacityError(
            f"Hetzner API returned non-JSON for {url}: {exc}",
        ) from exc


def fetch_availability(
    token: str,
    *,
    http_get: HttpGet | None = None,
) -> dict[str, set[str]]:
    """Query ``/v1/server_types`` + ``/v1/datacenters``.

    Returns a map ``{location_name: {available_server_type_name, ...}}``.
    A location is considered to "have" a server type if ANY datacenter
    at that location lists the type's ID in ``server_types.available``.
    (A single location like ``fsn1`` typically has 1-2 datacenters
    such as ``fsn1-dc14``; treating any-DC-available as
    location-available matches what ``tofu apply`` would actually
    succeed at.)

    Raises :class:`HetznerCapacityError` on auth/network failures or
    when either response is missing the expected top-level field
    (defensive against a future API schema change).
    """
    if not token:
        raise HetznerCapacityError("HCLOUD_TOKEN not set")
    get = http_get if http_get is not None else _default_http_get

    types_payload = get(f"{_API_BASE}/server_types?per_page=200", token)
    server_types = types_payload.get("server_types") if isinstance(types_payload, dict) else None
    if not isinstance(server_types, list):
        raise HetznerCapacityError(
            "Hetzner /v1/server_types response missing 'server_types' list",
        )
    id_to_name: dict[int, str] = {}
    for st in server_types:
        if not isinstance(st, dict):
            continue
        st_id = st.get("id")
        st_name = st.get("name")
        if isinstance(st_id, int) and isinstance(st_name, str):
            id_to_name[st_id] = st_name.lower()

    dc_payload = get(f"{_API_BASE}/datacenters?per_page=50", token)
    datacenters = dc_payload.get("datacenters") if isinstance(dc_payload, dict) else None
    if not isinstance(datacenters, list):
        raise HetznerCapacityError(
            "Hetzner /v1/datacenters response missing 'datacenters' list",
        )

    by_location: dict[str, set[str]] = {}
    for dc in datacenters:
        if not isinstance(dc, dict):
            continue
        location = dc.get("location")
        if not isinstance(location, dict):
            continue
        loc_name = location.get("name")
        if not isinstance(loc_name, str):
            continue
        loc_name = loc_name.lower()
        st_field = dc.get("server_types")
        if not isinstance(st_field, dict):
            continue
        available = st_field.get("available")
        if not isinstance(available, list):
            continue
        names = {id_to_name[i] for i in available if isinstance(i, int) and i in id_to_name}
        by_location.setdefault(loc_name, set()).update(names)
    return by_location


def select(
    preferences: tuple[ServerSpec, ...],
    availability: dict[str, set[str]],
) -> ServerSpec | None:
    """Walk ``preferences`` in order; return the first spec whose
    type is listed as available at the corresponding location.

    Returns ``None`` when every preference is out of stock — the
    caller (CLI handler) is responsible for turning that into a
    user-facing error with the per-pair status, since "list
    exhausted" is the operator-actionable case.
    """
    for spec in preferences:
        types_at_loc = availability.get(spec.location, set())
        if spec.server_type in types_at_loc:
            return spec
    return None


def render_status_lines(
    preferences: tuple[ServerSpec, ...],
    availability: dict[str, set[str]],
    selected: ServerSpec | None,
    excluded: dict[ServerSpec, str] | None = None,
) -> list[str]:
    """Build a per-preference status block for operator-facing logs.

    One line per preference, marking the selected one with ``→``,
    available-but-not-picked with ``✓``, and unavailable with ``✗``.
    Used by the CLI handler so the operator can see WHY a particular
    pair was chosen (or why all of them failed).

    Markers (PR #537 R7 #2 — split unknown-location from out-of-stock):

    * ``→`` — selected (the pair :func:`select` returned)
    * ``✓`` — available at this location but not picked (a later
      preference matched first, or this entry was passed in
      preference order)
    * ``✗`` — known location, but the requested type isn't in the
      ``available`` set (genuinely sold out / not supported there)
    * ``?`` — location key absent from ``availability`` entirely;
      almost always an operator typo (e.g. ``cx43:atlantis``).
      Suffix ``(unknown location)`` is appended so the failure
      message is actionable without the operator having to know
      the marker convention.
    * ``⊘`` — excluded before the availability walk because the type
      cannot host the snapshot being restored (disk too small, or
      wrong architecture). Only appears when ``excluded`` is passed,
      i.e. on the snapshot spin-up path; the reason is appended so a
      skipped tier does not look like a capacity problem.

    ``excluded`` defaults to ``None`` so the legacy call site renders
    exactly as before.
    """
    excluded = excluded or {}
    lines: list[str] = []
    for idx, spec in enumerate(preferences, start=1):
        if spec == selected:
            marker = "→"
            suffix = ""
        elif spec in excluded:
            marker = "⊘"
            suffix = f" ({excluded[spec]})"
        elif spec.location not in availability:
            marker = "?"
            suffix = " (unknown location)"
        elif spec.server_type in availability[spec.location]:
            marker = "✓"
            suffix = ""
        else:
            marker = "✗"
            suffix = ""
        lines.append(f"  {marker} {idx}. {spec}{suffix}")
    return lines

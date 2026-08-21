"""Tests for nexus_deploy.hetzner_capacity (Issue #536).

Three layers:

1. ``parse_preferences()`` — comma-list parser + validation.
2. ``fetch_availability()`` — HTTP integration via the ``http_get``
   DI seam (no real network calls).
3. ``select()`` + ``render_status_lines()`` — pure-logic preference
   walking.

Hetzner's API responses are stable enough that we hard-code
representative fixture payloads. The two-call pattern (server_types
then datacenters) is reproduced verbatim so a future schema change
shows up as a focused test failure rather than a runtime surprise.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_deploy.hetzner_capacity import (
    DEFAULT_PREFERENCES,
    HetznerCapacityError,
    ServerSpec,
    ServerTypeInfo,
    fetch_availability,
    fetch_server_types,
    filter_specs,
    parse_preferences,
    render_status_lines,
    select,
)

# ---------------------------------------------------------------------------
# parse_preferences
# ---------------------------------------------------------------------------


def test_parse_preferences_standard_form() -> None:
    """The canonical case: 3 ``type:loc`` tokens, comma-separated."""
    result = parse_preferences("cx43:fsn1, cx43:nbg1, ccx33:hel1")
    assert result == (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("cx43", "nbg1"),
        ServerSpec("ccx33", "hel1"),
    )


def test_parse_preferences_lowercases_input() -> None:
    """Operators copying from a list may have stray uppercase; the
    parser normalises so the in-memory match is case-insensitive."""
    result = parse_preferences("CX43:FSN1, ccx33:Hel1")
    assert result == (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("ccx33", "hel1"),
    )


def test_parse_preferences_skips_empty_tokens() -> None:
    """Trailing comma / double comma → empty token, silently skipped.
    Mirrors what a hand-edited config.tfvars usually looks like."""
    result = parse_preferences("cx43:fsn1,,cx43:hel1,")
    assert result == (ServerSpec("cx43", "fsn1"), ServerSpec("cx43", "hel1"))


def test_parse_preferences_strips_whitespace_inside_token() -> None:
    """``cx43 : fsn1`` is valid; whitespace inside the colon-separated
    halves is stripped."""
    result = parse_preferences("cx43 : fsn1 ,  ccx33 : nbg1 ")
    assert result == (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("ccx33", "nbg1"),
    )


def test_parse_preferences_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_preferences("")
    with pytest.raises(ValueError, match="empty"):
        parse_preferences("   \n  ")


def test_parse_preferences_rejects_token_without_colon() -> None:
    with pytest.raises(ValueError, match="exactly one ':' separator"):
        parse_preferences("cx43, fsn1")  # comma between, no colon


def test_parse_preferences_rejects_token_with_multiple_colons() -> None:
    """PR #537 R3 #1: ``cx43:fsn1:dc14`` used to parse silently to
    location=``fsn1:dc14`` because ``partition(':')`` only splits the
    first colon. That location would never match the Hetzner
    location-name keys, producing a confusing 'out of stock'
    outcome with no obvious cause."""
    with pytest.raises(ValueError, match="exactly one ':' separator"):
        parse_preferences("cx43:fsn1:dc14")


def test_parse_preferences_rejects_empty_half() -> None:
    with pytest.raises(ValueError, match="empty type or location"):
        parse_preferences("cx43:")
    with pytest.raises(ValueError, match="empty type or location"):
        parse_preferences(":fsn1")


def test_parse_preferences_rejects_duplicate_pair() -> None:
    """Duplicates are almost always typos; reject so the operator
    notices instead of silently consuming an extra API lookup."""
    with pytest.raises(ValueError, match="duplicate"):
        parse_preferences("cx43:fsn1, cx43:fsn1")


def test_parse_preferences_rejects_quote_in_value() -> None:
    """PR #537 R8 #1: a value containing ``"`` would break the
    downstream tfvars rewrite (close the HCL string early). Reject
    at the parser boundary before it can reach the rewriter."""
    with pytest.raises(ValueError, match="invalid characters"):
        parse_preferences('cx43:fsn1", server_type = "evil')


def test_parse_preferences_rejects_newline_in_value() -> None:
    """Embedded newline would split the HCL value across multiple
    lines on rewrite. Defensive — the env var pipeline shouldn't
    emit newlines but a hand-edited config.tfvars could.
    (Input keeps a single colon so the charset check fires; a
    multi-colon input would short-circuit to the colon-count error
    instead — see test_parse_preferences_rejects_token_with_multiple_colons.)"""
    with pytest.raises(ValueError, match="invalid characters"):
        parse_preferences("cx43:fsn1\nbreakout")


def test_parse_preferences_accepts_dash_in_identifier() -> None:
    """Hetzner's identifier shape is ``[a-z0-9-]+``; no current name
    uses a dash but the API spec allows it. Don't over-constrain."""
    # Synthetic — no real Hetzner type uses this shape, but the
    # parser must not preemptively reject it.
    result = parse_preferences("cx-future:fsn1")
    assert result == (ServerSpec("cx-future", "fsn1"),)


def test_parse_preferences_rejects_only_commas() -> None:
    """``,,,`` parses to all-empty tokens (skipped) → no specs."""
    with pytest.raises(ValueError, match="no valid entries"):
        parse_preferences(",,,")


def test_default_preferences_parse_round_trip() -> None:
    """The hard-coded DEFAULT_PREFERENCES tuple must round-trip
    through the parser; protects against a future typo in the
    default that would only surface in production."""
    parsed = parse_preferences(",".join(DEFAULT_PREFERENCES))
    assert tuple(str(spec) for spec in parsed) == DEFAULT_PREFERENCES


# ---------------------------------------------------------------------------
# fetch_availability
# ---------------------------------------------------------------------------


# Representative Hetzner Cloud API payloads. IDs picked to match the
# real ones at the time of writing; the test is robust to ID drift
# because we only check name-keyed result.
_FAKE_SERVER_TYPES = {
    "server_types": [
        {"id": 22, "name": "cx43"},
        {"id": 45, "name": "ccx33"},
        {"id": 9, "name": "cax31"},
    ],
}

_FAKE_DATACENTERS = {
    "datacenters": [
        {
            "id": 1,
            "name": "fsn1-dc14",
            "location": {"name": "fsn1"},
            "server_types": {"available": [22, 45], "supported": [22, 45, 9]},
        },
        {
            "id": 2,
            "name": "nbg1-dc3",
            "location": {"name": "nbg1"},
            "server_types": {"available": [45], "supported": [22, 45, 9]},
        },
        {
            "id": 4,
            "name": "hel1-dc2",
            "location": {"name": "hel1"},
            "server_types": {"available": [], "supported": [22, 45, 9]},
        },
    ],
}


def _make_http_get(types_payload: Any, dc_payload: Any) -> Any:
    """Build a fake ``http_get`` that routes server_types vs
    datacenters to the right fixture."""
    calls: list[tuple[str, str]] = []

    def _http_get(url: str, token: str) -> Any:
        calls.append((url, token))
        if "/server_types" in url:
            return types_payload
        if "/datacenters" in url:
            return dc_payload
        raise AssertionError(f"unexpected URL {url}")

    _http_get.calls = calls  # type: ignore[attr-defined]
    return _http_get


def test_fetch_availability_happy_path() -> None:
    fake = _make_http_get(_FAKE_SERVER_TYPES, _FAKE_DATACENTERS)
    result = fetch_availability("token-abc", http_get=fake)
    assert result == {
        "fsn1": {"cx43", "ccx33"},
        "nbg1": {"ccx33"},
        "hel1": set(),
    }
    # Verify the bearer token is forwarded on both calls.
    assert all(token == "token-abc" for _url, token in fake.calls)
    # Both endpoints hit; correct order doesn't matter functionally
    # but pin one call per endpoint to catch accidental duplication.
    assert sum("/server_types" in u for u, _ in fake.calls) == 1
    assert sum("/datacenters" in u for u, _ in fake.calls) == 1


def test_fetch_availability_collapses_multiple_datacenters_per_location() -> None:
    """A location with two datacenters should report the UNION of
    their available server_types — operator only cares whether ANY
    DC at that location can fulfil the request."""
    multi_dc = {
        "datacenters": [
            {
                "id": 1,
                "name": "fsn1-dc14",
                "location": {"name": "fsn1"},
                "server_types": {"available": [22]},  # cx43 only
            },
            {
                "id": 99,
                "name": "fsn1-dc15",
                "location": {"name": "fsn1"},
                "server_types": {"available": [45]},  # ccx33 only
            },
        ],
    }
    fake = _make_http_get(_FAKE_SERVER_TYPES, multi_dc)
    result = fetch_availability("t", http_get=fake)
    assert result == {"fsn1": {"cx43", "ccx33"}}


def test_fetch_availability_rejects_empty_token() -> None:
    """Don't even make the call without a token — saves a guaranteed
    401 round-trip and gives a more specific error."""
    with pytest.raises(HetznerCapacityError, match="HCLOUD_TOKEN not set"):
        fetch_availability("")


def test_fetch_availability_raises_on_missing_server_types_field() -> None:
    """Schema-drift safety: if Hetzner ever drops the top-level key
    name we want to fail loudly, not silently return {}."""
    fake = _make_http_get({"unexpected": []}, _FAKE_DATACENTERS)
    with pytest.raises(HetznerCapacityError, match="server_types"):
        fetch_availability("t", http_get=fake)


def test_fetch_availability_raises_on_missing_datacenters_field() -> None:
    fake = _make_http_get(_FAKE_SERVER_TYPES, {"unexpected": []})
    with pytest.raises(HetznerCapacityError, match="datacenters"):
        fetch_availability("t", http_get=fake)


def test_fetch_availability_skips_malformed_entries() -> None:
    """Defensive against partial-shape entries (a future API field
    becoming optional). Skip + continue, don't crash."""
    types_payload = {
        "server_types": [
            {"id": 22, "name": "cx43"},
            {"id": "not-an-int", "name": "garbage"},  # skipped
            "not-a-dict",  # skipped
            {"id": 45},  # missing name → skipped
        ],
    }
    dc_payload = {
        "datacenters": [
            {
                "id": 1,
                "name": "fsn1-dc14",
                "location": {"name": "fsn1"},
                "server_types": {"available": [22, 999]},  # 999 unknown → skipped
            },
            "not-a-dict",  # skipped
        ],
    }
    fake = _make_http_get(types_payload, dc_payload)
    result = fetch_availability("t", http_get=fake)
    assert result == {"fsn1": {"cx43"}}


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


def test_select_returns_first_match() -> None:
    """Walks preferences in order; first preference wins even if a
    later one is also available."""
    prefs = (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("ccx33", "fsn1"),
    )
    availability = {"fsn1": {"cx43", "ccx33"}}
    assert select(prefs, availability) == ServerSpec("cx43", "fsn1")


def test_select_skips_unavailable() -> None:
    """When the first preference is sold out, fall through to the
    next available pair."""
    prefs = (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("cx43", "nbg1"),
        ServerSpec("ccx33", "hel1"),
    )
    availability = {
        "fsn1": {"ccx33"},  # cx43 sold out at fsn1
        "nbg1": {"cx43"},  # cx43 available at nbg1 → pick this one
        "hel1": {"cx43", "ccx33"},
    }
    assert select(prefs, availability) == ServerSpec("cx43", "nbg1")


def test_select_returns_none_when_exhausted() -> None:
    """Every preference out of stock → caller decides what to do."""
    prefs = (ServerSpec("cx43", "fsn1"),)
    assert select(prefs, {"fsn1": {"ccx33"}}) is None
    assert select(prefs, {}) is None  # location not in API response at all


def test_select_handles_unknown_location() -> None:
    """Operator typed ``cx43:atlantis`` → Atlantis isn't in the
    availability map → that preference is silently skipped (caller
    handles the all-skipped case via ``select() is None``)."""
    prefs = (
        ServerSpec("cx43", "atlantis"),
        ServerSpec("cx43", "fsn1"),
    )
    availability = {"fsn1": {"cx43"}}
    assert select(prefs, availability) == ServerSpec("cx43", "fsn1")


# ---------------------------------------------------------------------------
# render_status_lines
# ---------------------------------------------------------------------------


def test_render_status_marks_selected_with_arrow() -> None:
    prefs = (
        ServerSpec("cx43", "fsn1"),
        ServerSpec("cx43", "nbg1"),
        ServerSpec("ccx33", "hel1"),
    )
    availability = {
        "fsn1": set(),
        "nbg1": {"cx43"},
        "hel1": {"ccx33"},
    }
    selected = ServerSpec("cx43", "nbg1")
    lines = render_status_lines(prefs, availability, selected)
    # ``→`` for selected, ``✓`` for available-but-not-picked, ``✗``
    # for unavailable.
    assert lines == [
        "  ✗ 1. cx43:fsn1",
        "  → 2. cx43:nbg1",
        "  ✓ 3. ccx33:hel1",
    ]


def test_render_status_marks_unknown_location_with_question() -> None:
    """PR #537 R7 #2: a preference whose location key is missing from
    the availability map (almost always an operator typo) is marked
    ``?`` with a ``(unknown location)`` suffix, NOT ``✗``. ``✗`` is
    reserved for known-but-empty locations (genuine sold-out)."""
    prefs = (
        ServerSpec("cx43", "atlantis"),  # unknown — typo
        ServerSpec("cx43", "fsn1"),  # known, sold out
        ServerSpec("ccx33", "fsn1"),  # known, available — picked
    )
    availability = {"fsn1": {"ccx33"}}
    selected = ServerSpec("ccx33", "fsn1")
    lines = render_status_lines(prefs, availability, selected)
    assert lines == [
        "  ? 1. cx43:atlantis (unknown location)",
        "  ✗ 2. cx43:fsn1",
        "  → 3. ccx33:fsn1",
    ]


def test_render_status_handles_no_selection() -> None:
    """When everything is out of stock, no ``→`` marker — every
    preference gets ``✗``."""
    prefs = (ServerSpec("cx43", "fsn1"),)
    lines = render_status_lines(prefs, {"fsn1": set()}, None)
    assert lines == ["  ✗ 1. cx43:fsn1"]


# ---------------------------------------------------------------------------
# fetch_availability — defensive continue branches (PR #537 R5 coverage)
# ---------------------------------------------------------------------------


def test_fetch_availability_skips_dc_with_missing_location() -> None:
    """Datacenter entry without a ``location`` dict → skipped, not
    crashed. Future schema where the field becomes optional must
    not take down the whole capacity check."""
    dc_payload = {
        "datacenters": [
            {"id": 1, "name": "fsn1-dc14", "server_types": {"available": [22]}},
            {
                "id": 2,
                "name": "nbg1-dc3",
                "location": {"name": "nbg1"},
                "server_types": {"available": [22]},
            },
        ],
    }
    fake = _make_http_get(_FAKE_SERVER_TYPES, dc_payload)
    result = fetch_availability("t", http_get=fake)
    # Only the well-formed nbg1 entry survived.
    assert result == {"nbg1": {"cx43"}}


def test_fetch_availability_skips_dc_with_non_string_location_name() -> None:
    dc_payload = {
        "datacenters": [
            {
                "id": 1,
                "name": "weird",
                "location": {"name": 12345},  # int, not string
                "server_types": {"available": [22]},
            },
            {
                "id": 2,
                "name": "fsn1-dc14",
                "location": {"name": "fsn1"},
                "server_types": {"available": [22]},
            },
        ],
    }
    fake = _make_http_get(_FAKE_SERVER_TYPES, dc_payload)
    result = fetch_availability("t", http_get=fake)
    assert result == {"fsn1": {"cx43"}}


def test_fetch_availability_skips_dc_with_missing_server_types_field() -> None:
    dc_payload = {
        "datacenters": [
            {"id": 1, "name": "fsn1-dc14", "location": {"name": "fsn1"}},
            {
                "id": 2,
                "name": "nbg1-dc3",
                "location": {"name": "nbg1"},
                "server_types": {"available": [22]},
            },
        ],
    }
    fake = _make_http_get(_FAKE_SERVER_TYPES, dc_payload)
    result = fetch_availability("t", http_get=fake)
    assert result == {"nbg1": {"cx43"}}


def test_fetch_availability_skips_dc_with_non_list_available() -> None:
    dc_payload = {
        "datacenters": [
            {
                "id": 1,
                "name": "fsn1-dc14",
                "location": {"name": "fsn1"},
                "server_types": {"available": "not-a-list"},
            },
            {
                "id": 2,
                "name": "nbg1-dc3",
                "location": {"name": "nbg1"},
                "server_types": {"available": [22]},
            },
        ],
    }
    fake = _make_http_get(_FAKE_SERVER_TYPES, dc_payload)
    result = fetch_availability("t", http_get=fake)
    assert result == {"nbg1": {"cx43"}}


# ---------------------------------------------------------------------------
# _default_http_get — production HTTP path (PR #537 R5 coverage)
#
# Tests exercise the real urllib-backed implementation by monkey-
# patching ``urllib.request.urlopen`` so we don't make actual network
# calls. Each branch (HTTP error / URL error / TimeoutError /
# malformed JSON / happy path) is pinned because these paths only
# fire in production, not when callers inject the ``http_get`` seam.
# ---------------------------------------------------------------------------


class _FakeUrlopenContext:
    """Context-manager stand-in for ``urllib.request.urlopen()`` —
    the ``with urlopen(req) as resp`` pattern requires both
    ``__enter__`` and ``__exit__``."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeUrlopenContext:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_default_http_get_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real urllib path: build Request, parse JSON body, return dict."""
    from nexus_deploy.hetzner_capacity import _default_http_get

    captured: dict[str, object] = {}

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        captured["url"] = req.full_url  # type: ignore[attr-defined]
        captured["auth"] = req.headers.get("Authorization")  # type: ignore[attr-defined]
        captured["timeout"] = timeout
        return _FakeUrlopenContext(b'{"ok": true}')

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    result = _default_http_get("https://api.hetzner.cloud/v1/server_types", "abc-token")
    assert result == {"ok": True}
    assert captured["url"] == "https://api.hetzner.cloud/v1/server_types"
    assert captured["auth"] == "Bearer abc-token"
    assert captured["timeout"] == 30.0  # _DEFAULT_TIMEOUT


def test_default_http_get_wraps_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 4xx/5xx → HetznerCapacityError carrying the status + reason."""
    import urllib.error

    from nexus_deploy.hetzner_capacity import _default_http_get

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        raise urllib.error.HTTPError(
            url="https://example/v1/x",
            code=401,
            msg="Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"HTTP 401.*Unauthorized"):
        _default_http_get("https://example/v1/x", "t")


def test_default_http_get_wraps_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS / connection failure → HetznerCapacityError with class name."""
    import urllib.error

    from nexus_deploy.hetzner_capacity import _default_http_get

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"URLError"):
        _default_http_get("https://api.hetzner.cloud/v1/datacenters", "t")


def test_default_http_get_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Socket timeout (TimeoutError subclass of OSError on modern Py)
    → HetznerCapacityError. Don't surface the raw exception at the CLI."""
    from nexus_deploy.hetzner_capacity import _default_http_get

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        raise TimeoutError("read timeout after 30s")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"TimeoutError|read timeout"):
        _default_http_get("https://api.hetzner.cloud/v1/datacenters", "t")


def test_default_http_get_wraps_non_utf8_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR #537 R6 #4: a misconfigured upstream proxy serving binary
    garbage on what should be JSON would have escaped as an uncaught
    UnicodeDecodeError. Now wrapped into HetznerCapacityError so the
    CLI handler sees the same single error class as every other
    failure mode."""
    from nexus_deploy.hetzner_capacity import _default_http_get

    # 0x80 is invalid as the start of a UTF-8 sequence.
    bad_bytes = b"\x80\x81\x82 not utf-8"

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        return _FakeUrlopenContext(bad_bytes)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"non-UTF-8"):
        _default_http_get("https://api.hetzner.cloud/v1/datacenters", "t")


def test_default_http_get_wraps_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Body parses to non-JSON → HetznerCapacityError with parser detail.
    Defensive against an upstream proxy that intercepts and serves an
    HTML error page on what should have been a JSON response."""
    from nexus_deploy.hetzner_capacity import _default_http_get

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        return _FakeUrlopenContext(b"<html>500 Internal Server Error</html>")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"non-JSON"):
        _default_http_get("https://api.hetzner.cloud/v1/datacenters", "t")


# ---------------------------------------------------------------------------
# fetch_server_types + filter_specs — snapshot restore constraints
# ---------------------------------------------------------------------------

# Disk sizes are the real ones for these types; the whole point of the
# filter is that DEFAULT_PREFERENCES mixes them, so a snapshot taken on
# one tier cannot necessarily be restored onto another.
_FAKE_TYPES_WITH_DISK = {
    "server_types": [
        {"id": 22, "name": "cx43", "disk": 160, "architecture": "x86"},
        {"id": 23, "name": "cx53", "disk": 320, "architecture": "x86"},
        {"id": 24, "name": "cpx42", "disk": 240, "architecture": "x86"},
        {"id": 9, "name": "cax31", "disk": 160, "architecture": "arm"},
    ],
}


def test_fetch_server_types_parses_disk_and_architecture() -> None:
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK, _FAKE_DATACENTERS)
    types = fetch_server_types("t", http_get=fake)
    assert types["cx43"] == ServerTypeInfo(name="cx43", disk_gb=160, architecture="x86")
    assert types["cax31"].architecture == "arm"


def test_fetch_server_types_rejects_empty_token() -> None:
    with pytest.raises(HetznerCapacityError, match="HCLOUD_TOKEN not set"):
        fetch_server_types("")


def test_fetch_server_types_raises_on_schema_drift() -> None:
    fake = _make_http_get({"nope": []}, _FAKE_DATACENTERS)
    with pytest.raises(HetznerCapacityError, match="missing 'server_types' list"):
        fetch_server_types("t", http_get=fake)


def test_fetch_server_types_skips_malformed_entries() -> None:
    fake = _make_http_get(
        {"server_types": [{"id": 1, "name": "cx43", "disk": 160}, {"id": 2}, "junk"]},
        _FAKE_DATACENTERS,
    )
    types = fetch_server_types("t", http_get=fake)
    assert list(types) == ["cx43"]
    # Missing architecture must not become a bogus value.
    assert types["cx43"].architecture == ""


def test_filter_specs_defaults_are_a_no_op() -> None:
    """The regression guard for the legacy spin-up path.

    select-capacity calls this with no constraints; if the defaults ever
    started filtering, a normal deploy could silently lose tiers.
    """
    prefs = parse_preferences("cx43:fsn1, cax31:hel1, cx53:nbg1")
    kept, excluded = filter_specs(prefs, {})
    assert kept == prefs
    assert excluded == {}


def test_filter_specs_drops_types_with_too_small_a_disk() -> None:
    """A 240GB snapshot cannot be restored onto a 160GB cx43."""
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK, _FAKE_DATACENTERS)
    types = fetch_server_types("t", http_get=fake)
    prefs = parse_preferences("cx43:fsn1, cpx42:fsn1, cx53:fsn1")
    kept, excluded = filter_specs(prefs, types, min_disk_gb=240)
    assert [str(s) for s in kept] == ["cpx42:fsn1", "cx53:fsn1"]
    assert "disk 160GB < 240GB required" in excluded[ServerSpec("cx43", "fsn1")]


def test_filter_specs_drops_mismatched_architecture() -> None:
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK, _FAKE_DATACENTERS)
    types = fetch_server_types("t", http_get=fake)
    prefs = parse_preferences("cx43:fsn1, cax31:hel1")
    kept, excluded = filter_specs(prefs, types, arch="x86")
    assert [str(s) for s in kept] == ["cx43:fsn1"]
    assert "architecture arm != x86" in excluded[ServerSpec("cax31", "hel1")]


def test_filter_specs_keeps_unknown_types() -> None:
    """Fail open: Hetzner can list a type as available before it shows
    up in /v1/server_types. Dropping it here would turn a transient API
    lag into a failed spin-up; select() already handles unknown types.
    """
    prefs = parse_preferences("brandnew:fsn1")
    kept, excluded = filter_specs(prefs, {}, min_disk_gb=999)
    assert kept == prefs
    assert excluded == {}


def test_filter_specs_tolerates_unknown_architecture_on_the_type() -> None:
    """Only enforce what is actually known."""
    types = {"cx43": ServerTypeInfo(name="cx43", disk_gb=160, architecture="")}
    prefs = parse_preferences("cx43:fsn1")
    kept, _excluded = filter_specs(prefs, types, arch="x86")
    assert kept == prefs


def test_render_status_lines_marks_excluded_with_reason() -> None:
    prefs = parse_preferences("cx43:fsn1, cpx42:fsn1")
    excluded = {ServerSpec("cx43", "fsn1"): "disk 160GB < 240GB required"}
    lines = render_status_lines(
        prefs,
        {"fsn1": {"cx43", "cpx42"}},
        ServerSpec("cpx42", "fsn1"),
        excluded,
    )
    assert "⊘" in lines[0]
    assert "disk 160GB < 240GB required" in lines[0]
    assert lines[1].strip().startswith("→")


def test_render_status_lines_without_excluded_is_unchanged() -> None:
    """Byte-for-byte identical to the pre-change output."""
    prefs = parse_preferences("cx43:fsn1, ccx33:nbg1")
    availability = {"fsn1": {"cx43"}, "nbg1": set()}
    selected = ServerSpec("cx43", "fsn1")
    assert render_status_lines(prefs, availability, selected) == render_status_lines(
        prefs,
        availability,
        selected,
        None,
    )

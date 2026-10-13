"""Tests for nexus_deploy.hetzner_capacity (Issue #536).

Three layers:

1. ``parse_preferences()`` — comma-list parser + validation.
2. ``fetch_availability()`` — HTTP integration via the ``http_get``
   DI seam (no real network calls).
3. ``select()`` + ``render_status_lines()`` — pure-logic preference
   walking.

Hetzner's API responses are stable enough that we hard-code
representative fixture payloads. The two-call pattern (server_types
locations) is reproduced verbatim so a future schema change
shows up as a focused test failure rather than a runtime surprise.
"""

from __future__ import annotations

import pathlib
import re
import urllib.error
from typing import Any
from unittest import mock

import pytest

from nexus_deploy import hetzner_capacity
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
        {
            "id": 22,
            "name": "cx43",
            "locations": [
                {"id": 1, "name": "fsn1", "available": True, "recommended": True},
                {"id": 2, "name": "nbg1", "available": False, "recommended": False},
                {"id": 3, "name": "hel1", "available": False, "recommended": False},
            ],
        },
        {
            "id": 45,
            "name": "ccx33",
            "locations": [
                {"id": 1, "name": "fsn1", "available": True, "recommended": False},
                {"id": 2, "name": "nbg1", "available": True, "recommended": False},
                {"id": 3, "name": "hel1", "available": False, "recommended": False},
            ],
        },
        {
            "id": 9,
            "name": "cax31",
            "locations": [
                {"id": 3, "name": "hel1", "available": False, "recommended": False},
            ],
        },
    ],
}


#: The one URL the module may request. Matched EXACTLY by the fake below —
#: a substring match on "/server_types" would also accept
#: `/v1/server_types/invalid`, so a broken path would pass the tests.
_EXPECTED_URL = "https://api.hetzner.cloud/v1/server_types?per_page=200"


def _make_http_get(types_payload: Any) -> Any:
    """Build a fake ``http_get`` that serves exactly one URL.

    Anything else is a bug the fake must expose rather than absorb: the
    datacenter endpoints were removed by Hetzner on 2026-10-01 and answer
    410 Gone, and a malformed server-types path would 404.
    """
    calls: list[tuple[str, str]] = []

    def _http_get(url: str, token: str) -> Any:
        calls.append((url, token))
        if url != _EXPECTED_URL:
            raise AssertionError(f"requested {url!r}, expected {_EXPECTED_URL!r}")
        return types_payload

    _http_get.calls = calls  # type: ignore[attr-defined]
    return _http_get


def test_fetch_availability_happy_path() -> None:
    fake = _make_http_get(_FAKE_SERVER_TYPES)
    result = fetch_availability("token-abc", http_get=fake)
    # hel1 is listed by all three fixture types and available at none, so it
    # is present and empty — see the test below for why that matters.
    assert result == {"fsn1": {"cx43", "ccx33"}, "nbg1": {"ccx33"}, "hel1": set()}
    assert all(token == "token-abc" for _url, token in fake.calls)
    # ONE call now. The second one went to /v1/datacenters, which Hetzner
    # removed on 2026-10-01; the availability it carried moved into each
    # server type's own `locations` array.
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == _EXPECTED_URL


def test_fetch_availability_keeps_locations_that_have_nothing_available() -> None:
    """A real location with no capacity must stay in the map, as an empty set.

    Dropping it is not equivalent: downstream, a location missing from the
    map means UNKNOWN, and `render_status_lines` prints
    `? (unknown location)` — which is wrong for a location Hetzner lists
    and simply has no capacity at. Present-but-empty prints `✗`.
    """
    result = fetch_availability("t", http_get=_make_http_get(_FAKE_SERVER_TYPES))
    assert result["hel1"] == set()


def test_unavailable_location_renders_as_a_cross_not_as_unknown() -> None:
    """The consequence of the test above, pinned where an operator sees it.

    A dict-shape assertion alone does not catch this: both shapes look
    plausible until you render them.
    """
    availability = fetch_availability("t", http_get=_make_http_get(_FAKE_SERVER_TYPES))
    prefs = parse_preferences("cx43:hel1,cx43:fsn1")
    lines = render_status_lines(prefs, availability, select(prefs, availability))

    assert "✗ 1. cx43:hel1" in lines[0], lines
    assert "unknown location" not in lines[0], lines


def test_fetch_availability_unions_types_across_one_location() -> None:
    """Two types available at the same location land in one set."""
    result = fetch_availability("t", http_get=_make_http_get(_FAKE_SERVER_TYPES))
    assert result["fsn1"] == {"cx43", "ccx33"}


def test_fetch_availability_rejects_empty_token() -> None:
    """Don't even make the call without a token — saves a guaranteed
    401 round-trip and gives a more specific error."""
    with pytest.raises(HetznerCapacityError, match="HCLOUD_TOKEN not set"):
        fetch_availability("")


def test_fetch_availability_raises_on_missing_server_types_field() -> None:
    fake = _make_http_get({"unexpected": []})
    with pytest.raises(HetznerCapacityError, match="server_types"):
        fetch_availability("t", http_get=fake)


def test_fetch_availability_skips_malformed_entries() -> None:
    """Junk in the catalogue must not take the deploy down with it.

    Each entry below is a different shape the parser has to survive, and
    the one good type still has to come through.
    """
    payload = {
        "server_types": [
            "not-a-dict",
            {"name": 42, "locations": [{"name": "fsn1", "available": True}]},  # name not a str
            {"id": 7, "locations": [{"name": "fsn1", "available": True}]},  # no name
            {"name": "nolocs"},  # locations missing entirely
            {"name": "nullocs", "locations": None},  # locations not a list
            {"name": "junklocs", "locations": ["x", 3, None]},  # entries not dicts
            {"name": "noname", "locations": [{"available": True}]},  # location has no name
            {"name": "badname", "locations": [{"name": 9, "available": True}]},
            {"name": "good", "locations": [{"name": "FSN1", "available": True}]},
        ],
    }
    result = fetch_availability("t", http_get=_make_http_get(payload))
    assert result["fsn1"] == {"good"}


def test_fetch_availability_treats_only_true_as_available() -> None:
    """`available` is a bool in the API. A schema change that turned it
    into a truthy string would otherwise mark every location available —
    which fails at `tofu apply` instead of at selection, where the
    operator can still read the reason.
    """
    payload = {
        "server_types": [
            {"name": "yes", "locations": [{"name": "fsn1", "available": True}]},
            {"name": "str", "locations": [{"name": "fsn1", "available": "true"}]},
            {"name": "one", "locations": [{"name": "fsn1", "available": 1}]},
            {"name": "no", "locations": [{"name": "fsn1", "available": False}]},
            {"name": "absent", "locations": [{"name": "fsn1"}]},
        ],
    }
    assert fetch_availability("t", http_get=_make_http_get(payload))["fsn1"] == {"yes"}


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
        hetzner_capacity._default_http_get("https://example/v1/x", "t")


def test_default_http_get_wraps_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS / connection failure → HetznerCapacityError with class name."""
    import urllib.error

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"URLError"):
        hetzner_capacity._default_http_get("https://api.hetzner.cloud/v1/server_types", "t")


def test_default_http_get_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Socket timeout (TimeoutError subclass of OSError on modern Py)
    → HetznerCapacityError. Don't surface the raw exception at the CLI."""

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        raise TimeoutError("read timeout after 30s")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"TimeoutError|read timeout"):
        hetzner_capacity._default_http_get("https://api.hetzner.cloud/v1/server_types", "t")


def test_default_http_get_wraps_non_utf8_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR #537 R6 #4: a misconfigured upstream proxy serving binary
    garbage on what should be JSON would have escaped as an uncaught
    UnicodeDecodeError. Now wrapped into HetznerCapacityError so the
    CLI handler sees the same single error class as every other
    failure mode."""

    # 0x80 is invalid as the start of a UTF-8 sequence.
    bad_bytes = b"\x80\x81\x82 not utf-8"

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        return _FakeUrlopenContext(bad_bytes)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"non-UTF-8"):
        hetzner_capacity._default_http_get("https://api.hetzner.cloud/v1/server_types", "t")


def test_default_http_get_wraps_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Body parses to non-JSON → HetznerCapacityError with parser detail.
    Defensive against an upstream proxy that intercepts and serves an
    HTML error page on what should have been a JSON response."""

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeUrlopenContext:
        return _FakeUrlopenContext(b"<html>500 Internal Server Error</html>")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(HetznerCapacityError, match=r"non-JSON"):
        hetzner_capacity._default_http_get("https://api.hetzner.cloud/v1/server_types", "t")


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
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK)
    types = fetch_server_types("t", http_get=fake)
    assert types["cx43"] == ServerTypeInfo(name="cx43", disk_gb=160, architecture="x86")
    assert types["cax31"].architecture == "arm"


def test_fetch_server_types_rejects_empty_token() -> None:
    with pytest.raises(HetznerCapacityError, match="HCLOUD_TOKEN not set"):
        fetch_server_types("")


def test_fetch_server_types_raises_on_schema_drift() -> None:
    fake = _make_http_get({"nope": []})
    with pytest.raises(HetznerCapacityError, match="missing 'server_types' list"):
        fetch_server_types("t", http_get=fake)


def test_fetch_server_types_skips_malformed_entries() -> None:
    fake = _make_http_get(
        {"server_types": [{"id": 1, "name": "cx43", "disk": 160}, {"id": 2}, "junk"]}
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
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK)
    types = fetch_server_types("t", http_get=fake)
    prefs = parse_preferences("cx43:fsn1, cpx42:fsn1, cx53:fsn1")
    kept, excluded = filter_specs(prefs, types, min_disk_gb=240)
    assert [str(s) for s in kept] == ["cpx42:fsn1", "cx53:fsn1"]
    assert "disk 160GB < 240GB required" in excluded[ServerSpec("cx43", "fsn1")]


def test_filter_specs_drops_mismatched_architecture() -> None:
    fake = _make_http_get(_FAKE_TYPES_WITH_DISK)
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


# ---------------------------------------------------------------------------
# The error detail — added after an outage where five causes printed one line
# ---------------------------------------------------------------------------


def test_error_detail_names_the_status_and_the_path() -> None:
    """An HTTP failure has to say WHICH status and WHICH endpoint.

    This is the case that cost an afternoon: Hetzner removed the
    datacenter endpoints on 2026-10-01, every spin-up failed, and the CLI
    printed only `(HetznerCapacityError)` — the same line a missing token
    or a timeout produces.
    """
    url = "https://api.hetzner.cloud/v1/datacenters?per_page=50"
    with (
        mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url=url,
                code=410,
                msg="Gone",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            ),
        ),
        pytest.raises(HetznerCapacityError) as excinfo,
    ):
        hetzner_capacity._default_http_get(url, "t")

    assert excinfo.value.detail == "HTTP 410 from /datacenters"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (urllib.error.URLError("boom"), "URLError reaching /server_types"),
        (TimeoutError("timed out"), "TimeoutError reaching /server_types"),
    ],
)
def test_error_detail_names_the_failure_class_for_network_errors(
    exc: Exception, expected: str
) -> None:
    url = "https://api.hetzner.cloud/v1/server_types?per_page=200"
    with (
        mock.patch("urllib.request.urlopen", side_effect=exc),
        pytest.raises(HetznerCapacityError) as excinfo,
    ):
        hetzner_capacity._default_http_get(url, "t")

    assert excinfo.value.detail == expected


def test_error_detail_carries_nothing_from_the_response_body() -> None:
    """`str(exc)` may quote upstream text; `detail` may not — that is the
    whole reason they are separate fields. The CLI prints only `detail`."""
    url = "https://api.hetzner.cloud/v1/server_types?per_page=200"
    body = b"SECRET-UPSTREAM-TEXT-THAT-MUST-NOT-BE-PRINTED \xff\xfe"
    with (
        mock.patch("urllib.request.urlopen", return_value=_FakeUrlopenContext(body)),
        pytest.raises(HetznerCapacityError) as excinfo,
    ):
        hetzner_capacity._default_http_get(url, "t")

    assert "SECRET-UPSTREAM-TEXT" not in (excinfo.value.detail or "")
    assert excinfo.value.detail == "non-UTF-8 body from /server_types"


def test_every_raise_site_sets_a_detail() -> None:
    """Stated as a rule, not a list: a `detail=None` would fall back to the
    bare class name and reintroduce exactly the blindness this fixes."""
    source = pathlib.Path(hetzner_capacity.__file__).read_text(encoding="utf-8")

    raises = re.findall(r"raise HetznerCapacityError\((.*?)\)\s*(?:from exc)?\n", source, re.S)
    assert raises, "no raise sites found — the regex no longer matches"
    for site in raises:
        assert "detail=" in site, f"raise without a detail: {site.strip()[:70]}"


def test_fetch_availability_survives_a_non_list_locations_field() -> None:
    """A truthy non-list used to raise TypeError out of this function.

    `_select_capacity` catches only `HetznerCapacityError`, so the CLI
    printed a traceback instead of a message and an exit code — which is
    the opposite of what the module's schema-drift posture promises.
    """
    payload = {
        "server_types": [
            {"name": "broken", "locations": 5},
            {"name": "alsobroken", "locations": "abc"},
            {"name": "mapping", "locations": {"fsn1": True}},
            {"name": "good", "locations": [{"name": "fsn1", "available": True}]},
        ],
    }
    assert fetch_availability("t", http_get=_make_http_get(payload)) == {"fsn1": {"good"}}


@pytest.mark.parametrize("locations", [5, "abc", {"fsn1": True}, None])
def test_fetch_availability_raises_when_nothing_parses(locations: Any) -> None:
    """A non-empty catalogue yielding no locations at all is schema drift,
    not a capacity state — every real type lists the locations it is
    offered in, available or not.

    Reporting it as "nothing in stock anywhere" would send the operator
    looking for a Hetzner outage that is not happening.
    """
    payload = {"server_types": [{"name": "x", "locations": locations}]}
    with pytest.raises(HetznerCapacityError) as excinfo:
        fetch_availability("t", http_get=_make_http_get(payload))

    assert excinfo.value.detail == "/v1/server_types had no parseable 'locations'"


def test_the_fake_rejects_a_malformed_server_types_path() -> None:
    """Guards the guard: a substring match would have accepted
    `/v1/server_types/invalid` and hidden a broken request path."""
    fake = _make_http_get(_FAKE_SERVER_TYPES)
    with pytest.raises(AssertionError, match="expected"):
        fake("https://api.hetzner.cloud/v1/server_types/invalid", "t")

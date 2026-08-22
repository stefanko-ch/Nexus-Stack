"""Tests for the ``select-capacity`` CLI handler (Issue #536).

These tests cover the small wrapper in ``nexus_deploy.__main__`` that
glues :mod:`nexus_deploy.hetzner_capacity` to the workflow:

- preference resolution (env > config.tfvars key > legacy single-pair >
  built-in default)
- HCLOUD_TOKEN missing → soft-skip with stderr warning + rc=0
- All preferences out of stock → rc=2 with per-pair status block
- Successful selection → rewrites ``server_type`` + ``server_location``
  in config.tfvars while preserving other lines / inline comments

The Hetzner API is stubbed via ``monkeypatch`` of
``hetzner_capacity.fetch_availability`` so the tests do not require
network access or a token.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus_deploy import hetzner_capacity as _hetzner
from nexus_deploy.__main__ import _select_capacity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_capacity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop the test runner's own env from bleeding into handler runs.
    HCLOUD_TOKEN may be set on the developer's shell; SERVER_PREFERENCES
    almost certainly isn't, but clear both for hermeticity."""
    monkeypatch.delenv("HCLOUD_TOKEN", raising=False)
    monkeypatch.delenv("TF_VAR_hcloud_token", raising=False)
    monkeypatch.delenv("SERVER_PREFERENCES", raising=False)


@pytest.fixture
def tfvars_with_legacy_pair(tmp_path: Path) -> Path:
    """Mimics today's machine-generated config.tfvars: server_type +
    server_location set as the only capacity-related lines."""
    path = tmp_path / "config.tfvars"
    path.write_text(
        'server_type     = "cx43"\n'
        'server_location = "hel1"\n'
        'server_image    = "ubuntu-24.04"\n'
        'domain          = "example.com"\n',
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------


def test_select_capacity_requires_tfvars_arg(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _select_capacity([])
    assert rc == 2
    assert "--tfvars PATH is required" in capsys.readouterr().err


def test_select_capacity_rejects_unknown_arg(
    tfvars_with_legacy_pair: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _select_capacity(["--bogus", "x", "--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    assert "unknown arg" in capsys.readouterr().err


def test_select_capacity_aborts_when_tfvars_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _select_capacity(["--tfvars", str(tmp_path / "does-not-exist.tfvars")])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_select_capacity_rejects_tfvars_without_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PR #537 R1 #2: ``--tfvars`` as the last token (no value) used
    to bottom-out in the generic ``unknown arg '--tfvars'`` branch.
    Now produces a specific error so the operator knows what's wrong."""
    rc = _select_capacity(["--tfvars"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--tfvars requires a value" in err


# ---------------------------------------------------------------------------
# Soft-skip when no token
# ---------------------------------------------------------------------------


def test_select_capacity_skips_when_no_token(
    tfvars_with_legacy_pair: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Local-dev / CI dry-run without HCLOUD_TOKEN must not abort —
    capacity selection is opportunistic. Returns 0 + stderr warning."""
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "HCLOUD_TOKEN not set" in err
    assert "skipping capacity check" in err
    # config.tfvars must NOT have been rewritten.
    assert tfvars_with_legacy_pair.read_text().count("cx43") == 1


# ---------------------------------------------------------------------------
# Preference source priority
# ---------------------------------------------------------------------------


def test_select_capacity_uses_server_preferences_env_var(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SERVER_PREFERENCES env var has highest priority — overrides
    both config.tfvars's key and the legacy single-pair shorthand."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "ccx33:nbg1, cx43:fsn1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"nbg1": {"ccx33"}, "fsn1": {"cx43"}},
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 0
    rewritten = tfvars_with_legacy_pair.read_text()
    # First in env-list, available → picked. The rewrite preserves
    # the original ``server_type     =`` spacing from the fixture.
    assert 'server_type     = "ccx33"' in rewritten
    assert 'server_location = "nbg1"' in rewritten
    err = capsys.readouterr().err
    assert "chose ccx33:nbg1" in err


def test_select_capacity_uses_server_preferences_from_tfvars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When SERVER_PREFERENCES env is empty, the
    ``server_preferences = "..."`` line in config.tfvars is used."""
    path = tmp_path / "config.tfvars"
    path.write_text(
        'server_preferences = "cx43:fsn1, ccx33:hel1"\n'
        'server_type        = "cx43"\n'
        'server_location    = "hel1"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": set(), "hel1": {"ccx33"}},
    )
    rc = _select_capacity(["--tfvars", str(path)])
    assert rc == 0
    rewritten = path.read_text()
    # cx43:fsn1 unavailable → fallback to ccx33:hel1.
    # Fixture used ``server_type        =`` spacing → rewrite preserves it.
    assert 'server_type        = "ccx33"' in rewritten
    assert 'server_location    = "hel1"' in rewritten


def test_select_capacity_strips_whitespace_in_legacy_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #537 R8 #3: a hand-edited config.tfvars with whitespace
    INSIDE the quoted value (``server_location = "hel1 "``) used to
    produce a ServerSpec with location='hel1 ' that never matched
    the Hetzner availability keys → confusing 'unknown location'
    error. Now ``_read_single_pair_from_tfvars`` strips before
    lowercasing, so the lookup succeeds."""
    path = tmp_path / "config.tfvars"
    path.write_text(
        'server_type = " cx43 "\nserver_location = "hel1 "\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"hel1": {"cx43"}},
    )
    rc = _select_capacity(["--tfvars", str(path)])
    assert rc == 0


def test_select_capacity_legacy_pair_appends_defaults(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator with only ``server_type`` + ``server_location`` set
    (the pre-#536 shorthand): the pair is used as the FIRST preference,
    then ``DEFAULT_PREFERENCES`` is appended as fallback (dedup'd).

    Previously this branch produced a 1-element preference list with
    no fallback — a single sold-out region for the class-configured
    type aborted the whole spin-up. The current behaviour transparently
    falls through to the next tier/region, which is what every
    realistic class-config caller actually wants."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"hel1": {"cx43"}},
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "legacy single-pair shorthand" in err
    assert "cx43:hel1" in err
    # The new "primary + DEFAULT fallback" branch announces the total
    # entry count so the operator knows the legacy pair isn't on its
    # own — that wording is part of the contract.
    assert "DEFAULT_PREFERENCES as fallback" in err


def test_select_capacity_legacy_pair_falls_through_when_primary_oos(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the legacy class-config pair is sold out, the appended
    DEFAULT_PREFERENCES list keeps the spin-up working.

    Regression test for the mid-2026-05 incident where a 16-user class
    with ``cx43:hel1`` configured all failed simultaneously during
    Hetzner EU peak — every stack aborted at "out of stock" despite
    cx53 / cpx42 / cpx52 having ample capacity. The fixture marks
    cx43:hel1 unavailable but cx53:hel1 available; the walk must pick
    cx53:hel1 rather than abort."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        # cx43:hel1 (the class-configured legacy pair) is OOS;
        # cx53:hel1 (Tier 2 of DEFAULT_PREFERENCES) is available.
        lambda _t, http_get=None: {"hel1": {"cx53"}, "fsn1": set(), "nbg1": set()},
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "chose cx53:hel1" in err
    # The rewrite must update both lines in config.tfvars, not just
    # one. The operator's view post-deploy should match what tofu
    # actually provisioned.
    rewritten = tfvars_with_legacy_pair.read_text()
    assert 'server_type     = "cx53"' in rewritten
    assert 'server_location = "hel1"' in rewritten


def test_select_capacity_uses_default_when_nothing_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bare config.tfvars (no server_type / server_location /
    server_preferences) → fall back to the in-code default list."""
    path = tmp_path / "config.tfvars"
    path.write_text('domain = "example.com"\n', encoding="utf-8")
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": {"cx43"}},
    )
    rc = _select_capacity(["--tfvars", str(path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "built-in default list" in err
    rewritten = path.read_text()
    # First *available* default pair given the mocked availability:
    # the actual default list starts with cx43:hel1, but the stub
    # only marks cx43 available at fsn1, so the walk falls through
    # past hel1 (unknown location) and picks fsn1. This pins the
    # full preference-walk path even when the head of the list is
    # absent from the API response. (PR #537 R4 #6 — comment fixed.)
    assert 'server_type = "cx43"' in rewritten
    assert 'server_location = "fsn1"' in rewritten


# ---------------------------------------------------------------------------
# Selection outcomes
# ---------------------------------------------------------------------------


def test_select_capacity_aborts_when_all_unavailable(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every preference out of stock → rc=2 with per-pair status
    block + actionable suggestion."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:fsn1, cx43:nbg1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": set(), "nbg1": set()},
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "every preference is out of stock" in err
    assert "✗ 1. cx43:fsn1" in err
    assert "✗ 2. cx43:nbg1" in err
    # Assert against the full Hetzner Console URL rather than the bare
    # hostname — same intent (verify the operator-facing pointer is
    # in the log) but more specific. Defensive against CodeQL's
    # py/incomplete-url-substring-sanitization rule, which flags
    # bare-domain matches as a class even in test assertions
    # (false-positive context — this is log-content verification,
    # not URL validation). Replaced radar.iodev.org with console.hetzner.cloud
    # in 2026-05: the third-party tracker started bot-blocking
    # (HTTP 403 to non-browser requests) and operators couldn't
    # always reach it, while the official Hetzner Console always
    # works for any operator who already has an HCLOUD_TOKEN.
    assert "https://console.hetzner.cloud/" in err
    # Original file MUST stay untouched on failure.
    assert 'server_type     = "cx43"' in tfvars_with_legacy_pair.read_text()


def test_select_capacity_diagnoses_all_unknown_locations(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PR #537 R7 #1: when every preference targets a location that
    isn't in Hetzner's response (operator typo), the failure message
    points at the typo instead of the misleading 'out of stock'
    guidance. Different operator action: fix the name, not widen
    the list."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:atlantis, cx43:lemuria")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": {"cx43"}, "hel1": {"cx43"}},
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "none of the preferred locations are known" in err
    # The per-pair block uses the ? marker + suffix.
    assert "? 1. cx43:atlantis (unknown location)" in err
    assert "? 2. cx43:lemuria (unknown location)" in err
    # Operator-actionable hint about Hetzner location-name shape.
    assert "lowercase like fsn1" in err


def test_select_capacity_keeps_oos_message_when_only_some_are_unknown(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the list MIXES unknown locations and genuine out-of-stock
    pairs, the dominant operator action is still 'widen / wait' (the
    typo entry is one of several, not the only thing wrong). Per-pair
    block tells the operator which is which via ? vs ✗ markers."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:atlantis, cx43:fsn1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": {"ccx33"}},  # cx43 sold out
    )
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    err = capsys.readouterr().err
    # Falls back to the generic "out of stock" message (mixed case).
    assert "every preference is out of stock" in err
    # Per-pair block still differentiates the two cases.
    assert "? 1. cx43:atlantis (unknown location)" in err
    assert "✗ 2. cx43:fsn1" in err


def test_select_capacity_aborts_on_api_error(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HetznerCapacityError (HTTP 401, network error, schema drift)
    propagates to rc=2, reported by TYPE rather than by message.

    This assertion was inverted in PR #651: it previously required the
    exception text to appear. That contradicted the project rule
    (CLAUDE.md, and the src/nexus_deploy path instructions) that error
    logs carry `type(exc).__name__` and never `str(exc)`, because
    exception messages embed upstream response bodies.

    The trade-off is real and worth naming: HetznerCapacityError covers
    auth, network, timeout and schema drift alike, so the log no longer
    distinguishes them. The rule prefers that over the chance of a
    credential reaching a public build log.
    """
    monkeypatch.setenv("HCLOUD_TOKEN", "t")

    def _raise(_token: str, http_get: object = None) -> dict[str, set[str]]:
        raise _hetzner.HetznerCapacityError("HTTP 401: Unauthorized")

    monkeypatch.setattr(_hetzner, "fetch_availability", _raise)
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Hetzner API failure" in err
    assert "HetznerCapacityError" in err
    assert "HTTP 401" not in err


def test_select_capacity_aborts_on_invalid_preferences(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator typo in SERVER_PREFERENCES → rc=2 with parse error."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43, fsn1")  # missing colon
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 2
    assert "exactly one ':' separator" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# tfvars rewrite mechanics
# ---------------------------------------------------------------------------


def test_select_capacity_preserves_other_tfvars_lines(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ``server_type`` + ``server_location`` may be touched;
    ``server_image`` / ``domain`` etc. must round-trip unchanged."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "ccx33:fsn1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": {"ccx33"}},
    )
    _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    rewritten = tfvars_with_legacy_pair.read_text()
    assert 'server_image    = "ubuntu-24.04"' in rewritten
    assert 'domain          = "example.com"' in rewritten


def test_select_capacity_preserves_trailing_inline_comments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #537 R1 #1: hand-edited tfvars often have inline comments
    after the value (``server_type = "cx43" # primary``). The rewrite
    must NOT silently delete them — re-emit the captured trail."""
    path = tmp_path / "config.tfvars"
    path.write_text(
        'server_type = "cx43" # primary instance class\n'
        'server_location = "hel1"  // hel1 was first in the list\n'
        'server_image = "ubuntu-24.04"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "ccx33:fsn1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": {"ccx33"}},
    )
    rc = _select_capacity(["--tfvars", str(path)])
    assert rc == 0
    rewritten = path.read_text()
    # New value, comment preserved.
    assert 'server_type = "ccx33" # primary instance class' in rewritten
    assert 'server_location = "fsn1"  // hel1 was first in the list' in rewritten


def test_select_capacity_strips_token_whitespace(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #537 R1 #3: ``HCLOUD_TOKEN`` sourced from a file may carry a
    trailing newline. The handler must ``.strip()`` before forwarding
    to ``fetch_availability`` so the Bearer header doesn't get
    corrupted (HTTP 401 with a confusing root cause)."""
    monkeypatch.setenv("HCLOUD_TOKEN", "  token-with-whitespace  \n")
    captured: dict[str, str] = {}

    def _capture_token(token: str, http_get: object = None) -> dict[str, set[str]]:
        captured["token"] = token
        return {"hel1": {"cx43"}}

    monkeypatch.setattr(_hetzner, "fetch_availability", _capture_token)
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)])
    assert rc == 0
    assert captured["token"] == "token-with-whitespace"


def test_select_capacity_appends_keys_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When config.tfvars only has ``server_preferences`` (no legacy
    pair lines), the rewrite APPENDS server_type + server_location
    so ``tofu apply`` has values to consume."""
    path = tmp_path / "config.tfvars"
    path.write_text(
        'server_preferences = "cx43:fsn1, ccx33:nbg1"\ndomain = "example.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"fsn1": set(), "nbg1": {"ccx33"}},
    )
    rc = _select_capacity(["--tfvars", str(path)])
    assert rc == 0
    rewritten = path.read_text()
    assert 'server_type = "ccx33"' in rewritten
    assert 'server_location = "nbg1"' in rewritten
    # Original lines preserved.
    assert 'domain = "example.com"' in rewritten
    assert 'server_preferences = "cx43:fsn1, ccx33:nbg1"' in rewritten


# ---------------------------------------------------------------------------
# Restore constraints: --min-disk-gb / --arch  (PR #651 review)
#
# These flags existed as module functions with full coverage while the CLI
# rejected them outright with "unknown arg". Every snapshot restore would
# have failed at the capacity step. The module tests could not catch it
# because they call filter_specs directly; only a CLI-level test does.
# ---------------------------------------------------------------------------


_TYPES = {
    "cx43": _hetzner.ServerTypeInfo(name="cx43", disk_gb=160, architecture="x86"),
    "cx53": _hetzner.ServerTypeInfo(name="cx53", disk_gb=320, architecture="x86"),
    "cax31": _hetzner.ServerTypeInfo(name="cax31", disk_gb=160, architecture="arm"),
}


def test_min_disk_gb_flag_is_accepted(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression guard: this used to exit 2 with 'unknown arg'."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:hel1, cx53:hel1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"hel1": {"cx43", "cx53"}},
    )
    monkeypatch.setattr(_hetzner, "fetch_server_types", lambda _t, http_get=None: _TYPES)

    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", "320"])
    assert rc == 0
    # cx43 has a 160GB disk and cannot host a 320GB image, so the walk
    # must skip it even though it is first and in stock.
    assert 'server_type     = "cx53"' in tfvars_with_legacy_pair.read_text()


def test_arch_flag_excludes_mismatched_architecture(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cax31:hel1, cx43:hel1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"hel1": {"cax31", "cx43"}},
    )
    monkeypatch.setattr(_hetzner, "fetch_server_types", lambda _t, http_get=None: _TYPES)

    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--arch", "x86"])
    assert rc == 0
    assert 'server_type     = "cx43"' in tfvars_with_legacy_pair.read_text()


def test_all_preferences_excluded_is_rc2(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No type can host the image: fail with an actionable message rather
    than letting `tofu apply` surface it as an opaque image error."""
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:hel1")
    monkeypatch.setattr(
        _hetzner, "fetch_availability", lambda _t, http_get=None: {"hel1": {"cx43"}}
    )
    monkeypatch.setattr(_hetzner, "fetch_server_types", lambda _t, http_get=None: _TYPES)

    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", "999"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "every preference was excluded" in err
    assert "force_fresh" in err


def test_constraint_flags_are_optional(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without them, fetch_server_types must not even be called — the
    legacy path stays a single API round-trip."""
    called = {"n": 0}

    def _boom(*_a: object, **_k: object) -> dict[str, object]:
        called["n"] += 1
        return {}

    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setattr(
        _hetzner, "fetch_availability", lambda _t, http_get=None: {"hel1": {"cx43"}}
    )
    monkeypatch.setattr(_hetzner, "fetch_server_types", _boom)

    assert _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)]) == 0
    assert called["n"] == 0


def test_min_disk_gb_rejects_non_integer(tfvars_with_legacy_pair: Path) -> None:
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", "lots"])
    assert rc == 2


@pytest.mark.parametrize("flag", ["--min-disk-gb", "--arch"])
def test_constraint_flag_without_value_is_rc2(
    tfvars_with_legacy_pair: Path,
    flag: str,
) -> None:
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), flag])
    assert rc == 2


def test_excluded_preferences_appear_in_the_status_block(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The status block must show WHY a tier was skipped.

    render_status_lines iterates whatever list it is handed, so passing
    it the post-filter tuple silently drops every excluded entry and the
    ⊘ marker can never appear — leaving an operator debugging a failed
    restore with no indication that disk size was the reason. This is the
    integration the module-level render test cannot cover, because that
    one passes the excluded spec in directly.
    """
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:hel1, cx53:hel1")
    monkeypatch.setattr(
        _hetzner,
        "fetch_availability",
        lambda _t, http_get=None: {"hel1": {"cx43", "cx53"}},
    )
    monkeypatch.setattr(_hetzner, "fetch_server_types", lambda _t, http_get=None: _TYPES)

    assert _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", "320"]) == 0

    err = capsys.readouterr().err
    assert "⊘" in err
    assert "cx43:hel1" in err
    assert "disk 160GB < 320GB required" in err
    # And the count must describe the original list, not the survivors.
    assert "excluded 1 of 2 preferences" in err


@pytest.mark.parametrize("value", ["0", "-1"])
def test_min_disk_gb_rejects_non_positive(
    tfvars_with_legacy_pair: Path,
    value: str,
) -> None:
    """Zero and negatives must be refused, not tolerated.

    The filter is gated on `min_disk_gb > 0`, so accepting these would
    silently disable the disk check instead of applying it. It is
    reachable: a snapshot whose `disk_size` is missing parses as 0 and
    reaches the CLI through SNAPSHOT_DISK_GB, and the restore would then
    pick a target that cannot host the image.
    """
    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", value])
    assert rc == 2


def test_api_failure_does_not_log_exception_text(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the exception type reaches stderr.

    HetznerCapacityError messages embed the upstream response body, which
    is text we do not control. Per CLAUDE.md and the src/nexus_deploy
    path instructions, error logs carry `type(exc).__name__`, never
    `str(exc)`.
    """
    monkeypatch.setenv("HCLOUD_TOKEN", "t")

    def _raise(*_a: object, **_k: object) -> dict[str, set[str]]:
        raise _hetzner.HetznerCapacityError("HTTP 401 for https://api — token=SUPERSECRET")

    monkeypatch.setattr(_hetzner, "fetch_availability", _raise)

    assert _select_capacity(["--tfvars", str(tfvars_with_legacy_pair)]) == 2
    out = capsys.readouterr()
    combined = out.err + out.out
    assert "HetznerCapacityError" in combined
    assert "SUPERSECRET" not in combined


def test_server_types_failure_does_not_log_exception_text(
    tfvars_with_legacy_pair: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The second API call needs the same guarantee as the first.

    The `str(exc)` fix covered fetch_availability; fetch_server_types is
    only reached on the snapshot path and had no test of its own. It is
    the more exposed of the two, since it is the call the restore
    constraints depend on.
    """
    monkeypatch.setenv("HCLOUD_TOKEN", "t")
    monkeypatch.setenv("SERVER_PREFERENCES", "cx43:hel1")
    monkeypatch.setattr(
        _hetzner, "fetch_availability", lambda _t, http_get=None: {"hel1": {"cx43"}}
    )

    def _raise(*_a: object, **_k: object) -> dict[str, object]:
        raise _hetzner.HetznerCapacityError("HTTP 401 for https://api — token=SUPERSECRET")

    monkeypatch.setattr(_hetzner, "fetch_server_types", _raise)

    rc = _select_capacity(["--tfvars", str(tfvars_with_legacy_pair), "--min-disk-gb", "320"])
    assert rc == 2
    out = capsys.readouterr()
    combined = out.err + out.out
    assert "HetznerCapacityError" in combined
    assert "SUPERSECRET" not in combined
    assert "HTTP 401" not in combined

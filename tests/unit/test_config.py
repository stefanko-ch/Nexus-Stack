"""Tests for nexus_deploy.config.

Covers:
- pure-data parsing (`from_secrets_json`)
- subprocess-shelling parsing (`from_tofu_output`)
- bash-eval-safe rendering (`dump_shell`) plus snapshot
- hypothesis property roundtrip via real bash eval
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from nexus_deploy.config import _FIELDS, ConfigError, NexusConfig

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_field_count() -> None:
    """The single-source-of-truth tuple has the right field count.

    Pinning the count guards against accidental field drops or
    silent drift between :data:`_FIELDS` and the upstream tofu
    schema.
    """
    assert len(_FIELDS) == 95


def test_no_duplicate_bash_var_names() -> None:
    bash_vars = [b for b, _, _ in _FIELDS]
    assert len(bash_vars) == len(set(bash_vars))


def test_no_duplicate_json_keys() -> None:
    json_keys = [k for _, k, _ in _FIELDS]
    assert len(json_keys) == len(set(json_keys))


# ---------------------------------------------------------------------------
# from_secrets_json
# ---------------------------------------------------------------------------


def test_from_secrets_json_full() -> None:
    raw = (FIXTURES / "secrets_full.json").read_text()
    config = NexusConfig.from_secrets_json(raw)
    payload = json.loads(raw)
    for json_key in payload:
        assert getattr(config, json_key) == payload[json_key], json_key


def test_from_secrets_json_empty() -> None:
    config = NexusConfig.from_secrets_json("{}")
    for _, json_key, _ in _FIELDS:
        assert getattr(config, json_key) is None, json_key


def test_from_secrets_json_partial() -> None:
    raw = (FIXTURES / "secrets_minimal.json").read_text()
    config = NexusConfig.from_secrets_json(raw)
    assert config.admin_username == "nexus"
    assert config.kestra_admin_password == "minimal-kestra-pw"
    assert config.dify_admin_password is None  # not in fixture


def test_invalid_json_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="not valid JSON"):
        NexusConfig.from_secrets_json("not-json")


def test_non_object_json_raises_clear_error() -> None:
    for non_object in ("[]", "42", '"string"', "true", "null"):
        with pytest.raises(ConfigError, match="must be a JSON object"):
            NexusConfig.from_secrets_json(non_object)


def test_extra_unknown_field_is_ignored() -> None:
    """A new tofu output key that nexus_deploy doesn't know yet must not break."""
    config = NexusConfig.from_secrets_json('{"future_unknown_field": "ignore-me"}')
    assert not hasattr(config, "future_unknown_field")


# ---------------------------------------------------------------------------
# dump_shell — value semantics
# ---------------------------------------------------------------------------


def _parse_dump(rendered: str) -> dict[str, str]:
    """Run `bash -c 'eval ...; printenv'` and return the parsed env subset."""
    bash_vars = [b for b, _, _ in _FIELDS]
    # `printenv VAR` prints the value or nothing if unset; we wrap each
    # in `printf '%s\0' "VAR=$VAR"` so we can re-parse unambiguously
    # even when values contain newlines or special chars.
    printer = "; ".join(f'printf "%s\\0" "{v}=${v}"' for v in bash_vars)
    completed = subprocess.run(
        ["bash", "-c", f"{rendered}\n{printer}"],
        check=True,
        capture_output=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    out: dict[str, str] = {}
    for chunk in completed.stdout.split(b"\0"):
        if not chunk:
            continue
        text = chunk.decode()
        name, _, value = text.partition("=")
        out[name] = value
    return out


def test_dump_shell_emits_all_fields() -> None:
    config = NexusConfig.from_secrets_json("{}")
    rendered = config.dump_shell()
    for bash_var, _, _ in _FIELDS:
        assert f"{bash_var}=" in rendered


def test_dump_shell_admin_username_default_is_admin() -> None:
    """When SECRETS_JSON is ``{}`` the per-field fallback fires —
    ``ADMIN_USERNAME`` defaults to ``admin``.

    The tofu-default may also produce a different value when
    ``tofu output`` lands a populated SECRETS_JSON; the per-field
    fallback only kicks in for the missing/empty case.
    """
    config = NexusConfig.from_secrets_json("{}")
    parsed = _parse_dump(config.dump_shell())
    assert parsed["ADMIN_USERNAME"] == "admin"


def test_dump_shell_external_s3_fallbacks() -> None:
    config = NexusConfig.from_secrets_json("{}")
    parsed = _parse_dump(config.dump_shell())
    assert parsed["EXTERNAL_S3_LABEL"] == "External Storage"
    assert parsed["EXTERNAL_S3_REGION"] == "auto"


def test_dump_shell_empty_string_treated_as_missing() -> None:
    """Both `null` and `""` must trigger the per-field fallback.

    Downstream consumers test ``[ -n "$VAR" ]`` and treat "" the
    same as unset, so an empty-string value should fire the
    per-field fallback exactly like ``null`` / missing key.
    """
    config = NexusConfig.from_secrets_json('{"external_s3_label": ""}')
    parsed = _parse_dump(config.dump_shell())
    assert parsed["EXTERNAL_S3_LABEL"] == "External Storage"


def test_dump_shell_eval_injection_safe(tmp_path: Path) -> None:
    """Adversarial values must NOT execute when the output is bash-eval'd.

    The dump-shell output is consumed via ``eval``, which introduces
    a command-execution surface. shlex.quote in
    :meth:`NexusConfig.dump_shell` is what keeps that path safe:
    this test proves it by feeding payloads that WOULD execute
    under naive concatenation (``$(touch …)``, backticks, ``;``
    injection) and asserting that nothing materialises in a
    per-test canary dir.

    Marker files target ``tmp_path`` (a per-test pytest tmpdir) plus a
    unique ``NEXUS_DEPLOY_INJECT_*`` prefix so a stray glob can't ever
    match unrelated files on a shared workstation.
    """
    canary_dir = tmp_path / "canaries"
    canary_dir.mkdir()
    payload_dir = shlex.quote(str(canary_dir))
    raw = json.dumps(
        {
            "kestra_admin_password": f"$(touch {payload_dir}/NEXUS_DEPLOY_INJECT_dollar)",
            "infisical_admin_password": f"`touch {payload_dir}/NEXUS_DEPLOY_INJECT_backtick`",
            "gitea_admin_password": (f'"; touch {payload_dir}/NEXUS_DEPLOY_INJECT_semi; echo "'),
        }
    )
    config = NexusConfig.from_secrets_json(raw)
    parsed = _parse_dump(config.dump_shell())
    # Values come back through bash-eval verbatim — proving they were
    # treated as opaque strings, not interpolated.
    assert parsed["KESTRA_PASS"] == f"$(touch {payload_dir}/NEXUS_DEPLOY_INJECT_dollar)"
    assert parsed["INFISICAL_PASS"] == f"`touch {payload_dir}/NEXUS_DEPLOY_INJECT_backtick`"
    assert parsed["GITEA_ADMIN_PASS"] == (
        f'"; touch {payload_dir}/NEXUS_DEPLOY_INJECT_semi; echo "'
    )
    # Side-channel: glob the per-test canary dir (NOT shared /tmp).
    materialised = sorted(canary_dir.glob("NEXUS_DEPLOY_INJECT_*"))
    assert materialised == [], f"eval-injection got through: {materialised}"


# ---------------------------------------------------------------------------
# dump_shell — snapshots
# ---------------------------------------------------------------------------


def test_dump_shell_full_snapshot(snapshot: SnapshotAssertion) -> None:
    raw = (FIXTURES / "secrets_full.json").read_text()
    config = NexusConfig.from_secrets_json(raw)
    assert config.dump_shell() == snapshot


def test_dump_shell_minimal_snapshot(snapshot: SnapshotAssertion) -> None:
    raw = (FIXTURES / "secrets_minimal.json").read_text()
    config = NexusConfig.from_secrets_json(raw)
    assert config.dump_shell() == snapshot


def test_dump_shell_empty_snapshot(snapshot: SnapshotAssertion) -> None:
    config = NexusConfig.from_secrets_json("{}")
    assert config.dump_shell() == snapshot


# ---------------------------------------------------------------------------
# from_tofu_output — subprocess paths
# ---------------------------------------------------------------------------


def test_from_tofu_output_missing_tofu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """tofu binary not on PATH → fallback to empty config."""
    monkeypatch.setenv("PATH", "/nonexistent")
    config = NexusConfig.from_tofu_output(tofu_dir=tmp_path)
    for _, json_key, _ in _FIELDS:
        assert getattr(config, json_key) is None, json_key


def test_from_tofu_output_subprocess_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tofu exits non-zero (e.g. uninitialised state) → fallback to empty."""

    def _raise(*_args: object, **_kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, ["tofu"])

    monkeypatch.setattr("nexus_deploy.config.subprocess.run", _raise)
    config = NexusConfig.from_tofu_output(tofu_dir=tmp_path)
    for _, json_key, _ in _FIELDS:
        assert getattr(config, json_key) is None, json_key


def test_from_tofu_output_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: subprocess returns valid JSON → parsed normally."""

    class FakeProc:
        stdout = '{"admin_username": "from-tofu", "kestra_admin_password": "k"}'

    def _ok(*_args: object, **_kwargs: object) -> FakeProc:
        return FakeProc()

    monkeypatch.setattr("nexus_deploy.config.subprocess.run", _ok)
    config = NexusConfig.from_tofu_output(tofu_dir=tmp_path)
    assert config.admin_username == "from-tofu"
    assert config.kestra_admin_password == "k"
    assert config.dify_admin_password is None


# ---------------------------------------------------------------------------
# CLI subcommand: `config dump-shell` invokes _config_dump_shell directly.
#
# We test the dispatcher in-process (no subprocess) so the tofu-output
# monkeypatch actually applies. Subprocess testing is deferred to the
# end-to-end smoke step that runs after a real spin-up.
# ---------------------------------------------------------------------------


def test_cli_dump_shell_returns_dump(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`config dump-shell --tofu-dir <path>` writes dump_shell() output."""
    raw = (FIXTURES / "secrets_minimal.json").read_text()

    class FakeProc:
        stdout = raw

    monkeypatch.setattr("nexus_deploy.config.subprocess.run", lambda *a, **kw: FakeProc())
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(
        sys, "argv", ["nexus-deploy", "config", "dump-shell", "--tofu-dir", str(tmp_path)]
    )
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == NexusConfig.from_secrets_json(raw).dump_shell()


def test_cli_dump_shell_unknown_arg_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "config", "dump-shell", "--bogus"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unknown arg" in captured.err


def test_cli_dump_shell_tofu_dir_missing_path(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--tofu-dir` without a following PATH exits 2 with a clear message."""
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "config", "dump-shell", "--tofu-dir"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "requires a PATH" in captured.err


def test_cli_dump_shell_stdin_and_tofu_dir_mutex(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--stdin` and `--tofu-dir` together is rejected with exit 2."""
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus-deploy", "config", "dump-shell", "--stdin", "--tofu-dir", "/tmp"],  # noqa: S108
    )
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "mutually exclusive" in captured.err


def test_cli_unknown_command_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "bootstrap"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unknown command" in captured.err


def test_cli_dump_shell_stdin_mode(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`config dump-shell --stdin` reads SECRETS_JSON from stdin.

    Useful when the caller already invoked ``tofu output`` (for an
    empty-check or other pre-flight) and wants to pipe the JSON in
    instead of having us re-run tofu.
    """
    import io

    from nexus_deploy.__main__ import main

    raw = (FIXTURES / "secrets_minimal.json").read_text()
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "config", "dump-shell", "--stdin"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == NexusConfig.from_secrets_json(raw).dump_shell()


def test_cli_dump_shell_stdin_invalid_json(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid JSON on stdin → exit 1 + clear stderr message."""
    import io

    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "config", "dump-shell", "--stdin"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "not valid JSON" in captured.err


def test_cli_dump_shell_default_tofu_dir(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config dump-shell` (no --tofu-dir) defaults to tofu/stack."""

    class FakeProc:
        stdout = "{}"

    captured_cwd: list[Path] = []

    def fake_run(*_args: object, cwd: Path = Path(), **_kwargs: object) -> FakeProc:
        captured_cwd.append(Path(cwd))
        return FakeProc()

    monkeypatch.setattr("nexus_deploy.config.subprocess.run", fake_run)
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "config", "dump-shell"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("ADMIN_USERNAME=admin\n")
    assert captured_cwd == [Path("tofu/stack")]


# ---------------------------------------------------------------------------
# Property-based: roundtrip through bash eval
# ---------------------------------------------------------------------------


# Unicode + a few control chars known to be benign for bash. Newlines/tabs
# excluded — they're handled separately in secret_sync (not config) per the
# Phase-1 plan: config carries opaque strings, sync layer decides whether
# they're env-file safe. `categories=…` (whitelist) keeps the type
# narrow vs `blacklist_categories=`'s broad Literal-tuple shape that mypy
# struggles with.
_safe_value_strategy = st.text(
    alphabet=st.characters(
        categories=["L", "N", "P", "S", "Zs"],
        blacklist_characters="\x00\n",
    ),
    min_size=0,
    max_size=40,
)
_field_keys = [k for _, k, _ in _FIELDS]


@given(
    overrides=st.dictionaries(
        keys=st.sampled_from(_field_keys),
        values=_safe_value_strategy,
        min_size=0,
        max_size=10,
    )
)
@settings(max_examples=50, deadline=None)
def test_roundtrip_dump_shell_then_eval(overrides: dict[str, str]) -> None:
    """Random subsets → dump → bash-eval → values match the overrides.

    Lock the eval-safety contract: for any string a SECRETS_JSON might
    plausibly carry (excluding control chars handled by secret_sync),
    the dump_shell output evaluates to the exact same value in bash.
    """
    raw = json.dumps(overrides)
    config = NexusConfig.from_secrets_json(raw)
    parsed = _parse_dump(config.dump_shell())

    # Build expected — anything not in overrides falls back per _FIELDS
    expected: dict[str, str] = {}
    for bash_var, json_key, fallback in _FIELDS:
        value = overrides.get(json_key)
        if value is None or value == "":
            value = fallback
        expected[bash_var] = value

    for bash_var, want in expected.items():
        assert parsed[bash_var] == want, f"{bash_var}: want={want!r} got={parsed[bash_var]!r}"


# ---------------------------------------------------------------------------
# Misc safety
# ---------------------------------------------------------------------------


def test_shlex_quote_used() -> None:
    """The dump_shell output is shell-safe regardless of input.

    Spot-check that values with spaces are properly quoted (shlex.quote
    wraps them in single quotes). Without quoting, ``KESTRA_PASS=foo bar``
    would set KESTRA_PASS=foo and run `bar` as a command on eval.
    """
    config = NexusConfig.from_secrets_json('{"kestra_admin_password": "with spaces"}')
    rendered = config.dump_shell()
    line = next(line for line in rendered.splitlines() if line.startswith("KESTRA_PASS="))
    # shlex.quote wraps spaces in single quotes
    assert line == f"KESTRA_PASS={shlex.quote('with spaces')}"


# ---------------------------------------------------------------------------
# service_host (Issue #540)
# ---------------------------------------------------------------------------


def test_service_host_default_separator_yields_dot_form() -> None:
    """Single-tenant default produces ``<prefix>.<domain>``."""
    from nexus_deploy.config import service_host

    assert service_host("kestra", "example.com") == "kestra.example.com"
    assert service_host("nocodb", "example.com", ".") == "nocodb.example.com"


def test_service_host_dash_separator_yields_flat_form() -> None:
    """Multi-tenant fork with separator='-' produces flat subdomain."""
    from nexus_deploy.config import service_host

    assert service_host("kestra", "user1.example.com", "-") == "kestra-user1.example.com"
    assert service_host("ssh", "user1.example.com", "-") == "ssh-user1.example.com"
    # The prefix itself is unchanged regardless of separator length:
    # "ccx33-user1.example.com" stays compact (no operator confusion
    # over multi-char prefixes).
    assert service_host("ccx33", "user1.example.com", "-") == "ccx33-user1.example.com"


def test_service_host_empty_domain_returns_just_prefix() -> None:
    """No domain → return prefix alone (defensive — every legitimate
    caller has a domain by the time URLs are built)."""
    from nexus_deploy.config import service_host

    assert service_host("kestra", "") == "kestra"
    assert service_host("kestra", "", "-") == "kestra"


def test_service_host_does_not_inject_separator_when_domain_empty() -> None:
    """Even with separator='-', empty domain must NOT produce
    ``kestra-`` (that would be a stray dangling separator the
    downstream URL parser would mis-interpret)."""
    from nexus_deploy.config import service_host

    assert service_host("kestra", "", "-") == "kestra"
    assert "kestra-" not in service_host("kestra", "", "-")

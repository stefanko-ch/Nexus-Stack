"""Tests for nexus_deploy.secret_sync.

Eight round-tagged invariant tests (one per the caller hardening round)
plus property tests for the dotenv-escape roundtrip and CLI integration
covering the rc=0/1/2 dispatch contract that the caller's case-block
relies on.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from nexus_deploy.secret_sync import (
    StackTarget,
    SyncResult,
    escape_dotenv_value,
    has_multiline,
    is_safe_envfile_key,
    parse_result,
    render_remote_script,
    run_sync_for_stack,
)

# Surrogate Unicode category for the dotenv-escape property test. Pulled
# out as a typed constant so mypy --strict picks up the Literal type;
# an inline ``("Cs",)`` infers as ``tuple[str]`` which doesn't satisfy
# hypothesis's ``Collection[Literal["L", "Lu", …]]`` parameter type.
_SURROGATE_CATEGORY: tuple[Literal["Cs"], ...] = ("Cs",)


# ---------------------------------------------------------------------------
# StackTarget — per-stack path conventions (stacks/<name>/.env etc.)
# ---------------------------------------------------------------------------


def test_stack_target_jupyter_paths() -> None:
    target = StackTarget(name="jupyter")
    assert target.env_file == "/opt/docker-server/stacks/jupyter/.infisical.env"
    assert target.legacy_env_file == "/opt/docker-server/stacks/jupyter/.env"
    assert target.compose_dir == "/opt/docker-server/stacks/jupyter"


def test_stack_target_marimo_paths() -> None:
    target = StackTarget(name="marimo")
    assert target.env_file == "/opt/docker-server/stacks/marimo/.infisical.env"
    assert target.legacy_env_file == "/opt/docker-server/stacks/marimo/.env"
    assert target.compose_dir == "/opt/docker-server/stacks/marimo"


def test_stack_target_begin_marker_capitalised() -> None:
    """Marker comment includes the capitalised stack name."""
    assert "Infisical → Jupyter env" in StackTarget(name="jupyter").begin_marker
    assert "Infisical → Marimo env" in StackTarget(name="marimo").begin_marker


def _kestra_target() -> StackTarget:
    """Helper: the Kestra-style StackTarget. Matches the construction
    in __main__._secret_sync (CLI dispatcher) — keep them in sync."""
    return StackTarget(
        name="kestra",
        key_prefix="SECRET_",
        use_base64_values=True,
        env_file_basename=".env",
        legacy_env_file_basename=None,
        force_recreate=True,
    )


def test_stack_target_kestra_paths() -> None:
    """Kestra writes to .env (the main stack file), not a separate
    .infisical.env. No legacy_env_file (kestra never had one)."""
    target = _kestra_target()
    assert target.env_file == "/opt/docker-server/stacks/kestra/.env"
    assert target.legacy_env_file is None
    assert target.compose_dir == "/opt/docker-server/stacks/kestra"


def test_stack_target_kestra_begin_marker_matches_legacy() -> None:
    """Kestra's BEGIN marker is load-bearing — the in-place sed
    replacement on the server greps for this exact wording, so any
    drift would silently break secret-sync runs against existing
    deploys. Pinned byte-for-byte."""
    assert StackTarget(name="kestra").begin_marker == (
        "# === BEGIN nexus-secret-sync (re-generated each spin-up; do not edit by hand) ==="
    )


def test_stack_target_kestra_format_toggles() -> None:
    """The 5 fields that parameterise the Kestra variant."""
    target = _kestra_target()
    assert target.key_prefix == "SECRET_"
    assert target.use_base64_values is True
    assert target.env_file_basename == ".env"
    assert target.legacy_env_file_basename is None
    assert target.force_recreate is True


def test_stack_target_jupyter_marimo_defaults_unchanged() -> None:
    """Defaults preserve the original Jupyter/Marimo behavior."""
    for name in ("jupyter", "marimo"):
        target = StackTarget(name=name)
        assert target.key_prefix == ""
        assert target.use_base64_values is False
        assert target.env_file_basename == ".infisical.env"
        assert target.legacy_env_file_basename == ".env"
        assert target.force_recreate is False


def test_stack_target_code_server_paths() -> None:
    """code-server reuses the Jupyter/Marimo plaintext-dotenv default
    (issue #496). Paths share the same convention; no force_recreate
    needed since code-server reads env vars at container start and
    compose detects env_file content changes on plain `up -d`."""
    target = StackTarget(name="code-server")
    assert target.env_file == "/opt/docker-server/stacks/code-server/.infisical.env"
    assert target.legacy_env_file == "/opt/docker-server/stacks/code-server/.env"
    assert target.compose_dir == "/opt/docker-server/stacks/code-server"
    assert target.key_prefix == ""
    assert target.use_base64_values is False
    assert target.force_recreate is False


def test_stack_target_code_server_begin_marker() -> None:
    """Marker uses the capitalised stack name; ``"code-server".capitalize()``
    produces ``"Code-server"``."""
    assert "Infisical → Code-server env" in StackTarget(name="code-server").begin_marker


# ---------------------------------------------------------------------------
# Pure-logic helpers — direct tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "ok"),
    [
        ("FOO", True),
        ("FOO_BAR", True),
        ("FOO123", True),
        ("_LEADING_UNDERSCORE", True),
        ("a", True),
        ("1FOO", False),  # leading digit
        ("FOO-BAR", False),  # hyphen
        ("FOO BAR", False),  # space
        ("FOO.BAR", False),  # dot
        ("", False),  # empty
        ("FOO=BAR", False),  # equals
    ],
)
def test_is_safe_envfile_key(key: str, ok: bool) -> None:
    """Round 5 — POSIX shell-identifier rules."""
    assert is_safe_envfile_key(key) is ok


@given(st.text(min_size=1, max_size=20))
def test_is_safe_envfile_key_property(text: str) -> None:
    """Property: result matches the regex the caller uses."""
    expected = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text))
    assert is_safe_envfile_key(text) is expected


def test_has_multiline_round_6() -> None:
    """Round 6 — multi-line value guard."""
    assert has_multiline("with\nnewline") is True
    assert has_multiline("plain value") is False
    assert has_multiline("") is False
    # Carriage-return alone is not "multi-line" per the bash check
    # (the caller's `grep -q $'\n'` only matches \n)
    assert has_multiline("with\rcarriage") is False


def test_escape_dotenv_value_basic() -> None:
    """Round 6 escape rules — `"`, `\\`, `$`, ``\\``` get backslash-escaped
    inside the dotenv value so dotenv parsers (and Kestra's
    EnvVarSecretProvider) read the original string verbatim."""
    assert escape_dotenv_value("plain") == "plain"
    assert escape_dotenv_value('with"quote') == 'with\\"quote'
    assert escape_dotenv_value("with\\backslash") == "with\\\\backslash"
    # Order matters: backslash escape FIRST, then quote
    assert escape_dotenv_value('mix"\\') == 'mix\\"\\\\'


@given(
    # Surrogates ("Cs") can't round-trip through UTF-8 → bash subprocess
    # — exclude them at the strategy level. Real Infisical values don't
    # carry lone surrogates either. The exclude list also drops:
    # newlines / CR (filtered upstream by has_multiline), NUL (env-var
    # values can't carry NUL), $ and backtick (the caller's sed escape
    # doesn't neutralise either — parity choice, see docstring).
    #
    # ``_SURROGATE_CATEGORY`` is hoisted to a module-level constant
    # with an explicit Literal annotation; an inline ``("Cs",)`` infers
    # as ``tuple[str]`` and mypy --strict rejects that against
    # hypothesis's typed ``Collection[Literal["L", "Lu", …]]``.
    st.text(
        alphabet=st.characters(
            exclude_characters="\n\r\x00$`",
            exclude_categories=_SURROGATE_CATEGORY,
        ),
        max_size=40,
    )
)
@settings(max_examples=50, deadline=None)
def test_escape_dotenv_roundtrip_via_bash_eval(value: str) -> None:
    """Property: escape → embed in `K="..."` → bash-eval-parse → original.

    The escape is correct iff bash's dotenv-style assignment parses
    the escaped form back to the original. Excluded:
      - newlines / CR (filtered upstream by has_multiline)
      - NUL (env-var values can't carry NUL)
      - ``$`` and backtick — the caller's sed escape doesn't neutralise
        them either (a parity choice, not a security claim). Such
        values are vanishingly rare in real Infisical content; if one
        occurs, the resulting ``.infisical.env`` line is bash-evaluated
        when docker-compose loads it. Tracked as a known-divergence
        from "fully shell-safe" semantics.
    """
    escaped = escape_dotenv_value(value)
    line = f'K="{escaped}"'
    completed = subprocess.run(
        ["bash", "-c", f"{line}\nprintf '%s' \"$K\""],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert completed.stdout == value


# ---------------------------------------------------------------------------
# render_remote_script — locks the 8 hardening rounds in the rendered bash
# ---------------------------------------------------------------------------


def _render_default(stack: str = "jupyter", **kwargs: Any) -> str:
    defaults: dict[str, Any] = {
        "target": StackTarget(name=stack),
        "project_id": "p",
        "infisical_token": "tok",
        "infisical_env": "dev",
        "forgejo_token": "",
    }
    defaults.update(kwargs)
    return render_remote_script(**defaults)


def test_round_1_set_euo_pipefail_first_executable_line() -> None:
    """Round 1 — `set -euo pipefail` must be the FIRST command in the script.

    Otherwise an early failure (e.g. `mktemp` failing) wouldn't abort
    cleanly; the bash heredoc runs in a fresh shell that doesn't
    inherit the parent's `set` flags.
    """
    script = _render_default()
    first_executable = next(
        line for line in script.splitlines() if line and not line.startswith("#")
    )
    assert first_executable == "set -euo pipefail"


def test_round_3_trap_cleans_all_tmpfiles() -> None:
    """Round 3 — trap on EXIT removes every tmpfile.

    Any addition/removal of tmpfiles must be reflected in the trap;
    test ensures we don't drift. ``$TMP_OUT`` and ``$LEGACY_TMP`` are
    optional (created later in conditional branches) and must be
    guarded by a non-empty check inside the trap so an early-exit
    doesn't `rm -f ""`.
    """
    script = _render_default()
    trap_line = next(line for line in script.splitlines() if line.startswith("trap"))
    for var in ("$CFG", "$SEEN", "$APPEND", "$NEW_BLOCK", "$TSV", "$TMP_OUT", "$LEGACY_TMP"):
        assert var in trap_line, f"trap is missing {var}"
    # Optional tmpfiles must be guarded by a non-empty check
    assert '[ -n "$TMP_OUT" ]' in trap_line
    assert '[ -n "$LEGACY_TMP" ]' in trap_line


def test_round_4_two_stage_jq_validation() -> None:
    """Round 4 — both `.secrets | type == "array"` AND TSV extraction must succeed.

    If we lost the second check, a malformed `secretValue` could let
    SUCCEEDED++ fire while the TSV file is broken — the per-secret
    loop would then read garbage and possibly emit invalid env-vars.
    """
    script = _render_default()
    assert '.secrets | type == "array"' in script
    assert "@base64)] | @tsv" in script
    # The two checks gate SUCCEEDED++ in sequence (continue on either fail)
    assert script.count("FAILED=$((FAILED+1))") >= 2


def test_round_5_key_regex_inline() -> None:
    """Round 5 — exact regex the caller uses, embedded in the rendered bash."""
    script = _render_default()
    assert "'^[A-Za-z_][A-Za-z0-9_]*$'" in script


def test_round_6_multiline_warning_does_not_emit_value() -> None:
    """Round 6 — the SKIPPED_MULTI warning logs only the key + folder, NEVER the value.

    Critical security invariant: if a secret value happens to contain
    a newline, the warning channel must not echo it (could leak partial
    secret to the deploy log). the caller's wording was verbatim:
        "  ⚠ Skipping multi-line secret '$KEY' (folder '$FOLDER_LABEL')"
    """
    script = _render_default()
    skip_warning = next(
        line for line in script.splitlines() if "Skipping multi-line secret" in line
    )
    assert "$KEY" in skip_warning
    assert "$VALUE" not in skip_warning  # NEVER include the value
    assert "$VALUE_B64" not in skip_warning


def test_round_6_uses_bash_case_not_grep_for_multiline_check() -> None:
    """Round 6 — multi-line check uses `case "$VALUE" in *$'\\n'*)`, NOT `grep -q $'\\n'`.

    The legacy form ``printf '%s' "$VALUE" | grep -q $'\\n'`` returns
    a match for EVERY non-empty single-line value because grep
    processes input line-by-line and the ``\\n`` pattern matches the
    implicit line terminator. Result: every secret was skipped as
    "multi-line" and only ``FORGEJO_TOKEN`` (added via a separate code
    path) survived. Confirmed by the spin-up after #510 where
    ``secret-sync: jupyter wrote 1 env-vars`` instead of ~25.

    The bash ``case`` glob compares the variable's bytes directly and
    only fires on genuine embedded newlines.
    """
    script = _render_default()
    # The fix
    assert 'case "$VALUE" in' in script
    assert "*$'\\n'*)" in script
    # The legacy bug must not regress: the buggy line was specifically
    # `printf '%s' "$VALUE" | grep -q $'\\n'`. Comments may legitimately
    # mention `grep -q $'\\n'` to document the pre-fix history, so we
    # only forbid the active pipe form.
    assert "printf '%s' \"$VALUE\" | grep" not in script


def test_round_6_multiline_check_executes_correctly_via_bash() -> None:
    """End-to-end: the rendered multi-line check actually does what we expect.

    The static-text test above confirms we emit the right bash form;
    this test confirms bash interprets that form correctly. We extract
    just the per-secret loop body and run it against five carefully
    chosen inputs. This is the test that would have caught the legacy
    ``grep -q`` bug pre-#510 — the static check would have passed but
    the actual behaviour was broken.
    """
    cases = [
        ("nexus-stack.ch", "single"),
        ("auto", "single"),
        ("admin@example.com", "single"),
        ("line1\nline2", "multi"),  # genuine multi-line
        ("", "single"),  # empty is single-line (consistent with legacy + new)
    ]
    for value, expected in cases:
        b64 = subprocess.run(
            ["base64"], input=value, capture_output=True, text=True, check=True
        ).stdout.strip()
        # Replicate just the multi-line guard from the rendered script
        snippet = f"""
set -euo pipefail
VALUE=$(printf '%s' '{b64}' | base64 -d || true)
case "$VALUE" in
    *$'\\n'*) echo multi ;;
    *) echo single ;;
esac
"""
        out = subprocess.run(
            ["bash", "-c", snippet], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert out == expected, f"value={value!r} expected={expected} got={out}"


def test_round_7_atomic_write_same_directory_mktemp() -> None:
    """Round 7 — `mktemp` for `.infisical.env` is in the SAME directory.

    Cross-filesystem `mv` falls back to copy+unlink (NOT atomic); a
    same-fs rename is atomic, which guarantees a Ctrl-C / SIGKILL
    can never leave $ENV_FILE in a half-state.
    """
    script = _render_default()
    assert 'TMP_OUT=$(mktemp -p "$(dirname "$ENV_FILE")"' in script
    # Make sure we mv (atomic rename), not cp
    mv_line = next(line for line in script.splitlines() if 'mv "$TMP_OUT"' in line)
    assert "$ENV_FILE" in mv_line


def test_round_8_two_outage_gates() -> None:
    """Round 8 — Gate 1 (succeeded==0) AND Gate 2 (pushed==0). Both → wrote=0, exit 0.

    Both gates must be present and BOTH must produce `wrote=0` so the
    existing `.infisical.env` is preserved. Removing either creates a
    silent secrets-wipe vector during partial Infisical outages.
    """
    script = _render_default()
    assert '[ "$SUCCEEDED" -eq 0 ]' in script  # Gate 1
    assert '[ "$PUSHED" -eq 0 ]' in script  # Gate 2
    # Both gates emit RESULT with wrote=0 + exit 0
    wrote_zero_count = script.count("succeeded=0 wrote=0") + script.count(
        "succeeded=$SUCCEEDED wrote=0"
    )
    assert wrote_zero_count >= 2


def test_render_quotes_token_safely() -> None:
    """Adversarial token can't break out of the rendered bash.

    A token with a literal single-quote would have escaped the heredoc
    in the caller's old form (no shlex.quote). Python's shlex.quote
    closes that — verified by bash-eval'ing the TOKEN-extraction line
    against a pytest tmp canary.
    """
    nasty = "tok';rm -rf /;echo '"
    script = _render_default(infisical_token=nasty)
    # Token appears, but ONLY inside a shlex-quoted form. We extract
    # the assignment line and bash-eval just that, then check $ITOK.
    itok_line = next(line for line in script.splitlines() if line.startswith("ITOK="))
    completed = subprocess.run(
        ["bash", "-c", f'{itok_line}\nprintf "%s" "$ITOK"'],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert completed.stdout == nasty


def test_render_includes_legacy_env_strip() -> None:
    """Legacy `.env` block stripped only after successful new-file write.

    The ordering matters: if we stripped the legacy first and the new
    write failed, we'd lose the only working copy of the secrets.
    """
    script = _render_default()
    # WROTE=1 must come BEFORE the legacy-strip block
    wrote_idx = script.index("WROTE=1")
    # Find the LATEST legacy-strip occurrence (the actual sed call,
    # not the variable assignment at the top)
    legacy_strip_idx = script.rindex("LEGACY_ENV")
    assert wrote_idx < legacy_strip_idx


def test_render_jq_missing_path_emits_zero_result() -> None:
    """If jq is missing on the VM, the script emits a zero RESULT and exits 0.

    the caller's pre-flight jq check exists so operators don't get
    misleading "all folder fetches failed" messages — they'd debug
    Infisical instead of installing jq.
    """
    script = _render_default()
    jq_check = next(line for line in script.splitlines() if "command -v jq" in line)
    assert jq_check.startswith("if ! command -v jq")
    # The fallback emits RESULT with all zeros + wrote=0
    assert (
        "pushed=0 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=0 wrote=0"
        in script
    )


def test_render_marker_strings_match_legacy_format() -> None:
    """BEGIN/END marker wording is load-bearing — the in-place sed
    replacement on the server greps for these exact strings."""
    jup = _render_default(stack="jupyter")
    mar = _render_default(stack="marimo")
    assert "BEGIN nexus-secret-sync (Infisical → Jupyter env" in jup
    assert "BEGIN nexus-secret-sync (Infisical → Marimo env" in mar
    # The strip regex anchors at start — must match the legacy comment
    assert "/^# === BEGIN nexus-secret-sync/,/^# === END nexus-secret-sync/d" in jup


# ---------------------------------------------------------------------------
# parse_result — RESULT line extraction
# ---------------------------------------------------------------------------


def test_parse_result_full_line() -> None:
    stdout = "some warnings here\nRESULT pushed=5 skipped_name=2 skipped_multi=1 failed=0 collisions=3 succeeded=4 wrote=1\nfooter"
    result = parse_result(stdout)
    assert result is not None
    assert result == SyncResult(
        pushed=5,
        skipped_invalid_name=2,
        skipped_multiline=1,
        failed_folders=0,
        collisions=3,
        succeeded_folders=4,
        wrote=True,
    )


def test_parse_result_wrote_zero() -> None:
    stdout = (
        "RESULT pushed=0 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=0 wrote=0"
    )
    result = parse_result(stdout)
    assert result is not None
    assert result.wrote is False
    assert result.pushed == 0


def test_parse_result_missing_returns_none() -> None:
    """A missing RESULT line yields None — caller maps to a 'no parseable result' path."""
    assert parse_result("some unrelated output") is None
    assert parse_result("") is None


def test_parse_result_must_anchor_at_line_start() -> None:
    """A stray 'RESULT ...' substring inside another sentence must not match."""
    stdout = "  warning: see RESULT pushed=1 ... above for details\n"
    assert parse_result(stdout) is None


def test_sync_result_is_partial() -> None:
    base_kwargs: dict[str, Any] = {
        "pushed": 5,
        "skipped_invalid_name": 0,
        "skipped_multiline": 0,
        "collisions": 0,
        "succeeded_folders": 1,
    }
    assert SyncResult(failed_folders=0, wrote=True, **base_kwargs).is_partial is False
    assert SyncResult(failed_folders=2, wrote=True, **base_kwargs).is_partial is True
    assert SyncResult(failed_folders=2, wrote=False, **base_kwargs).is_partial is False


# ---------------------------------------------------------------------------
# Round 8 outage-gate: gates are simulated via the script_runner mock,
# proving run_sync_for_stack handles the wrote=False path correctly.
# ---------------------------------------------------------------------------


def _ok_script_runner(stdout: str) -> Any:
    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=stdout, stderr="")

    return runner


def _no_op_command_runner() -> Any:
    def runner(_cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    return runner


def test_round_8_gate_1_succeeded_zero_yields_wrote_false() -> None:
    """Gate 1 — no folder fetch succeeded → wrote=False, no restart issued."""
    target = StackTarget(name="jupyter")
    out = "RESULT pushed=0 skipped_name=0 skipped_multi=0 failed=3 collisions=0 succeeded=0 wrote=0"
    restart_called = {"n": 0}

    def cmd_runner(_cmd: str) -> subprocess.CompletedProcess[str]:
        restart_called["n"] += 1
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    result = run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner(out),
        command_runner=cmd_runner,
    )
    assert result.wrote is False
    assert result.failed_folders == 3
    assert restart_called["n"] == 0  # NO restart on wrote=False


def test_round_8_gate_2_pushed_zero_yields_wrote_false() -> None:
    """Gate 2 — folder fetches OK but no usable secrets → wrote=False."""
    target = StackTarget(name="marimo")
    out = "RESULT pushed=0 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=2 wrote=0"
    result = run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner(out),
        command_runner=_no_op_command_runner(),
    )
    assert result.wrote is False
    assert result.succeeded_folders == 2


def test_run_sync_invokes_restart_on_wrote_true() -> None:
    """`docker compose up -d <stack>` runs after a successful write."""
    target = StackTarget(name="jupyter")
    out = "RESULT pushed=5 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=2 wrote=1"
    captured: dict[str, str] = {}

    def cmd_runner(cmd: str) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    result = run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner(out),
        command_runner=cmd_runner,
    )
    assert result.wrote is True
    assert "/opt/docker-server/stacks/jupyter" in captured["cmd"]
    assert "docker compose up -d jupyter" in captured["cmd"]


def test_run_sync_restart_failure_does_not_alter_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Restart-on-change failure surfaces via stderr but doesn't change SyncResult.

    The sync itself was successful (wrote=True) — the operator already
    has a fresh `.infisical.env`. A failed restart-on-change is a
    separate concern (next spin-up will pick it up); we don't reverse
    the result.
    """
    target = StackTarget(name="jupyter")
    out = "RESULT pushed=5 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=2 wrote=1"

    def failing_cmd(_cmd: str) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            1, ["ssh"], output="pull failed: image not found", stderr=""
        )

    result = run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner(out),
        command_runner=failing_cmd,
    )
    assert result.wrote is True
    captured = capsys.readouterr()
    # Warning goes to stderr (matches the docstring contract)
    assert "docker compose up -d jupyter failed" in captured.err
    assert "rc=1" in captured.err
    # Captured docker-compose output is forwarded so the operator can debug
    assert "pull failed: image not found" in captured.err
    # exc.cmd/argv must NOT leak (defence in depth)
    assert "['ssh']" not in captured.out
    assert "['ssh']" not in captured.err


def test_run_sync_no_result_returns_zero_struct() -> None:
    """Remote stdout without RESULT line → SyncResult all-zeros, wrote=False."""
    target = StackTarget(name="jupyter")
    result = run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner("garbage output"),
        command_runner=_no_op_command_runner(),
    )
    assert result == SyncResult(
        pushed=0,
        skipped_invalid_name=0,
        skipped_multiline=0,
        failed_folders=0,
        collisions=0,
        succeeded_folders=0,
        wrote=False,
    )


def test_run_sync_forwards_remote_warnings_to_local_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Remote diagnostic lines reach local stderr; RESULT is stripped.

    Operationally critical: when the remote script skips a multi-line
    secret, drops a malformed folder, or fires an outage gate, the
    operator sees the warning in the local workflow log. The legacy
    the caller heredoc had this for free (no capture); the migration
    must replicate it explicitly because `_remote.ssh_run_script`
    captures stdout/stderr.
    """
    target = StackTarget(name="jupyter")
    remote_output = (
        "  ⚠ Infisical fetch '<root>' returned bad shape, skipping\n"
        "  ⚠ Skipping multi-line secret 'PEM_KEY' (folder 'storage')\n"
        "RESULT pushed=3 skipped_name=0 skipped_multi=1 failed=1 collisions=0 succeeded=2 wrote=1\n"
    )
    run_sync_for_stack(
        target,
        project_id="p",
        infisical_token="t",
        script_runner=_ok_script_runner(remote_output),
        command_runner=_no_op_command_runner(),
    )
    captured = capsys.readouterr()
    assert "Infisical fetch '<root>' returned bad shape" in captured.err
    assert "Skipping multi-line secret 'PEM_KEY'" in captured.err
    # RESULT line is wire-format, not human-readable — must NOT pollute stderr
    assert "RESULT pushed=" not in captured.err
    assert "RESULT pushed=" not in captured.out


# ---------------------------------------------------------------------------
# Snapshot — full rendered script for both stacks (locks every detail)
# ---------------------------------------------------------------------------


def test_render_jupyter_snapshot(snapshot: SnapshotAssertion) -> None:
    """Full rendered script for a known fixture set — locks every byte."""
    script = render_remote_script(
        target=StackTarget(name="jupyter"),
        project_id="snapshot-project",
        infisical_token="snapshot-token",
        infisical_env="dev",
        forgejo_token="snapshot-forgejo-token",
    )
    assert script == snapshot


def test_render_marimo_snapshot(snapshot: SnapshotAssertion) -> None:
    script = render_remote_script(
        target=StackTarget(name="marimo"),
        project_id="snapshot-project",
        infisical_token="snapshot-token",
        infisical_env="dev",
        forgejo_token="snapshot-forgejo-token",
    )
    assert script == snapshot


def test_render_kestra_snapshot(snapshot: SnapshotAssertion) -> None:
    """Full rendered script for the Kestra variant — pins:
    - KEY_PREFIX=SECRET_, USE_B64=1
    - ENV_FILE=.../kestra/.env (NOT .infisical.env)
    - LEGACY_ENV='' (no separate legacy file)
    - the BEGIN marker wording is pinned byte-for-byte (see
      ``test_stack_target_kestra_begin_marker_matches_legacy``)
    """
    script = render_remote_script(
        target=_kestra_target(),
        project_id="snapshot-project",
        infisical_token="snapshot-token",
        infisical_env="dev",
        forgejo_token="snapshot-forgejo-token",
    )
    assert script == snapshot


def test_render_kestra_uses_secret_prefix() -> None:
    """Kestra appends rows like 'SECRET_<KEY>=<base64>' (NOT
    '<KEY>=value' like Jupyter/Marimo)."""
    script = render_remote_script(
        target=_kestra_target(),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
    )
    # Format toggles set (shlex.quote leaves "SECRET_" + the path
    # unquoted because no shell-special chars are present)
    assert "KEY_PREFIX=SECRET_" in script
    assert "USE_B64=1" in script
    # Base64 branch present (used at runtime when USE_B64=1)
    assert 'printf \'%s%s=%s\\n\' "$KEY_PREFIX" "$KEY" "$VALUE_B64"' in script


def test_render_kestra_writes_to_env_not_infisical_env() -> None:
    """Kestra target writes to .env directly; no separate .infisical.env."""
    script = render_remote_script(
        target=_kestra_target(),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
    )
    assert "ENV_FILE=/opt/docker-server/stacks/kestra/.env" in script
    # No legacy env-file path either (empty string after shlex.quote('') = '')
    assert "LEGACY_ENV=''" in script


def test_render_kestra_skips_legacy_strip_when_no_legacy_file() -> None:
    """Kestra's LEGACY_ENV is empty → the legacy-strip block is gated
    on '[ -n \"$LEGACY_ENV\" ]' so it doesn't try to strip a nonexistent
    file. Reflects the fact that Kestra never had a legacy
    .infisical.env file in the first place."""
    script = render_remote_script(
        target=_kestra_target(),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
    )
    assert 'if [ -n "$LEGACY_ENV" ] && [ -f "$LEGACY_ENV" ]' in script


def test_render_kestra_forgejo_token_in_base64() -> None:
    """When forgejo_token is set, the SECRET_FORGEJO_TOKEN line is also
    base64-encoded (not the plaintext-escaped form Jupyter/Marimo use)."""
    script = render_remote_script(
        target=_kestra_target(),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
        forgejo_token="my-forgejo-token",
    )
    # Kestra branch base64-encodes the token before appending.
    assert "GTOKEN_B64=$(printf '%s' \"$GTOKEN\" | base64 | tr -d '\\n')" in script
    assert 'printf \'%sFORGEJO_TOKEN=%s\\n\' "$KEY_PREFIX" "$GTOKEN_B64"' in script
    # And the dedup-grep uses the prefix
    assert 'grep -qE "^${KEY_PREFIX}FORGEJO_TOKEN="' in script


def test_render_jupyter_branch_unchanged_for_forgejo_token() -> None:
    """Defence in depth: Jupyter/Marimo forgejo-token path stays plain-
    escaped (regression check that the new Kestra branch didn't break
    the original behavior)."""
    script = render_remote_script(
        target=StackTarget(name="jupyter"),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
        forgejo_token="my-forgejo-token",
    )
    # No base64-encode of GTOKEN in the jupyter branch
    assert "GTOKEN_B64=$(printf" in script  # both branches render
    # But the actual emit uses ESCAPED_GTOKEN (plain-escaped) inside the USE_B64=0 branch
    assert "ESCAPED_GTOKEN=" in script
    assert 'printf \'%sFORGEJO_TOKEN="%s"\\n\' "$KEY_PREFIX" "$ESCAPED_GTOKEN"' in script


def test_render_kestra_skips_multiline_guard() -> None:
    """R-multi-line-base64 (Kestra-specific): the multi-line skip
    must NOT run in USE_B64=1 mode. Multi-line PEMs / certs / multi-
    line tokens transit as single-line base64 to Kestra's
    EnvVarSecretProvider, which decodes them server-side. Legacy
    Kestra-secret-sync had no multi-line guard at all (it wrote
    SECRET_<KEY>=<base64> directly without decoding); my migration
    erroneously inherited Jupyter/Marimo's plain-text guard.
    Regression caught in PR #530 R1."""
    script = render_remote_script(
        target=_kestra_target(),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
    )
    # The multi-line guard must be gated on USE_B64=0
    assert 'if [ "$USE_B64" = "0" ]; then' in script
    # And the case statement that does the actual skip lives inside
    # that conditional
    multiline_idx = script.index('case "$VALUE" in')
    use_b64_idx = script.index('if [ "$USE_B64" = "0" ]; then')
    assert use_b64_idx < multiline_idx, (
        "multi-line guard's case statement must come AFTER the USE_B64=0 conditional opens"
    )


def test_render_jupyter_marimo_keep_multiline_guard() -> None:
    """Defence in depth: USE_B64=0 mode (Jupyter/Marimo) MUST still
    skip multi-line values — they can't survive the dotenv KEY="value"
    encoding without escaping."""
    for name in ("jupyter", "marimo"):
        script = render_remote_script(
            target=StackTarget(name=name),
            project_id="p",
            infisical_token="t",
            infisical_env="dev",
        )
        assert 'if [ "$USE_B64" = "0" ]; then' in script
        assert "SKIPPED_MULTI=$((SKIPPED_MULTI+1))" in script


# ---------------------------------------------------------------------------
# CLI — `nexus-deploy secret-sync --stack <jupyter|marimo>`
# ---------------------------------------------------------------------------


def test_cli_secret_sync_missing_stack_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "--stack <jupyter|marimo> is required" in captured.err


def test_cli_secret_sync_unknown_stack_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "redpanda"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unknown stack" in captured.err


def test_cli_secret_sync_unknown_arg_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--bogus"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unknown arg" in captured.err


def test_cli_secret_sync_stack_without_value_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "--stack requires a value" in captured.err


def test_cli_secret_sync_missing_env_vars_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.delenv("PROJECT_ID", raising=False)
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "PROJECT_ID and INFISICAL_TOKEN" in captured.err


def test_cli_secret_sync_happy_path_returns_0(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful sync (wrote=True, failed=0, collisions=0) → rc=0."""
    from nexus_deploy.__main__ import main

    out = "RESULT pushed=7 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=2 wrote=1"

    def fake_script(_s: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=out, stderr="")

    def fake_cmd(_c: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", fake_script)
    monkeypatch.setattr("nexus_deploy._remote.ssh_run", fake_cmd)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "wrote 7 env-vars" in captured.out


def test_cli_secret_sync_partial_returns_1(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """wrote=True AND failed_folders>0 → rc=1 (the caller warns + continues)."""
    from nexus_deploy.__main__ import main

    out = "RESULT pushed=5 skipped_name=0 skipped_multi=0 failed=2 collisions=0 succeeded=3 wrote=1"

    def fake_script(_s: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=out, stderr="")

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", fake_script)
    monkeypatch.setattr(
        "nexus_deploy._remote.ssh_run",
        lambda _c, **_kw: subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="", stderr=""
        ),
    )
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "marimo"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "2 folder fetch(es) failed" in captured.out


def test_cli_secret_sync_outage_gate_returns_0(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """wrote=False from one of the two outage gates → rc=0 (the caller continues)."""
    from nexus_deploy.__main__ import main

    out = "RESULT pushed=0 skipped_name=0 skipped_multi=0 failed=3 collisions=0 succeeded=0 wrote=0"

    def fake_script(_s: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=out, stderr="")

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", fake_script)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "skipped" in captured.out


def test_cli_secret_sync_transport_failure_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ssh/rsync transport error → rc=2 (the caller aborts)."""
    from nexus_deploy.__main__ import main

    def failing_script(_s: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(255, ["ssh", "secret-token-leak-attempt"])

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", failing_script)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "transport failure" in captured.err
    # Defence-in-depth: argv (which would carry the secret-shaped payload) must NOT surface
    assert "secret-token-leak-attempt" not in captured.err
    assert "secret-token-leak-attempt" not in captured.out


def test_cli_secret_sync_unexpected_exception_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-transport exception (KeyError etc.) → rc=2; secret args must not leak."""
    from nexus_deploy.__main__ import main

    secret = "very-secret-value-must-not-appear"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise KeyError(secret)

    monkeypatch.setattr("nexus_deploy.__main__.run_sync_for_stack", boom)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unexpected error (KeyError)" in captured.err
    # Class name only; exception args (which include the secret) must not surface
    assert secret not in captured.err
    assert secret not in captured.out


def test_cli_secret_sync_no_result_line_returns_0(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remote stdout w/o RESULT line → all-zero SyncResult → rc=0 + warning.

    The "no result emitted" branch is non-fatal: the inner script's
    stderr already explained why, so we don't abort the deploy on
    top of it.
    """
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(
        "nexus_deploy._remote.ssh_run_script",
        lambda _s, **_kw: subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="garbage", stderr=""
        ),
    )
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "secret-sync", "--stack", "jupyter"])
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "no usable result" in captured.out


def test_sort_separator_is_a_separate_argument_not_attached() -> None:
    """Regression guard for the Ubuntu 26.04 secret-sync failure.

    uutils (26.04's coreutils) parses `-t=` as "-t with an empty
    value" and exits 2. GNU and BSD read it as "separator is =". The
    block runs under `set -e`, so on 26.04 this killed the whole
    phase with nothing but `transport (CalledProcessError)` to show
    for it.
    """
    script = render_remote_script(
        target=StackTarget(name="kestra", key_prefix="SECRET_", use_base64_values=True),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
        forgejo_token="g",
    )
    executable = [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]

    assert any("sort -t '=' -k1,1" in ln for ln in executable)
    assert not [ln for ln in executable if "-t=" in ln]


def test_sort_still_orders_by_key_not_by_whole_line() -> None:
    """The fix must not become "drop the flags".

    Plain line sort is not equivalent: for keys where one is a prefix
    of another, `A1=x` sorts before `A=y` on the whole line but after
    it on the key. Keeping `-k1,1` is what preserves the key order.
    """
    script = render_remote_script(
        target=StackTarget(name="kestra", key_prefix="SECRET_", use_base64_values=True),
        project_id="p",
        infisical_token="t",
        infisical_env="dev",
        forgejo_token="g",
    )
    assert "-k1,1" in script

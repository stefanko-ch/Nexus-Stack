"""Tests for nexus_deploy.compose_runner.

Eight round-tagged invariant tests (one per hardening round) plus
virtual-service expansion tests, exec'd-bash regression tests for
the parallel-deploy semantics, and CLI integration covering rc=0/1/2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

from nexus_deploy.compose_runner import (
    ComposeUpResult,
    expand_targets,
    parse_result,
    render_remote_script,
    run_compose_up,
)

# ---------------------------------------------------------------------------
# expand_targets — virtual-service resolution
# ---------------------------------------------------------------------------


def test_virtual_services_derived_from_stack_parents_keys() -> None:
    """`_VIRTUAL_SERVICES` is derived from `_STACK_PARENTS.keys()` —
    they cannot drift. Round-4 finding: previously they were two
    independent sources of truth, and a service listed in
    `_VIRTUAL_SERVICES` but missing from `_STACK_PARENTS` would
    have been silently never started (skipped from leaves AND
    parents). The derivation closes that risk.
    """
    from nexus_deploy.compose_runner import _STACK_PARENTS, _VIRTUAL_SERVICES

    assert frozenset(_STACK_PARENTS.keys()) == _VIRTUAL_SERVICES


def test_expand_targets_no_virtuals() -> None:
    """All-leaf input: parents empty, leaves preserve order."""
    parents, leaves = expand_targets(["jupyter", "marimo", "forgejo"])
    assert parents == []
    assert leaves == ["jupyter", "marimo", "forgejo"]


def test_round_5_parent_dedupe_two_virtual_children() -> None:
    """R5 — parent stack appears once even with two virtual children enabled."""
    parents, leaves = expand_targets(["seaweedfs-filer", "seaweedfs-manager"])
    assert parents == ["seaweedfs"]
    assert leaves == []


def test_round_5_parent_skipped_in_leaves_when_already_added() -> None:
    """R5 — explicit parent + child means parent is started once, not twice."""
    parents, leaves = expand_targets(["seaweedfs", "seaweedfs-filer"])
    assert parents == ["seaweedfs"]
    # Explicit "seaweedfs" must not appear in leaves
    assert "seaweedfs" not in leaves
    assert leaves == []


def test_round_6_deferred_services_skipped() -> None:
    """R6 — woodpecker is deferred (started later by the orchestrator)."""
    parents, leaves = expand_targets(["jupyter", "woodpecker", "forgejo"])
    assert parents == []
    assert "woodpecker" not in leaves
    assert leaves == ["jupyter", "forgejo"]


def test_expand_targets_preserves_source_order() -> None:
    """Source order is preserved (operators rely on it for log debug)."""
    parents, leaves = expand_targets(["c", "a", "seaweedfs-filer", "b", "seaweedfs-manager", "z"])
    assert parents == ["seaweedfs"]
    assert leaves == ["c", "a", "b", "z"]


def test_expand_targets_handles_duplicates_in_input() -> None:
    """Duplicate enabled entries don't duplicate compose-up calls."""
    _, leaves = expand_targets(["jupyter", "jupyter", "marimo"])
    assert leaves == ["jupyter", "marimo"]


# ---------------------------------------------------------------------------
# render_remote_script — locks the 8 hardening rounds in the rendered bash
# ---------------------------------------------------------------------------


def _render_default(**kwargs: Any) -> str:
    defaults: dict[str, Any] = {
        "parents": [],
        "leaves": ["jupyter", "marimo"],
    }
    defaults.update(kwargs)
    return render_remote_script(**defaults)


def test_round_1_set_euo_pipefail_first_executable_line() -> None:
    """R1 — `set -euo pipefail` is the first command."""
    script = _render_default()
    first_executable = next(
        line for line in script.splitlines() if line and not line.startswith("#")
    )
    assert first_executable == "set -euo pipefail"


def test_round_2_firewall_override_check_present() -> None:
    """R2 — per-stack firewall override applied when present on disk."""
    script = _render_default(leaves=["minio"])
    # The conditional check must appear
    assert "docker-compose.firewall.yml" in script
    # And the compose invocation form must use both files when present
    assert "-f docker-compose.yml -f docker-compose.firewall.yml" in script


def test_round_3_parallel_deploy_via_background_jobs() -> None:
    """R3 — leaf compose-up runs in background; PIDs collected for `wait`."""
    script = _render_default(leaves=["jupyter", "marimo"])
    # Background-jobs marker
    assert "&\n" in script
    # PID collection
    assert "PIDS+=($!)" in script
    # Wait loop
    assert 'wait "$pid"' in script


def test_round_4_docker_ps_verification_via_bash_exec() -> None:
    """R4 — `docker ps` verification logic, executed via bash.

    Modul-2.0 lesson: dispatch logic that LOOKS right but behaves
    wrong (e.g. grep matching substrings instead of exact names) is
    a real risk. We extract the verification snippet and run it
    against six scenarios.

    Round-3 finding: switched from `grep -q "^name$"` (regex anchors)
    to `grep -qFx -- "name"` (fixed-string + line-exact + arg-end
    sentinel) so that container names containing regex metacharacters
    (`.`, `[`, `*`) can't false-match. The two new cases at the bottom
    pin this — they would have failed under the old regex form.
    """
    cases = [
        # (docker_ps_output, target_name, expected_match)
        ("foo\nbar\nbaz\n", "foo", True),
        ("foo-bar\nfoo-baz\n", "foo", False),  # substring → must NOT match
        ("\n", "foo", False),
        ("foo\n", "FOO", False),  # case-sensitive
        # Regex-metachar safety (round-3 fix). Under the old
        # `^name$` regex, `foo.bar` as a pattern would match `fooXbar`
        # because `.` is "any char". Fixed-string `grep -F` rejects.
        ("fooXbar\n", "foo.bar", False),
        # Exact-match still works with fixed-string + metachar in name
        ("foo.bar\n", "foo.bar", True),
    ]
    for ps_output, name, expected in cases:
        snippet = f"""
set -euo pipefail
printf '%s' {shlex_quote(ps_output)} | grep -qFx -- {shlex_quote(name)} && echo match || echo nomatch
"""
        out = subprocess.run(
            ["bash", "-c", snippet], capture_output=True, text=True, check=False
        ).stdout.strip()
        assert (out == "match") is expected, (
            f"ps={ps_output!r} name={name!r} expected={expected} got={out!r}"
        )


def shlex_quote(s: str) -> str:
    """Local helper because we need bash quoting in the test snippet."""
    import shlex as _shlex

    return _shlex.quote(s)


def test_round_7_global_env_sourced_with_set_a() -> None:
    """R7 — global env (image-version pins) sourced via `set -a; source ...`."""
    script = _render_default()
    assert 'if [ -f "$GLOBAL_ENV" ]; then' in script
    assert "set -a" in script
    assert 'source "$GLOBAL_ENV"' in script
    assert "set +a" in script


def test_round_8_result_line_emitted() -> None:
    """R8 — RESULT line at end with started+failed counts."""
    script = _render_default()
    last_lines = [line for line in script.splitlines() if line.strip()][-3:]
    assert any('echo "RESULT started=' in line for line in last_lines)


def test_render_dify_storage_prep_only_when_flagged() -> None:
    """Dify chown block only present when dify_storage_prep=True."""
    without = _render_default(dify_storage_prep=False)
    assert "/mnt/nexus-data/dify/storage" not in without
    assert "chown -R 1001:1001" not in without

    with_dify = _render_default(dify_storage_prep=True)
    assert "/mnt/nexus-data/dify/storage" in with_dify
    assert "chown -R 1001:1001 /mnt/nexus-data/dify/storage" in with_dify


def test_render_metabase_storage_prep_only_when_flagged() -> None:
    """Metabase mkdir+chown block only present when
    metabase_storage_prep=True (issue #528). UID 2000 is the
    Metabase container's runtime user since v0.46."""
    without = _render_default(metabase_storage_prep=False)
    assert "/mnt/nexus-data/metabase" not in without
    assert "chown -R 2000:2000" not in without

    with_metabase = _render_default(metabase_storage_prep=True)
    assert "/mnt/nexus-data/metabase" in with_metabase
    assert "chown -R 2000:2000 /mnt/nexus-data/metabase" in with_metabase


def test_render_metabase_chown_is_guarded_by_owner_check() -> None:
    """The metabase chown must be guarded by an owner-stat check so
    `compose up` doesn't walk the entire data tree on every deploy
    once the dashboards/H2 state has grown. Round-1 PR #591 review
    finding."""
    script = _render_default(metabase_storage_prep=True)
    # Guard structure: stat the top-level dir, only chown if owner
    # isn't already 2000:2000.
    assert "stat -c '%u:%g' /mnt/nexus-data/metabase" in script
    assert '!= "2000:2000"' in script
    # The chown must be INSIDE the if-block (not before/after it).
    # Approximate check: chown appears between the if-line and the
    # closing 'fi' on adjacent lines.
    lines = script.splitlines()
    if_idx = next(i for i, le in enumerate(lines) if "stat -c '%u:%g'" in le)
    fi_idx = next(i for i, le in enumerate(lines) if i > if_idx and le.strip() == "fi")
    assert any("chown -R 2000:2000" in le for le in lines[if_idx:fi_idx])


def test_render_dify_and_metabase_blocks_independent() -> None:
    """Both flags can fire together — Dify + Metabase enabled in the
    same stack produces both prep blocks back-to-back."""
    script = _render_default(dify_storage_prep=True, metabase_storage_prep=True)
    assert "/mnt/nexus-data/dify/storage" in script
    assert "/mnt/nexus-data/metabase" in script


def test_render_handles_empty_lists() -> None:
    """Empty parents + leaves still produces a parseable RESULT (started=0 failed=0)."""
    script = render_remote_script(parents=[], leaves=[])
    # Bash arrays with zero elements don't enter the `for` loop
    assert "PARENTS=()" in script
    assert "LEAVES=()" in script
    assert 'echo "RESULT started=$STARTED failed=$FAILED"' in script


def test_render_missing_parent_compose_counted_as_failed() -> None:
    """A missing parent docker-compose.yml is counted as failed in
    BOTH the parent and leaf branches (so the cleanup loop is
    idempotent and an unmatched virtual service surfaces as a real
    failure rather than being silently skipped)."""
    script = render_remote_script(parents=["seaweedfs"], leaves=[])
    # The conditional + FAILED increment must be present
    assert 'if [ -f "$STACKS_DIR/$svc/docker-compose.yml" ]' in script
    assert "missing for parent" in script
    # Both parent + leaf branches increment FAILED on missing compose.yml
    # → the loop appears twice (one per branch); count via the
    # specific FAILED+=1 pattern. We expect two occurrences.
    assert script.count("FAILED=$((FAILED+1))") >= 2


def test_render_special_chars_in_service_name_quoted() -> None:
    """shlex.quote protects against future stack names with special chars.

    Realistically the STACK_PARENTS map is hard-coded to safe ASCII
    names, but defence in depth: a future contributor adding
    'foo bar' would not break the rendered bash.
    """
    script = render_remote_script(parents=["foo-bar"], leaves=["a;b"])
    assert "'a;b'" in script  # shlex-quoted form


# ---------------------------------------------------------------------------
# parse_result
# ---------------------------------------------------------------------------


def test_parse_result_happy() -> None:
    out = "RESULT started=8 failed=0"
    assert parse_result(out) == ComposeUpResult(started=8, failed=0)


def test_parse_result_with_warnings_above() -> None:
    out = (
        "  ✓ jupyter started and running\n"
        "  ✗ marimo compose up failed (rc=1)\n"
        "RESULT started=1 failed=1"
    )
    assert parse_result(out) == ComposeUpResult(started=1, failed=1)


def test_parse_result_no_match() -> None:
    assert parse_result("garbage output") is None


def test_compose_up_result_is_success() -> None:
    assert ComposeUpResult(started=5, failed=0).is_success is True
    assert ComposeUpResult(started=0, failed=0).is_success is True
    assert ComposeUpResult(started=5, failed=2).is_success is False


# ---------------------------------------------------------------------------
# run_compose_up — orchestration
# ---------------------------------------------------------------------------


def _ok_runner(stdout: str) -> Any:
    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=stdout, stderr="")

    return runner


def test_run_compose_up_happy_path() -> None:
    out = "RESULT started=2 failed=0"
    result = run_compose_up(["jupyter", "marimo"], script_runner=_ok_runner(out))
    assert result == ComposeUpResult(started=2, failed=0)


def test_run_compose_up_no_result_attributes_failure_to_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No RESULT line → failed=count of (parents+leaves)."""
    result = run_compose_up(
        ["jupyter", "marimo", "seaweedfs-filer"],
        script_runner=_ok_runner("garbage output"),
    )
    # parents=[seaweedfs], leaves=[jupyter, marimo] → 3 services
    assert result.failed == 3
    assert result.started == 0


def test_run_compose_up_forwards_remote_warnings_to_local_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Modul-1.2 Round-4 lesson: remote ✓/✗ lines reach local stderr."""
    out = (
        "  ✓ jupyter started and running\n"
        "  ✗ marimo compose up failed (rc=1)\n"
        "RESULT started=1 failed=1"
    )
    run_compose_up(["jupyter", "marimo"], script_runner=_ok_runner(out))
    captured = capsys.readouterr()
    assert "jupyter started and running" in captured.err
    assert "marimo compose up failed" in captured.err
    # RESULT line is wire-format, must NOT pollute stderr
    assert "RESULT started=" not in captured.err


def test_run_compose_up_dify_default_when_dify_in_enabled() -> None:
    """dify_storage_prep defaults to True iff 'dify' is in enabled."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "dify"], script_runner=capture)
    assert "/mnt/nexus-data/dify/storage" in captured_script["script"]


def test_run_compose_up_dify_omitted_when_dify_not_in_enabled() -> None:
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter"], script_runner=capture)
    assert "/mnt/nexus-data/dify/storage" not in captured_script["script"]


def test_run_compose_up_metabase_default_when_metabase_in_enabled() -> None:
    """metabase_storage_prep defaults to True iff 'metabase' is in enabled
    (issue #528). Mirrors the equivalent dify default-on test."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "metabase"], script_runner=capture)
    assert "/mnt/nexus-data/metabase" in captured_script["script"]
    # Owner-check guard present (avoids O(n) chown on every deploy).
    assert "stat -c '%u:%g'" in captured_script["script"]


def test_run_compose_up_metabase_omitted_when_metabase_not_in_enabled() -> None:
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter"], script_runner=capture)
    assert "/mnt/nexus-data/metabase" not in captured_script["script"]


def test_run_compose_up_metabase_explicit_override_beats_enabled_inference() -> None:
    """Caller can force metabase_storage_prep=False even when 'metabase'
    is in enabled — needed for tests + operator escape hatch if the
    chown is causing trouble. Mirrors the dify override semantics."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["metabase"], script_runner=capture, metabase_storage_prep=False)
    assert "/mnt/nexus-data/metabase" not in captured_script["script"]


# ---------------------------------------------------------------------------
# ollama-internal cross-stack network prep (shared by ollama + litellm)
# ---------------------------------------------------------------------------


def test_render_ollama_internal_network_prep_only_when_flagged() -> None:
    """Both `stacks/ollama` and `stacks/litellm` declare `ollama-internal`
    as an `external: true` network. Without the network already created,
    `docker compose up` aborts BEFORE the container is created. The
    pre-compose block creates the network idempotently when either stack
    is enabled (or omitted otherwise)."""
    without = _render_default(ollama_internal_network_prep=False)
    assert "ollama-internal" not in without
    assert "docker network create" not in without

    with_prep = _render_default(ollama_internal_network_prep=True)
    assert "docker network inspect ollama-internal" in with_prep
    assert "docker network create --label managed-by=nexus-stack ollama-internal" in with_prep


def test_render_ollama_internal_network_prep_is_idempotent() -> None:
    """The inspect-then-create guard short-circuits if the network
    already exists. A bare `docker network create` would fail with
    a non-zero exit on the second deploy under `set -euo pipefail`
    and abort the entire compose-up loop.

    Tests the full inspect→create chain as one contiguous expression
    rather than just `||` presence: a future refactor that splits
    the guard into two unrelated statements (e.g. `inspect; if [ $?
    -ne 0 ]; then create; fi`) would lose the short-circuit semantics
    under `set -e` and silently break idempotency. Whitespace is
    normalised so the test isn't brittle to backslash-newline
    continuation tweaks bash treats as one logical line.
    """
    script = _render_default(ollama_internal_network_prep=True)
    # Normalise whitespace AND strip the bash line-continuation
    # backslash (`\` followed by newline) so the substring matcher
    # doesn't depend on the renderer's exact line-wrap choice.
    normalised = " ".join(script.replace("\\\n", " ").split())
    assert (
        "docker network inspect ollama-internal >/dev/null 2>&1 || "
        "docker network create --label managed-by=nexus-stack ollama-internal"
    ) in normalised


def test_run_compose_up_network_prep_default_when_litellm_in_enabled() -> None:
    """ollama_internal_network_prep defaults to True iff 'litellm' OR
    'ollama' is in enabled. Mirrors the dify/metabase storage-prep
    default semantics."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "litellm"], script_runner=capture)
    assert "docker network inspect ollama-internal" in captured_script["script"]


def test_run_compose_up_network_prep_default_when_ollama_in_enabled() -> None:
    """Ollama-only deployment (LiteLLM disabled) still needs the
    pre-create because ollama's own compose declares the network as
    `external: true` — symmetric ownership with litellm."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "ollama"], script_runner=capture)
    assert "docker network inspect ollama-internal" in captured_script["script"]


def test_run_compose_up_network_prep_renders_once_in_joint_case() -> None:
    """Joint LiteLLM + Ollama deployment: only one pre-create block,
    not duplicated. The `inspect || create` guard is idempotent at
    runtime regardless, but rendering the block twice would be a
    silent code smell — confirms the inference doesn't double-add."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=2 failed=0", stderr=""
        )

    run_compose_up(["litellm", "ollama"], script_runner=capture)
    assert (
        captured_script["script"].count(
            "docker network create --label managed-by=nexus-stack ollama-internal"
        )
        == 1
    )


def test_run_compose_up_network_prep_omitted_when_neither_in_enabled() -> None:
    """Neither litellm nor ollama → no network-prep block (also no
    spurious network created on stacks that don't need it)."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter"], script_runner=capture)
    assert "ollama-internal" not in captured_script["script"]


def test_run_compose_up_network_prep_explicit_override_beats_enabled_inference() -> None:
    """Caller can force ollama_internal_network_prep=False even when
    'litellm' or 'ollama' is in enabled — operator escape hatch if the
    network handling needs to be deferred to a different mechanism."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["litellm"], script_runner=capture, ollama_internal_network_prep=False)
    assert "ollama-internal" not in captured_script["script"]


# ---------------------------------------------------------------------------
# HedgeDoc uploads-dir prep (bind-mount for R2 snapshot/restore)
# ---------------------------------------------------------------------------


def test_render_hedgedoc_uploads_prep_only_when_flagged() -> None:
    """HedgeDoc bind-mounts /mnt/nexus-data/hedgedoc/uploads onto its
    /hedgedoc/public/uploads so the R2 snapshot/restore cycle can
    rsync user-uploaded images (#618). Block only present when
    hedgedoc_uploads_prep=True; absent for other stacks."""
    without = _render_default(hedgedoc_uploads_prep=False)
    assert "/mnt/nexus-data/hedgedoc/uploads" not in without
    assert "10000:10000" not in without

    with_hedgedoc = _render_default(hedgedoc_uploads_prep=True)
    assert "/mnt/nexus-data/hedgedoc/uploads" in with_hedgedoc
    assert "chown -R 10000:10000 /mnt/nexus-data/hedgedoc/uploads" in with_hedgedoc


def test_render_hedgedoc_chown_is_guarded_by_owner_check() -> None:
    """The hedgedoc chown must be guarded by an owner-stat check so
    `compose up` doesn't walk the entire uploads tree on every deploy
    once users have accumulated attached images. Same pattern as the
    metabase chown guard."""
    script = _render_default(hedgedoc_uploads_prep=True)
    assert "stat -c '%u:%g' /mnt/nexus-data/hedgedoc/uploads" in script
    assert '!= "10000:10000"' in script
    lines = script.splitlines()
    if_idx = next(
        i for i, le in enumerate(lines) if "stat -c '%u:%g' /mnt/nexus-data/hedgedoc/uploads" in le
    )
    fi_idx = next(i for i, le in enumerate(lines) if i > if_idx and le.strip() == "fi")
    assert any("chown -R 10000:10000" in le for le in lines[if_idx:fi_idx])


def test_run_compose_up_hedgedoc_default_when_hedgedoc_in_enabled() -> None:
    """hedgedoc_uploads_prep defaults to True iff 'hedgedoc' is in
    enabled. Mirrors the dify/metabase storage-prep defaults."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "hedgedoc"], script_runner=capture)
    assert "/mnt/nexus-data/hedgedoc/uploads" in captured_script["script"]


def test_run_compose_up_hedgedoc_omitted_when_hedgedoc_not_in_enabled() -> None:
    """No hedgedoc → no uploads-prep block."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter"], script_runner=capture)
    assert "/mnt/nexus-data/hedgedoc/uploads" not in captured_script["script"]


# ---------------------------------------------------------------------------
# Planka data-dir prep (bind-mount for R2 snapshot/restore)
# ---------------------------------------------------------------------------


def test_render_planka_data_prep_only_when_flagged() -> None:
    """Planka 2.x bind-mounts /mnt/nexus-data/planka/data onto its
    /app/data so the R2 snapshot/restore cycle can rsync uploads.
    Block only present when planka_data_prep=True; absent otherwise."""
    without = _render_default(planka_data_prep=False)
    assert "/mnt/nexus-data/planka/data" not in without

    with_planka = _render_default(planka_data_prep=True)
    assert "/mnt/nexus-data/planka/data" in with_planka
    assert "chown -R 1000:1000 /mnt/nexus-data/planka/data" in with_planka


def test_render_planka_chown_is_guarded_by_owner_check() -> None:
    """The planka chown must be guarded by an owner-stat check so
    `compose up` doesn't walk the entire data tree on every deploy.
    Same pattern as the hedgedoc/metabase chown guards."""
    script = _render_default(planka_data_prep=True)
    assert "stat -c '%u:%g' /mnt/nexus-data/planka/data" in script
    assert '!= "1000:1000"' in script
    lines = script.splitlines()
    if_idx = next(
        i for i, le in enumerate(lines) if "stat -c '%u:%g' /mnt/nexus-data/planka/data" in le
    )
    fi_idx = next(i for i, le in enumerate(lines) if i > if_idx and le.strip() == "fi")
    assert any("chown -R 1000:1000" in le for le in lines[if_idx:fi_idx])


def test_run_compose_up_planka_default_when_planka_in_enabled() -> None:
    """planka_data_prep defaults to True iff 'planka' is in enabled."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter", "planka"], script_runner=capture)
    assert "/mnt/nexus-data/planka/data" in captured_script["script"]


def test_run_compose_up_planka_omitted_when_planka_not_in_enabled() -> None:
    """No planka → no data-prep block."""
    captured_script: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured_script["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT started=1 failed=0", stderr=""
        )

    run_compose_up(["jupyter"], script_runner=capture)
    assert "/mnt/nexus-data/planka/data" not in captured_script["script"]


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, "-m", "nexus_deploy", "compose", *args],
        capture_output=True,
        text=True,
        env=full_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_compose_missing_subcommand_returns_2() -> None:
    rc, _, err = _run_cli([])
    assert rc == 2
    assert "only 'up' subcommand" in err


def test_cli_compose_up_missing_enabled_returns_2() -> None:
    rc, _, err = _run_cli(["up"])
    assert rc == 2
    assert "--enabled" in err


def test_cli_compose_up_empty_enabled_returns_zero() -> None:
    """Empty list = nothing to do = success."""
    rc, out, _ = _run_cli(["up", "--enabled", ""])
    assert rc == 0
    assert "nothing to do" in out


def test_run_compose_up_filters_empty_csv_entries() -> None:
    """expand_targets handles empty / duplicate inputs cleanly.

    Regression-test the PARSER side: an upstream CSV produced by a
    `tr '\\n ' ',,'` pipeline may contain empty entries between
    consecutive separators or at the trailing position. The CLI's
    list-comprehension filter `[s.strip() for s in ... if s.strip()]`
    drops them; expand_targets' dedupe handles repeats. Result: a
    CSV like `",jupyter,,marimo,"` resolves to the same targets as
    `"jupyter,marimo"`.
    """
    # Simulate what the CLI parser produces from a messy CSV
    raw = ",jupyter,,marimo,"
    enabled = [s.strip() for s in raw.split(",") if s.strip()]
    assert enabled == ["jupyter", "marimo"]
    parents, leaves = expand_targets(enabled)
    assert parents == []
    assert leaves == ["jupyter", "marimo"]


def test_cli_compose_up_unknown_arg_returns_2() -> None:
    rc, _, err = _run_cli(["up", "--enabled", "jupyter", "--bogus"])
    assert rc == 2
    assert "unknown arg" in err


def test_cli_compose_up_subcommand_typo_returns_2() -> None:
    """`compose down`, `compose restart`, etc. all rejected."""
    rc, _, err = _run_cli(["down", "--enabled", "x"])
    assert rc == 2
    assert "only 'up'" in err


# ---------------------------------------------------------------------------
# CLI rc-mapping unit tests — monkeypatch run_compose_up to exercise the
# rc=1 (partial) and rc=2-from-no-RESULT paths without spinning a subprocess.
# Subprocess-based tests above only exercise rc=0/2-from-arg-validation;
# these fill the gap (round-2 finding on PR #513).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("started", "failed", "expected_rc"),
    [
        (5, 0, 0),  # all success
        (3, 2, 1),  # partial: some succeeded, some failed → rc=1
        (0, 4, 2),  # nothing succeeded → rc=2 (orchestrator should abort)
        (0, 0, 0),  # zero-zero (e.g. all virtuals collapsed) → rc=0
    ],
)
def test_compose_up_cli_rc_mapping(
    monkeypatch: pytest.MonkeyPatch, started: int, failed: int, expected_rc: int
) -> None:
    """Verify the rc=0/1/2 contract via direct `_compose_up` call."""
    from nexus_deploy.__main__ import _compose_up

    def fake_run(_enabled: list[str]) -> ComposeUpResult:
        return ComposeUpResult(started=started, failed=failed)

    monkeypatch.setattr("nexus_deploy.__main__.run_compose_up", fake_run)
    rc = _compose_up(["up", "--enabled", "jupyter,marimo"])
    assert rc == expected_rc


def test_compose_up_cli_rc2_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Programming errors → rc=2 (NOT Python's default rc=1, which would
    collide with the partial-failure semantic). Exception class only
    in stderr; no str/repr that could leak attribute values."""
    from nexus_deploy.__main__ import _compose_up

    def boom(_enabled: list[str]) -> ComposeUpResult:
        raise RuntimeError("secret-bearing-message-NEVER-print")

    monkeypatch.setattr("nexus_deploy.__main__.run_compose_up", boom)
    rc = _compose_up(["up", "--enabled", "jupyter"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "RuntimeError" in captured.err
    assert "secret-bearing-message-NEVER-print" not in captured.err
    assert "secret-bearing-message-NEVER-print" not in captured.out


def test_compose_up_cli_rc2_on_transport_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ssh/rsync failure → rc=2. exc.cmd must NOT leak to stderr."""
    from nexus_deploy.__main__ import _compose_up

    def boom(_enabled: list[str]) -> ComposeUpResult:
        raise subprocess.CalledProcessError(255, ["ssh", "with-secret-arg"])

    monkeypatch.setattr("nexus_deploy.__main__.run_compose_up", boom)
    rc = _compose_up(["up", "--enabled", "jupyter"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "transport failure" in captured.err
    assert "with-secret-arg" not in captured.err
    assert "with-secret-arg" not in captured.out

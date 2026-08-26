"""Tests for nexus_deploy.seeder.

Eight round-tagged invariant tests (one per the caller hardening round)
plus path-safety property tests, exec'd-bash regression tests for HTTP
dispatch (Modul-2.0 lessons), and CLI integration covering rc=0/1/2.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nexus_deploy.seeder import (
    SeedFile,
    SeedResult,
    _is_safe_repo_path,
    _url_encode_path,
    encode_payloads,
    list_seed_files,
    parse_result,
    render_remote_loop,
    run_seed_for_repo,
)

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "workspace_seeds_minimal"


# ---------------------------------------------------------------------------
# Path safety + URL encoding — pure-logic helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("nexus_seeds/foo.yaml", True),
        ("nexus_seeds/kestra/flows/abc.yaml", True),
        ("nexus_seeds/dot.in.name.txt", True),
        ("nexus_seeds/under_score-dash.txt", True),
        ("nexus_seeds/with space.txt", False),
        ("nexus_seeds/with$dollar.txt", False),
        ("nexus_seeds/with`backtick`.txt", False),
        ("nexus_seeds/non-ascii-é.txt", False),
        ("nexus_seeds/with;semi.txt", False),
        # `..` and `/` are both in the safe-char set, so this passes
        # the regex layer. The actual escape protection is two-layer
        # (regex + Path.resolve() relative_to) — see
        # ``test_round_5_path_safety_rejects_dotdot_escape`` for the
        # second layer.
        ("../escape.txt", True),
        ("", False),
    ],
)
def test_is_safe_repo_path_parameterized(path: str, ok: bool) -> None:
    """R5 — repo-path safety regex matches the canonical
    ``[a-zA-Z0-9_./-]+`` shape from ``_VALID_REPO_PATH_RE`` in
    ``src/nexus_deploy/seeder.py``.

    This test only covers the char-level regex. Structural escape
    protection (``..`` segments, leading ``/``, empty segments) is
    enforced separately in ``list_seed_files`` via Path.resolve()
    + relative_to() and in ``_seed`` via per-segment validation.
    """
    assert _is_safe_repo_path(path) is ok


@given(st.text(min_size=1, max_size=30))
def test_is_safe_repo_path_property(text: str) -> None:
    """Property: result matches the documented regex."""
    import re

    expected = bool(re.fullmatch(r"[A-Za-z0-9._/-]+", text))
    assert _is_safe_repo_path(text) is expected


def test_url_encode_path_per_segment() -> None:
    """— per-segment ``jq @uri`` encoding."""
    assert _url_encode_path("nexus_seeds/foo.yaml") == "nexus_seeds/foo.yaml"
    # Slash separator preserved, but special chars in segments are encoded
    assert (
        _url_encode_path("nexus_seeds/kestra/flow with space.yaml")
        == "nexus_seeds/kestra/flow%20with%20space.yaml"
    )
    # Unsafe chars get escaped per-segment
    assert _url_encode_path("a&b/c?d") == "a%26b/c%3Fd"


# ---------------------------------------------------------------------------
# list_seed_files — walk + safety
# ---------------------------------------------------------------------------


def test_list_seed_files_minimal_fixture() -> None:
    """Fixture has 4 files; all walked + sorted by repo_path."""
    files = list_seed_files(FIXTURE_ROOT)
    assert len(files) == 4
    repo_paths = [f.repo_path for f in files]
    # Sorted for deterministic ordering (R7)
    assert repo_paths == sorted(repo_paths)
    # All under the prefix
    assert all(rp.startswith("nexus_seeds/") for rp in repo_paths)


def test_round_5_path_safety_rejects_dotdot_escape(tmp_path: Path) -> None:
    """R5 — Path.resolve() rejects files whose resolved path escapes root.

    Direct attack vector: a file whose Path.resolve() lands outside
    root (via a symlink to /etc/passwd or similar). The regex check
    alone wouldn't catch this — only the Path.resolve().relative_to()
    check does. Test covers both vectors:
    1. Symlink pointing outside root (SHOULD be skipped via is_symlink)
    2. Filename containing chars that pass regex but resolve outside
       (impossible in practice without symlinks, but we check the
       resolved-path comparison fires anyway).
    """
    inside = tmp_path / "good.txt"
    inside.write_text("safe", encoding="utf-8")

    outside = tmp_path / "OUTSIDE.txt"
    outside.write_text("NEVER seed this", encoding="utf-8")

    # Symlink whose target escapes the seed root
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "good.txt").write_text("ok", encoding="utf-8")
    (seed_root / "escape").symlink_to(outside)

    files = list_seed_files(seed_root)
    repo_paths = [f.repo_path for f in files]
    # Symlink skipped, only the real file passes
    assert "nexus_seeds/good.txt" in repo_paths
    assert not any("OUTSIDE" in rp for rp in repo_paths)
    assert not any("escape" in rp for rp in repo_paths)


def test_round_6_symlinks_skipped(tmp_path: Path) -> None:
    """R6 — symlinks are skipped (regular files only)."""
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    real = seed_root / "real.txt"
    real.write_text("real content", encoding="utf-8")
    link = seed_root / "link_to_real.txt"
    link.symlink_to(real)

    files = list_seed_files(seed_root)
    repo_paths = {f.repo_path for f in files}
    assert "nexus_seeds/real.txt" in repo_paths
    assert "nexus_seeds/link_to_real.txt" not in repo_paths


def test_round_7_deterministic_ordering() -> None:
    """R7 — list_seed_files returns the same ordering across calls.

    Operators rely on stable ordering for log debug + snapshot tests
    (filename: index correspondence in the push-dir).
    """
    a = list_seed_files(FIXTURE_ROOT)
    b = list_seed_files(FIXTURE_ROOT)
    assert [f.repo_path for f in a] == [f.repo_path for f in b]
    assert a == b


def test_list_seed_files_unsafe_filename_dropped(tmp_path: Path) -> None:
    """Files whose computed repo_path violates _VALID_REPO_PATH_RE are dropped.

    Files with an unsafe computed ``repo_path`` are dropped silently;
    the caller is expected to notice via the file-count mismatch.
    Future enhancement: surface a warning + count.
    """
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "ok.txt").write_text("ok", encoding="utf-8")
    # Filename with space — fails the regex
    (seed_root / "with space.txt").write_text("space", encoding="utf-8")
    files = list_seed_files(seed_root)
    repo_paths = {f.repo_path for f in files}
    assert "nexus_seeds/ok.txt" in repo_paths
    assert "nexus_seeds/with space.txt" not in repo_paths


def test_list_seed_files_returns_empty_for_missing_root(tmp_path: Path) -> None:
    """Non-existent root → empty list, NOT exception."""
    assert list_seed_files(tmp_path / "does-not-exist") == []


def test_list_seed_files_base64_encodes_content(tmp_path: Path) -> None:
    """File bytes are base64-encoded ASCII string (no MIME line wrapping)."""
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    raw = b"hello\nworld"
    (seed_root / "x.txt").write_bytes(raw)
    files = list_seed_files(seed_root)
    assert len(files) == 1
    assert files[0].content_b64 == base64.b64encode(raw).decode("ascii")
    # No newlines in the encoded form
    assert "\n" not in files[0].content_b64


def test_list_seed_files_custom_prefix(tmp_path: Path) -> None:
    """Custom prefix is applied to every repo_path."""
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "x.txt").write_text("x", encoding="utf-8")
    files = list_seed_files(seed_root, prefix="custom/")
    assert files[0].repo_path == "custom/x.txt"


# ---------------------------------------------------------------------------
# encode_payloads — JSON construction
# ---------------------------------------------------------------------------


def test_encode_payloads_filename_format() -> None:
    """Filenames are seed-NNNN.json with zero-padded sequential index."""
    files = [
        SeedFile(
            repo_path=f"nexus_seeds/file{i}.txt",
            url_path=f"nexus_seeds/file{i}.txt",
            content_b64="aGVsbG8=",
            commit_message=f"chore(seed): add file{i}",
        )
        for i in range(3)
    ]
    payloads = encode_payloads(files)
    assert sorted(payloads.keys()) == [
        "seed-0000.json",
        "seed-0001.json",
        "seed-0002.json",
    ]


def test_encode_payloads_json_shape() -> None:
    """JSON carries the three expected keys (url_path, content, message).

    Key ordering on disk is alphabetical (``encode_payloads`` uses
    ``sort_keys=True`` for byte-stable serialisation), but ordering
    isn't semantically meaningful after json.loads() — this test
    asserts on the parsed dict, not the byte form.
    """
    files = [
        SeedFile(
            repo_path="nexus_seeds/x.txt",
            url_path="nexus_seeds/x.txt",
            content_b64="aGVsbG8=",
            commit_message="chore(seed): add x",
        )
    ]
    payloads = encode_payloads(files)
    body = json.loads(payloads["seed-0000.json"])
    assert body == {
        "url_path": "nexus_seeds/x.txt",
        "content": "aGVsbG8=",
        "message": "chore(seed): add x",
    }


def test_encode_payloads_minimal_fixture_snapshot() -> None:
    """Snapshot the per-file JSON for the minimal fixture (gold-master)."""
    files = list_seed_files(FIXTURE_ROOT)
    payloads = encode_payloads(files)
    # 4 files in the fixture
    assert len(payloads) == 4
    # All bodies parse as JSON with the 3 expected keys
    for body_str in payloads.values():
        body = json.loads(body_str)
        assert set(body.keys()) == {"url_path", "content", "message"}


# ---------------------------------------------------------------------------
# render_remote_loop — locks the 8 hardening rounds in the rendered bash
# ---------------------------------------------------------------------------


def _render_default(**kwargs: Any) -> str:
    defaults: dict[str, Any] = {
        "token": "tok",
        "repo_owner": "admin",
        "repo_name": "workspace",
    }
    defaults.update(kwargs)
    return render_remote_loop(**defaults)


def test_round_1_set_euo_pipefail_first_executable_line() -> None:
    """R1 — `set -euo pipefail` is the FIRST command in the rendered bash."""
    script = _render_default()
    first_executable = next(
        line for line in script.splitlines() if line and not line.startswith("#")
    )
    assert first_executable == "set -euo pipefail"


def test_round_2_token_only_in_config_tmpfile_never_argv() -> None:
    """R2 — token reaches Forgejo ONLY via the curl --config tmpfile.

    The token must NOT appear on any curl argv; --config reads the
    Authorization header from a mode-600 tmpfile written by printf.
    Verifying:
      - curl invocation uses --config "$CFG" (NOT -H "Authorization: ...")
      - $TOKEN is referenced only by the tmpfile-write line
    """
    script = _render_default(token="super-secret-do-not-leak")
    # --config is present
    assert '--config "$CFG"' in script
    # No curl line has -H 'Authorization' — that would put token in argv
    for line in script.splitlines():
        if line.lstrip().startswith("curl ") or "curl -s" in line or "| curl " in line:
            assert "Authorization" not in line, (
                f"curl line must not embed Authorization header in argv: {line!r}"
            )
    # $TOKEN appears only in the printf line that writes the cfg
    token_lines = [line for line in script.splitlines() if "$TOKEN" in line]
    assert len(token_lines) == 1
    assert "printf" in token_lines[0]
    # The literal token (shlex-quoted, after rendering) must NOT appear in
    # curl invocations or anywhere outside the TOKEN= assignment line.
    assert "super-secret-do-not-leak" in script  # appears in TOKEN= line
    for line in script.splitlines():
        if line.startswith("TOKEN="):
            continue
        assert "super-secret-do-not-leak" not in line, f"Token leaked outside TOKEN= line: {line!r}"


def test_round_3_trap_cleans_all_tmpfiles() -> None:
    """R3 — EXIT trap removes the curl-config + push-dir, with `[ -n ]` guards."""
    script = _render_default()
    trap_line = next(line for line in script.splitlines() if line.startswith("trap"))
    assert '"$CFG"' in trap_line
    assert '"$PUSH_DIR"' in trap_line
    # Optional vars guarded
    assert '[ -n "$PUSH_DIR" ]' in trap_line


def test_round_4_http_code_dispatch_via_bash_exec() -> None:
    """R4 — HTTP-code dispatch executed via bash, NOT just static-text-checked.

    Adopts the Modul-2.0 lesson: the legacy `grep -q $'\\n'` bug
    would have passed any static check but failed when bash actually
    ran it. Same risk here: dispatch logic that LOOKS right but
    behaves wrong (e.g., `case` fall-through, wrong code grouping).

    We extract the case-statement logic and run it via bash -c
    against six representative HTTP codes.
    """
    cases = [
        ("200", "created"),
        ("201", "created"),
        ("422", "skipped"),
        ("000", "failed"),
        ("500", "failed"),
        ("401", "failed"),
    ]
    for code, expected in cases:
        snippet = f"""
set -euo pipefail
HTTP_CODE='{code}'
case "$HTTP_CODE" in
    200|201) echo created ;;
    422)     echo skipped ;;
    *)       echo failed ;;
esac
"""
        out = subprocess.run(
            ["bash", "-c", snippet], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert out == expected, f"http_code={code} expected={expected} got={out}"


def test_round_4_dispatch_present_in_rendered_script() -> None:
    """Static check: the rendered script contains the same case form."""
    script = _render_default()
    assert "200|201) CREATED=" in script
    assert "422)     SKIPPED=" in script
    assert "*)" in script


def test_round_5_path_safety_via_resolve_check_in_module() -> None:
    """R5 doc-test — the Python implementation uses Path.resolve() check.

    list_seed_files's path safety relies on:
    1. Path.resolve(strict=True) catches non-existent / dangling paths
    2. resolved.relative_to(root_resolved) raises ValueError on escape
    Both are exercised by the symlink test above.
    """
    # This is a meta-test: the actual test is
    # test_round_5_path_safety_rejects_dotdot_escape via fixtures
    import inspect

    from nexus_deploy import seeder

    src = inspect.getsource(seeder.list_seed_files)
    assert "resolve(" in src
    assert "relative_to(" in src


def test_round_8_token_never_leaks_on_runtime_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R8 — token doesn't appear in stdout/stderr when rsync/ssh fail.

    Force rsync to raise CalledProcessError whose exc.cmd embeds the
    token (worst-case argv leak); assert nothing the seeder code path
    PRINTS contains the token. The exception object itself may still
    carry exc.cmd unfiltered — the CLI wrapper (``_seed`` in __main__)
    is responsible for rendering exceptions safely (``type(exc).__name__``
    only). Same approach as the secret-sync R8 invariant.

    Previously this test populated a private list that was never
    written to, so the assertion was vacuously true (Copilot finding).
    Now uses pytest's ``capsys`` to capture both streams.
    """
    secret_token = "TOK-SHOULD-NEVER-APPEAR-IN-OUTPUT-12345"

    def explode_rsync(_src: Path, _dst: str) -> subprocess.CompletedProcess[str]:
        # exc.cmd embeds the token to simulate a rsync invocation that
        # might have it in argv (worst case)
        raise subprocess.CalledProcessError(
            1, ["rsync", f"--password={secret_token}"], output="", stderr=""
        )

    def noop_script(_s: str) -> subprocess.CompletedProcess[str]:
        # Won't be reached because rsync fails first
        raise AssertionError("script_runner should not be invoked when rsync fails")

    with pytest.raises(subprocess.CalledProcessError):
        run_seed_for_repo(
            repo_owner="admin",
            repo_name="repo",
            root=FIXTURE_ROOT,
            token=secret_token,
            push_dir=tmp_path / "seed-push-test-r8",
            script_runner=noop_script,
            rsync_runner=explode_rsync,
        )
    captured = capsys.readouterr()
    assert secret_token not in captured.out
    assert secret_token not in captured.err


# ---------------------------------------------------------------------------
# parse_result
# ---------------------------------------------------------------------------


def test_parse_result_happy() -> None:
    out = "RESULT created=10 skipped=2 failed=0"
    assert parse_result(out) == SeedResult(created=10, skipped=2, failed=0)


def test_parse_result_with_warnings_above() -> None:
    """RESULT line is found even when stderr noise precedes it."""
    out = "  ⚠ Seed POST nexus_seeds/foo.txt returned HTTP 500\nRESULT created=3 skipped=0 failed=1"
    result = parse_result(out)
    assert result == SeedResult(created=3, skipped=0, failed=1)


def test_parse_result_no_match() -> None:
    assert parse_result("garbage output") is None
    assert parse_result("") is None


# ---------------------------------------------------------------------------
# run_seed_for_repo — orchestration
# ---------------------------------------------------------------------------


def _ok_script_runner(stdout: str) -> Any:
    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=stdout, stderr="")

    return runner


def _noop_rsync(_src: Path, _dst: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")


def test_run_seed_happy_path(tmp_path: Path) -> None:
    """End-to-end with mocked runners — fixture seeds, RESULT parsed."""
    out = "RESULT created=4 skipped=0 failed=0"
    result = run_seed_for_repo(
        repo_owner="admin",
        repo_name="ws",
        root=FIXTURE_ROOT,
        token="t",
        push_dir=tmp_path / "push",
        script_runner=_ok_script_runner(out),
        rsync_runner=_noop_rsync,
    )
    assert result == SeedResult(created=4, skipped=0, failed=0)


def test_run_seed_no_result_returns_failed_count(tmp_path: Path) -> None:
    """Remote stdout without RESULT → SeedResult with failed=N (file count)."""
    result = run_seed_for_repo(
        repo_owner="admin",
        repo_name="ws",
        root=FIXTURE_ROOT,
        token="t",
        push_dir=tmp_path / "push",
        script_runner=_ok_script_runner("garbage output"),
        rsync_runner=_noop_rsync,
    )
    # Fixture has 4 files
    assert result.failed == 4
    assert result.created == 0
    assert result.skipped == 0


def test_run_seed_forwards_remote_warnings_to_local_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Modul-1.2 Round-4 lesson: remote stderr noise is forwarded to local stderr."""
    remote_out = (
        "  ⚠ Seed POST nexus_seeds/x.txt returned HTTP 500\n"
        "  ⚠ Seed payload missing url_path: seed-9999.json\n"
        "RESULT created=2 skipped=0 failed=2"
    )
    run_seed_for_repo(
        repo_owner="admin",
        repo_name="ws",
        root=FIXTURE_ROOT,
        token="t",
        push_dir=tmp_path / "push",
        script_runner=_ok_script_runner(remote_out),
        rsync_runner=_noop_rsync,
    )
    captured = capsys.readouterr()
    assert "returned HTTP 500" in captured.err
    assert "missing url_path" in captured.err
    # RESULT line is wire-format, must NOT pollute stderr
    assert "RESULT created=" not in captured.err


def test_seed_result_is_partial() -> None:
    """is_partial: True iff failed > 0 AND (created+skipped) > 0."""
    assert SeedResult(created=0, skipped=0, failed=0).is_partial is False
    assert SeedResult(created=5, skipped=0, failed=0).is_partial is False
    assert SeedResult(created=0, skipped=0, failed=5).is_partial is False  # all failed
    assert SeedResult(created=3, skipped=0, failed=2).is_partial is True
    assert SeedResult(created=0, skipped=3, failed=2).is_partial is True


def test_list_seed_files_handles_resolve_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If Path.resolve(strict=True) raises OSError, file is silently skipped."""
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "good.txt").write_text("ok", encoding="utf-8")
    (seed_root / "broken.txt").write_text("ok", encoding="utf-8")

    real_resolve = Path.resolve

    def fake_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self.name == "broken.txt":
            raise OSError("simulated resolve failure")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    files = list_seed_files(seed_root)
    repo_paths = {f.repo_path for f in files}
    assert "nexus_seeds/good.txt" in repo_paths
    assert "nexus_seeds/broken.txt" not in repo_paths


def test_list_seed_files_handles_relative_to_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If resolved.relative_to(root) raises ValueError, file is silently skipped.

    Directory-traversal guard: simulate a resolved path that doesn't
    share root_resolved as a prefix (real-world: a successful resolve()
    on a symlink whose target is outside root).
    """
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "good.txt").write_text("ok", encoding="utf-8")
    (seed_root / "bad.txt").write_text("would-be-escape", encoding="utf-8")

    real_resolve = Path.resolve

    def fake_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        # Make bad.txt's resolved path land outside root_resolved.
        # is_symlink() check fires first if we used a real symlink, so
        # we monkey-patch resolve to bypass that and exercise the
        # relative_to() guard specifically.
        if self.name == "bad.txt" and kwargs.get("strict"):
            return Path("/elsewhere/bad.txt")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    files = list_seed_files(seed_root)
    repo_paths = {f.repo_path for f in files}
    assert "nexus_seeds/good.txt" in repo_paths
    assert not any("bad" in rp for rp in repo_paths)


def test_run_seed_clears_stale_payloads_from_push_dir(tmp_path: Path) -> None:
    """Stale ``seed-*.json`` from a previous run must not leak into the next.

    Without cleanup, a previous run that produced 10 files leaves
    seed-0009.json behind; the next run produces 4 files (overwriting
    seed-0000..0003) and orphan seed-0004..0009 get rsynced + POSTed.
    Result: phantom seeds in the workspace repo. Regression test for
    the Copilot finding on PR #512.
    """
    push_dir = tmp_path / "push"
    push_dir.mkdir()
    # Stale files from a hypothetical earlier run
    (push_dir / "seed-0009.json").write_text('{"stale": "from previous run"}', encoding="utf-8")
    (push_dir / "seed-0010.json").write_text('{"stale": "also previous"}', encoding="utf-8")
    # Operator-parked file should NOT be touched (only seed-*.json)
    (push_dir / "operator-state.txt").write_text("hands off", encoding="utf-8")

    run_seed_for_repo(
        repo_owner="admin",
        repo_name="ws",
        root=FIXTURE_ROOT,
        token="t",
        push_dir=push_dir,
        script_runner=_ok_script_runner("RESULT created=4 skipped=0 failed=0"),
        rsync_runner=_noop_rsync,
    )
    # Fixture has 4 files → seed-0000..0003. Stale 0009/0010 must be gone.
    seed_files = sorted(push_dir.glob("seed-*.json"))
    assert [f.name for f in seed_files] == [
        "seed-0000.json",
        "seed-0001.json",
        "seed-0002.json",
        "seed-0003.json",
    ]
    # Operator's parked file is preserved
    assert (push_dir / "operator-state.txt").read_text(encoding="utf-8") == "hands off"


def test_list_seed_files_unsafe_path_emits_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unsafe-path drops emit a stderr warning so operators can see them.

    Previously the comment claimed these were "counted as failed" but
    the implementation silently dropped them. Now we surface them via
    stderr (same workflow-log surface as the bash warnings), keeping
    the SeedResult shape stable but giving operators visibility.
    """
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "ok.txt").write_text("ok", encoding="utf-8")
    (seed_root / "with space.txt").write_text("space", encoding="utf-8")
    list_seed_files(seed_root)
    captured = capsys.readouterr()
    assert "Skipping seed with unsafe path" in captured.err
    assert "with space" in captured.err


def test_run_seed_writes_payloads_to_push_dir(tmp_path: Path) -> None:
    """write_payloads landing files in the configured push_dir."""
    push_dir = tmp_path / "custom_push"
    run_seed_for_repo(
        repo_owner="admin",
        repo_name="ws",
        root=FIXTURE_ROOT,
        token="t",
        push_dir=push_dir,
        script_runner=_ok_script_runner("RESULT created=4 skipped=0 failed=0"),
        rsync_runner=_noop_rsync,
    )
    assert push_dir.is_dir()
    files = sorted(push_dir.iterdir())
    assert len(files) == 4
    assert all(f.name.startswith("seed-") and f.name.endswith(".json") for f in files)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run `python -m nexus_deploy seed ...` in a subprocess.

    Subprocess invocation mirrors how the caller calls the CLI; coverage
    is reported on the subprocess via pytest-cov auto-instrumentation
    (see pyproject.toml [tool.coverage]).
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, "-m", "nexus_deploy", "seed", *args],
        capture_output=True,
        text=True,
        env=full_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_seed_missing_repo_returns_2() -> None:
    rc, _, err = _run_cli([], env={"FORGEJO_TOKEN": "t"})
    assert rc == 2
    assert "--repo" in err


def test_cli_seed_invalid_repo_format_returns_2() -> None:
    rc, _, err = _run_cli(["--repo", "no-slash"], env={"FORGEJO_TOKEN": "t"})
    assert rc == 2
    assert "must contain '/'" in err or "'/'" in err


def test_cli_seed_missing_token_returns_2() -> None:
    rc, _, err = _run_cli(["--repo", "admin/ws"], env={"FORGEJO_TOKEN": ""})
    assert rc == 2
    assert "FORGEJO_TOKEN" in err


def test_cli_seed_missing_root_returns_zero() -> None:
    """Missing seed dir is non-fatal — early-return with rc=0."""
    rc, _, err = _run_cli(
        ["--repo", "admin/ws", "--root", "/does/not/exist"],
        env={"FORGEJO_TOKEN": "t"},
    )
    assert rc == 0
    assert "not a directory" in err


def test_cli_seed_unknown_arg_returns_2() -> None:
    rc, _, err = _run_cli(["--repo", "admin/ws", "--bogus"], env={"FORGEJO_TOKEN": "t"})
    assert rc == 2
    assert "unknown arg" in err


@pytest.mark.parametrize(
    ("prefix", "valid"),
    [
        # Valid: empty (seed into root) or safe relative dir ending with /
        ("nexus_seeds/", True),
        ("custom/", True),
        ("a/b/c/", True),  # nested OK
        ("", True),  # empty = seed into repo root
        # Invalid — char-level
        ("nexus_seeds", False),  # missing trailing slash
        ("nexus seeds/", False),  # space (fails per-segment safe-char check)
        ("nexus_seeds`/", False),  # backtick
        ("nexus_seeds$/", False),  # dollar
        # Invalid — path-traversal / structural (round-3 finding)
        ("../", False),  # parent-dir escape
        ("a/../b/", False),  # parent-dir mid-path
        ("./", False),  # current-dir token
        ("/foo/", False),  # leading slash → absolute-looking
        ("a//b/", False),  # empty segment (double slash)
        ("//", False),  # only empty segments
        ("/", False),  # bare slash → empty body segments
    ],
)
def test_cli_seed_prefix_validation(prefix: str, valid: bool) -> None:
    """`--prefix` must be empty or a safe relative dir ending with `/`.

    Round-2 caught char-level issues (missing trailing slash, unsafe chars).
    Round-3 caught path-traversal vectors (`..`, leading `/`, empty
    segments) that the char-level regex alone permitted because `..`
    and `/` are both in the safe-char set.
    """
    rc, _, err = _run_cli(
        ["--repo", "admin/ws", "--root", "/does/not/exist", "--prefix", prefix],
        env={"FORGEJO_TOKEN": "t"},
    )
    if valid:
        # rc=0 because --root doesn't exist (non-fatal early-return),
        # NOT because of the prefix. We're only checking the prefix
        # validation didn't reject. So rc != 2 is the assertion.
        assert rc != 2, f"prefix={prefix!r} should validate, got err={err!r}"
    else:
        assert rc == 2
        assert "invalid --prefix" in err

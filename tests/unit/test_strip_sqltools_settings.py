"""Tests for the one-time #593 migration script that strips
sqltools.* keys from a code-server settings.json.

Covers the atomicity properties (no half-write on interruption,
no truncation on malformed JSON) and the idempotency (no-op on
already-clean files or missing files).
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "stacks"
    / "code-server"
    / "scripts"
    / "strip-sqltools-settings.py"
)


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
    )


def test_strips_sqltools_keys_preserves_others(tmp_path: Path) -> None:
    """Happy path: sqltools.* keys are removed, every other key
    survives byte-for-byte (well, modulo JSON re-indenting)."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "editor.fontSize": 14,
                "sqltools.connections": [{"password": "leaked-pg-pw"}],
                "sqltools.useNodeRuntime": True,
                "workbench.colorTheme": "Default Dark+",
            }
        )
    )

    result = _run(settings)

    assert result.returncode == 0
    assert "Stripped sqltools.* keys" in result.stdout
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    assert "sqltools.useNodeRuntime" not in after
    assert after["editor.fontSize"] == 14
    assert after["workbench.colorTheme"] == "Default Dark+"


def test_no_sqltools_keys_is_noop(tmp_path: Path) -> None:
    """Idempotent: a clean settings.json triggers an exit-0 "nothing
    to do" log line, file mtime should not change."""
    settings = tmp_path / "settings.json"
    original = json.dumps({"editor.fontSize": 14})
    settings.write_text(original)
    mtime_before = settings.stat().st_mtime_ns

    result = _run(settings)

    assert result.returncode == 0
    assert "No sqltools" in result.stdout
    assert settings.read_text() == original
    assert settings.stat().st_mtime_ns == mtime_before, (
        "file was touched even though no work was needed"
    )


def test_missing_file_is_noop(tmp_path: Path) -> None:
    """Idempotent: a missing settings.json (fresh install) is a no-op
    exit 0, not a crash. The compose entrypoint runs this script
    unconditionally now (the `if [ -f settings.json ]` prefilter was
    dropped in PR #593 review round 11 — see commit 0e0efcb — because
    its bash equivalent conflated read-errors with no-match), so this
    branch is the script's primary guarantee that fresh containers
    don't see a Python traceback in their startup log."""
    result = _run(tmp_path / "does-not-exist.json")
    assert result.returncode == 0
    assert "not found" in result.stdout


def test_malformed_json_does_not_truncate_file(tmp_path: Path) -> None:
    """Critical guarantee: if settings.json is malformed JSON, the
    script must NOT truncate or modify it — the operator needs the
    intact corrupt file for debugging. Script exits 1 (visible failure)
    with a SECURITY WARNING on stderr."""
    settings = tmp_path / "settings.json"
    original = '{"editor.fontSize": 14, "sqltools.connections": [BROKEN'
    settings.write_text(original)

    result = _run(settings)

    assert result.returncode == 1
    assert "SECURITY WARNING" in result.stderr
    assert settings.read_text() == original, (
        "script truncated a malformed file when it should have left it alone"
    )


def test_atomic_rename_leaves_no_tmp_files_on_success(tmp_path: Path) -> None:
    """After a successful run, the target should be replaced and the
    temp file removed — no .settings.json.* artifacts left behind.

    The subprocess-success assertion is important: without it the
    test would pass even if the script crashed before creating any
    temp file (a vacuous green tick that hides regressions in the
    atomic-rename path itself)."""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"sqltools.connections": []}))

    result = _run(settings)

    assert result.returncode == 0, (
        f"script crashed before reaching the atomic-rename path: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    leftover_tmps = [p for p in tmp_path.iterdir() if p.name != "settings.json"]
    assert leftover_tmps == [], f"leftover temp file(s): {leftover_tmps}"


def test_jsonc_strip_preserves_urls_with_double_slash(tmp_path: Path) -> None:
    """Critical: the JSONC fallback must NOT mangle string values that
    contain '//' (e.g. URLs like 'https://example.com'). A naive regex
    that strips '//' anywhere in the document would corrupt those values.
    Regression guard for the string-aware state machine in
    _strip_jsonc — it must skip in-string '//'."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        """{
            // user note: link goes to upstream docs
            "docs.url": "https://example.com/path",
            "regex.pattern": "https?://[^/]+/.*",
            "sqltools.connections": [{"password": "leaked"}],
            "editor.fontSize": 14
        }
        """
    )

    result = _run(settings)

    assert result.returncode == 0, (
        f"JSONC fallback failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    # Both URL-like string values must survive intact.
    assert after["docs.url"] == "https://example.com/path"
    assert after["regex.pattern"] == "https?://[^/]+/.*"
    assert after["editor.fontSize"] == 14


def test_jsonc_strip_preserves_commas_inside_string_values(tmp_path: Path) -> None:
    """Critical: the trailing-comma stripper must NOT remove a comma
    that appears INSIDE a string literal, even when that comma is
    immediately followed by `]` or `}`. A naive regex like
    `,(\\s*[}\\]])` would rewrite the string value silently, which
    would either corrupt user data on disk or fall through to the
    SECURITY WARNING path leaving the leaked password in place.
    The state machine treats in-string commas as plain content."""
    settings = tmp_path / "settings.json"
    # The trigger for JSONC mode is a comment. Inside that file there
    # are two string values that end with `,]` and `,}` — both must
    # survive byte-for-byte.
    settings.write_text(
        """{
            // user comment so strict JSON parse fails
            "errMsg": "expected closing bracket — got ',]' instead",
            "tplFragment": "config block ends with ',}'",
            "sqltools.connections": [{"password": "leaked"}],
            "editor.fontSize": 14
        }
        """
    )

    result = _run(settings)

    assert result.returncode == 0, (
        f"JSONC fallback failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    assert after["errMsg"] == "expected closing bracket — got ',]' instead"
    assert after["tplFragment"] == "config block ends with ',}'"
    assert after["editor.fontSize"] == 14


def test_jsonc_strip_handles_trailing_comma_followed_by_inline_comment(
    tmp_path: Path,
) -> None:
    """Common VS Code JSONC pattern: a trailing comma followed by an
    inline `// comment` before the closing `}` or `]`. The state
    machine must strip the comment first (so the comma becomes
    truly trailing whitespace + `}`), THEN apply the trailing-comma
    rule. Order matters — if we did commas first, the `,` would not
    yet look trailing (a `// comment` is between it and the `}`)."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        """{
            "editor.fontSize": 14,
            "sqltools.connections": [
                {"name": "old-leaked", "password": "x"}, // legacy entry from #588
            ]
        }
        """
    )

    result = _run(settings)

    assert result.returncode == 0, (
        f"trailing-comma + inline-comment failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    assert after["editor.fontSize"] == 14


def test_jsonc_strip_handles_escaped_quotes_in_strings(tmp_path: Path) -> None:
    """The string-aware comment stripper must handle backslash-escaped
    quotes inside string values, so e.g. "say \\"hi\\"" doesn't end the
    string prematurely and let a following `//` look like a comment."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        r"""{
            // comment outside
            "greeting": "say \"hi\" // to the world",
            "sqltools.connections": [],
            "editor.fontSize": 14
        }
        """
    )

    result = _run(settings)

    assert result.returncode == 0
    after = json.loads(settings.read_text())
    assert after["greeting"] == 'say "hi" // to the world'
    assert "sqltools.connections" not in after
    assert after["editor.fontSize"] == 14


def test_strips_jsonc_with_line_and_block_comments(tmp_path: Path) -> None:
    """VS Code settings.json is JSONC — line + block comments + trailing
    commas are valid. Strict json.load() would fail, leaving the leaked
    password in the file. The script's JSONC fallback handles all three."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        """{
            // user's editor preference
            "editor.fontSize": 14,
            /* old SQLTools setup
               from before #593: */
            "sqltools.connections": [{"password": "leaked-pg-pw"}],
            "workbench.colorTheme": "Default Dark+",
        }
        """
    )

    result = _run(settings)

    assert result.returncode == 0, (
        f"JSONC fallback failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    assert after["editor.fontSize"] == 14
    assert after["workbench.colorTheme"] == "Default Dark+"


def test_strips_bare_sqltools_key(tmp_path: Path) -> None:
    """The bare 'sqltools' key is matched in addition to the dotted
    namespace. Regression guard for a future maintainer who reads the
    'sqltools.*' docstring and removes the `k == 'sqltools'` branch."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "sqltools": [{"password": "leaked-via-bare-key"}],
                "editor.fontSize": 14,
            }
        )
    )

    result = _run(settings)

    assert result.returncode == 0
    after = json.loads(settings.read_text())
    assert "sqltools" not in after
    assert after["editor.fontSize"] == 14


def test_preserves_unrelated_keys_that_share_sqltools_prefix(tmp_path: Path) -> None:
    """Regression: 'startswith(sqltools)' would have matched unrelated
    keys like 'sqltoolsBackup' or another extension's 'sqltoolsPreview',
    deleting user data. The matcher requires either an exact 'sqltools'
    or a 'sqltools.' prefix (the VS Code namespace convention)."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "sqltools.connections": [{"password": "leaked"}],
                "sqltoolsBackup": "user-data-must-survive",
                "sqltoolsPreview": {"keep": "me"},
                "editor.fontSize": 14,
            }
        )
    )

    result = _run(settings)

    assert result.returncode == 0
    after = json.loads(settings.read_text())
    assert "sqltools.connections" not in after
    assert after["sqltoolsBackup"] == "user-data-must-survive"
    assert after["sqltoolsPreview"] == {"keep": "me"}
    assert after["editor.fontSize"] == 14


def test_usage_error_when_path_missing(tmp_path: Path) -> None:
    """No argv[1] → exit 2 with a usage line on stderr (don't crash
    with a Python traceback that obscures the actual problem)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_preserves_file_after_replace(tmp_path: Path) -> None:
    """After atomic replace the file exists, is non-empty, and is
    valid JSON. (Sanity: catches a regression where the temp file
    was accidentally renamed onto itself or os.replace was misused.)"""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"sqltools.foo": 1, "other": 2}))

    _run(settings)

    assert settings.exists()
    after = json.loads(settings.read_text())
    assert after == {"other": 2}
    # Should still be a regular readable file
    mode = stat.S_IMODE(settings.stat().st_mode)
    assert mode & 0o400, f"file is unreadable: mode {oct(mode)}"

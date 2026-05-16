#!/usr/bin/env python3
"""One-time migration: remove any sqltools.* keys from a
code-server settings.json that survives from before #593.

Called from the compose entrypoint with the settings.json path as
argv[1]. Atomic: writes to a same-directory temp file then os.replace
so the target file is never half-written even if the process is
killed mid-execution (e.g. container OOM, sudden restart). The
target's previous content is fully preserved until rename succeeds.

Idempotent: if no sqltools.* keys are present, exits 0 with a
"nothing to do" log line and does not touch the file at all.

JSONC-tolerant: VS Code's settings.json is officially JSONC (JSON
with comments and trailing commas allowed). Python's json.load() is
strict — so before giving up we try a regex pre-pass that strips //
line comments, /* block */ comments, and trailing commas, then
retry. The output is always written as strict JSON (json.dump),
which is a slight behavioral change vs the original file but matches
how code-server itself rewrites the file when the user edits via
the Settings UI.

Why a separate script (instead of inline python3 -c in the
entrypoint): the atomic-write recipe is ~15 lines with try/except
cleanup. Cramming that into a bash `>`-folded YAML string is
unreadable and YAML quoting bugs are easy to introduce. A real
.py file is testable, lintable, and survives copy-paste edits.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile

# JSONC tolerance: strip `//` line comments, `/* ... */` block comments,
# and trailing commas before `]` or `}`. Naive regex (doesn't avoid
# matches inside string literals) — acceptable here because the worst
# case is JSONDecodeError on the retry, which falls through to the
# SECURITY WARNING path (no data loss). VS Code's own settings parser
# is similarly naive about strings-vs-comments at file scope.
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _parse_jsonc(text: str) -> dict:
    """Try strict json first; fall back to JSONC-stripped retry."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        stripped = _BLOCK_COMMENT.sub("", text)
        stripped = _LINE_COMMENT.sub("", stripped)
        stripped = _TRAILING_COMMA.sub(r"\1", stripped)
        return json.loads(stripped)  # may raise — caller handles


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: strip-sqltools-settings.py <settings.json>",
            file=sys.stderr,
        )
        return 2

    path = sys.argv[1]

    try:
        with open(path) as f:
            raw = f.read()
        data = _parse_jsonc(raw)
    except FileNotFoundError:
        print(f"[code-server] settings.json not found at {path} — nothing to strip")
        return 0
    except json.JSONDecodeError as exc:
        # Even the JSONC retry failed. Leave the file alone — don't
        # truncate a malformed settings.json, the operator needs to
        # see it intact for debugging. Failure-loud to stderr so it
        # shows up in `docker logs code-server`.
        print(
            f"[code-server] SECURITY WARNING: settings.json at {path} is not parseable as JSON or JSONC ({exc}) — sqltools strip skipped, leaked Postgres password may still be present. Operator action required.",
            file=sys.stderr,
        )
        return 1

    # Match keys in the SQLTools namespace AND the bare "sqltools" root
    # (e.g. "sqltools.connections", "sqltools.useNodeRuntime", and the
    # bare "sqltools" array that the #588 writer used). Does NOT match
    # unrelated keys that share the prefix without a dot (e.g. a
    # hypothetical user setting "sqltoolsBackup" or another extension's
    # "sqltoolsPreview") — those survive intact.
    sqltools_keys = [k for k in data if k == "sqltools" or k.startswith("sqltools.")]
    if not sqltools_keys:
        print("[code-server] No sqltools.* keys in settings.json — nothing to strip")
        return 0

    for k in sqltools_keys:
        data.pop(k)

    # Atomic write: temp file in the same directory (so os.replace is
    # truly atomic — cross-device renames raise EXDEV instead of being
    # silently translated to a non-atomic copy+delete, which is why
    # the temp file MUST live next to the target). Cleanup on failure.
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(
        dir=dir_,
        prefix=".settings.json.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print(f"[code-server] Stripped sqltools.* keys from settings.json: {sqltools_keys}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

Why a separate script (instead of inline python3 -c in the
entrypoint): the atomic-write recipe is ~15 lines with try/except
cleanup. Cramming that into a bash `>`-folded YAML string is
unreadable and YAML quoting bugs are easy to introduce. A real
.py file is testable, lintable, and survives copy-paste edits.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile


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
            data = json.load(f)
    except FileNotFoundError:
        print(f"[code-server] settings.json not found at {path} — nothing to strip")
        return 0
    except json.JSONDecodeError as exc:
        # Leave the file alone — don't truncate a malformed settings.json,
        # the operator needs to see it intact for debugging. Failure-loud
        # to stderr so it shows up in `docker logs code-server`.
        print(
            f"[code-server] SECURITY WARNING: settings.json at {path} is not valid JSON ({exc}) — sqltools strip skipped, leaked Postgres password may still be present. Operator action required.",
            file=sys.stderr,
        )
        return 1

    sqltools_keys = [k for k in data if k.startswith("sqltools")]
    if not sqltools_keys:
        print("[code-server] No sqltools.* keys in settings.json — nothing to strip")
        return 0

    for k in sqltools_keys:
        data.pop(k)

    # Atomic write: temp file in the same directory (so os.replace is
    # truly atomic — cross-device renames degrade to copy+delete and
    # break atomicity). Cleanup on failure.
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

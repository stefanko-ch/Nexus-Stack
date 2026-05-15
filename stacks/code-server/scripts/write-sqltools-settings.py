"""Write/merge the SQLTools Nexus-Postgres connection into the
code-server user settings file.

Invoked from the compose entrypoint when
``NEXUS_POSTGRES_ENABLED=1`` and ``POSTGRES_PASSWORD`` is non-empty.
Lives in a separate file (not inline ``python3 -c``) because YAML's
folded scalar ``>`` collapses newlines into spaces, which makes
embedding any multi-line Python (e.g. ``try`` / ``except``) inside
the compose entrypoint impossible.

Behavior:

1. Read the existing ``settings.json`` if present.
2. If parsing fails (corrupted / partial / non-dict root), fall back
   to ``{}`` rather than crashing — the entrypoint then can't get
   into a restart loop just because a student saved invalid JSON.
3. Replace ONLY the ``sqltools.connections`` key. Custom editor
   settings + other extensions' config under the same JSON root are
   preserved (merge, not overwrite).
4. Write back atomically (write tmp + os.replace) at mode 0o600 —
   the file contains a plain-text password.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

SETTINGS_PATH = "/home/coder/.local/share/code-server/User/settings.json"

CONNECTION = {
    "name": "Nexus Postgres",
    "driver": "PostgreSQL",
    "server": "postgres",
    "port": 5432,
    "database": "postgres",
    "username": "nexus-postgres",
    "askForPassword": False,
    "connectionTimeout": 30,
}


def _load_existing() -> dict:
    """Return the existing settings dict, or {} if anything goes wrong.

    Treats every failure mode (missing file, unreadable file, empty
    string, invalid JSON, non-dict root) the same way: start fresh.
    The merge that follows is non-destructive only for OTHER keys —
    we always own ``sqltools.connections``, so losing it on a parse
    error is fine.
    """
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    if not pw:
        # Entrypoint already guards on this; defensive double-check
        # so we never write an empty-password connection.
        print("write-sqltools-settings: POSTGRES_PASSWORD empty, skip", file=sys.stderr)
        return 1

    cfg = _load_existing()
    connection = dict(CONNECTION, password=pw)
    cfg["sqltools.connections"] = [connection]

    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings.", dir=os.path.dirname(SETTINGS_PATH))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Workspace-repo seed-loop.

Walks ``examples/workspace-seeds/`` and POSTs each file to the Forgejo
Contents API under the ``nexus_seeds/<path>`` prefix in the user's
workspace repo. Two callers (non-mirror mode → admin-owned repo,
mirror+user mode → user's fork) hit one CLI invocation parameterised
by ``--repo <owner>/<name>``.

Server-side curl loop (consistent with :mod:`infisical` +
:mod:`secret_sync`): the rendered bash runs over rsync'd JSON
payloads, so the Forgejo token transits via a remote ``--config``
tmpfile (NOT argv) and never reaches ``ps`` / CI logs / exception
messages.

Eight rounds of hardening preserved (one regression test per round in
``tests/unit/test_seeder.py``):

R1. ``set -euo pipefail`` first executable line in the rendered bash.
R2. Token via ``curl --config <tmpfile>`` (NOT argv) — same defence
    as infisical.py and Module 1.2 secret_sync.
R3. EXIT trap cleans push-dir + curl-config tmpfile, with ``[ -n ]``
    guards on optional vars.
R4. HTTP-code dispatch (200/201 → created, 422 → skipped, else →
    failed), exec'd-bash regression test (Modul-2.0 lessons).
R5. ``Path.resolve()`` rejects ``..``-escape from ``root``.
R6. Symlinks skipped (regular files only).
R7. File ordering deterministic (operators rely on it for log debug).
R8. Token never in stdout / stderr / exception messages.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from nexus_deploy import _remote

# Server-side Forgejo endpoint. Port 3202, NOT 3000: the forgejo
# stack's compose file maps host 3202 to the container's 3000.
# Hardcoded because that mapping is a convention of the stack, not a
# per-environment knob. (3201 belongs to git-proxy.)
_FORGEJO_BASE_URL = "http://localhost:3202"

# Server-side path where rsync uploads the payload tree and the curl
# loop reads from. Transient — removed by the EXIT trap. Mirrors
# infisical.py's _REMOTE_PUSH_DIR convention.
_REMOTE_PUSH_DIR = "/tmp/seed-push"  # noqa: S108 — server path, not credential

# Path-safety regex. Restricts file paths to a safe filesystem subset
# (ASCII alphanumerics + dot/dash/underscore/slash). Any character
# outside this set causes the file to be
# dropped from the SeedFile list with a stderr warning — it does NOT
# reach the remote loop and therefore does NOT show up in the remote
# RESULT failed= count. Defence in depth against shell-injection via
# filenames AND against directory-traversal.
_VALID_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# RESULT-line format. Same wire-format shape as the secret-sync
# runner (``RESULT key=value key=value ...``) so the parser can stay simple.
_RESULT_PATTERN = re.compile(
    r"^RESULT created=(?P<created>\d+) "
    r"skipped=(?P<skipped>\d+) "
    r"failed=(?P<failed>\d+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SeedFile:
    """One file to upload.

    ``repo_path`` is the unencoded path under the prefix
    (``nexus_seeds/kestra/flows/sample.yaml``). ``url_path`` is the
    per-segment URL-encoded form for the Forgejo Contents API URL
    (``nexus_seeds/kestra/flows/sample.yaml`` — no actual encoding
    needed for these chars, but special chars in segment names get
    properly escaped). ``content_b64`` is the file bytes base64-encoded
    in one line (no MIME-style 76-char wrapping — Forgejo's API expects
    raw base64).
    """

    repo_path: str
    url_path: str
    content_b64: str
    commit_message: str


@dataclass(frozen=True)
class SeedResult:
    """Counters parsed from the remote ``RESULT`` line.

    Mirrors the bash counters one-to-one. ``created`` includes both
    HTTP 201 (new file) and HTTP 200 (some Forgejo versions). ``skipped``
    is HTTP 422 (file already exists; user edits persist — #501
    contract). ``failed`` is anything the remote loop saw and could
    not classify as 200/201/422 — transport failures, 401/403 (bad
    token), 5xx, etc.

    Unsafe-path rejections happen LOCALLY in :func:`list_seed_files`
    before payloads are generated, so they never reach the remote loop
    and are NOT reflected here. Operators see those as ``⚠ Skipping
    seed with unsafe path:`` warnings on stderr alongside the bash
    warnings.
    """

    created: int
    skipped: int
    failed: int

    @property
    def is_partial(self) -> bool:
        """True if any file failed but at least one succeeded."""
        return self.failed > 0 and (self.created + self.skipped) > 0


# ---------------------------------------------------------------------------
# Pure-logic helpers — file-walk, path-safety, payload-construction.
# Each one is unit-testable without I/O.
# ---------------------------------------------------------------------------


def _is_safe_repo_path(path: str) -> bool:
    """Restrict repo paths to a safe ASCII filename subset."""
    return bool(_VALID_REPO_PATH_RE.fullmatch(path))


def _url_encode_path(path: str) -> str:
    """URL-encode each path segment, then join with ``/``.

    A full ``urllib.parse.quote(path)`` would NOT escape the segment
    delimiters, and would not produce the same encoding as
    ``jq @uri`` for edge-cases. Per-segment encoding is the safer
    convention.
    """
    return "/".join(quote(seg, safe="") for seg in path.split("/"))


def list_seed_files(root: Path, prefix: str = "nexus_seeds/") -> list[SeedFile]:
    """Walk ``root`` recursively, return SeedFiles sorted by ``repo_path``.

    Behaviour:
    - Symlinks are skipped (``Path.is_file()`` follows symlinks but we
      filter via ``Path.is_symlink()`` upfront — see R6).
    - Hidden files (starting with ``.``) are NOT excluded by default
      — ``.gitkeep`` is intentionally seeded.
    - ``..``-escape rejection via ``Path.resolve()`` comparison (R5).
    - Files whose computed ``repo_path`` violates
      ``_VALID_REPO_PATH_RE`` are dropped with a stderr warning. They
      do NOT appear in the SeedFile list and therefore don't show up
      in the remote ``RESULT failed=`` count — operators should
      cross-reference the warning lines if the deploy log shows fewer
      ``created`` than expected.

    Output is sorted by ``repo_path`` for deterministic ordering (R7).
    """
    if not root.is_dir():
        return []

    root_resolved = root.resolve()
    results: list[SeedFile] = []

    for local_path in sorted(root.rglob("*")):
        if local_path.is_symlink() or not local_path.is_file():
            continue

        # R5: reject `..`-escape. Path.resolve() collapses `..`, so we
        # compare the resolved path against the resolved root.
        try:
            local_resolved = local_path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        try:
            local_resolved.relative_to(root_resolved)
        except ValueError:
            continue

        rel = local_resolved.relative_to(root_resolved)
        repo_path = f"{prefix}{rel.as_posix()}"
        if not _is_safe_repo_path(repo_path):
            sys.stderr.write(f"  ⚠ Skipping seed with unsafe path: {repo_path}\n")
            continue

        content = base64.b64encode(local_path.read_bytes()).decode("ascii")
        results.append(
            SeedFile(
                repo_path=repo_path,
                url_path=_url_encode_path(repo_path),
                content_b64=content,
                commit_message=(
                    f"chore(seed): add {repo_path} from Nexus-Stack examples/workspace-seeds/"
                ),
            )
        )

    return sorted(results, key=lambda f: f.repo_path)


def encode_payloads(files: list[SeedFile]) -> dict[str, str]:
    """SeedFile → ``filename → JSON-text`` mapping for the push-dir.

    Filename format: ``seed-NNNN.json`` (zero-padded sequential index
    over the sorted list). Stable across re-runs because
    ``list_seed_files`` returns sorted-by-repo_path output.

    JSON shape per file: ``{"url_path", "content", "message"}``. The
    ``url_path`` field is metadata for the curl-loop (it builds the
    Forgejo URL from it); the actual POST body sent to Forgejo is just
    ``{"content", "message"}`` — extracted via ``jq`` in the rendered
    bash so we don't need to write two files per seed.
    """
    return {
        f"seed-{idx:04d}.json": json.dumps(
            {
                "url_path": f.url_path,
                "content": f.content_b64,
                "message": f.commit_message,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for idx, f in enumerate(files)
    }


# ---------------------------------------------------------------------------
# Bash rendering — produces the server-side script that
# `_remote.ssh_run_script` will exec via stdin.
# ---------------------------------------------------------------------------


def render_remote_loop(*, token: str, repo_owner: str, repo_name: str) -> str:
    """Render the remote bash that POSTs each seed-NNNN.json to Forgejo.

    All inputs are shlex-quoted; token reaches the server only via the
    rendered bash (sent via ssh stdin) and lands in a remote
    ``--config`` tmpfile (NOT argv).

    Loop:
      1. Write Authorization header to a tmpfile, chmod 600.
      2. For each ``$PUSH_DIR/seed-*.json``:
         - Extract ``url_path`` via jq.
         - POST ``{content, message}`` body to ``contents/<url_path>``.
         - Dispatch HTTP code: 200|201 → created, 422 → skipped,
           else → failed.
      3. Cleanup via EXIT trap.
      4. Emit RESULT line.
    """
    token_q = shlex.quote(token)
    owner_q = shlex.quote(repo_owner)
    repo_q = shlex.quote(repo_name)
    base_url_q = shlex.quote(_FORGEJO_BASE_URL)
    push_dir_q = shlex.quote(_REMOTE_PUSH_DIR)

    # The rendered bash uses curl --config + per-file POST + a
    # 200|201/422/other dispatch:
    #   - File walk + base64 + JSON build run in Python (locally),
    #     payloads arrive via rsync. The bash only loops + POSTs.
    #   - Token is shlex-quoted into the rendered bash (sent via ssh
    #     stdin), then written to a remote --config tmpfile.
    #   - HTTP-code dispatch is via bash `case`. Semantics pinned by
    #     an exec'd-bash regression test (R4).
    return f"""set -euo pipefail

TOKEN={token_q}
OWNER={owner_q}
REPO={repo_q}
BASE_URL={base_url_q}
PUSH_DIR={push_dir_q}

CFG=$(mktemp)
chmod 600 "$CFG"
trap 'rm -f "$CFG"; [ -n "$PUSH_DIR" ] && rm -rf "$PUSH_DIR"; true' EXIT
printf 'header = "Authorization: token %s"\\n' "$TOKEN" > "$CFG"

if ! command -v jq >/dev/null 2>&1; then
    echo "  ⚠ jq is not installed on the remote VM — seeder needs jq, install with: sudo apt-get install -y jq" >&2
    echo "RESULT created=0 skipped=0 failed=0"
    exit 0
fi

CREATED=0; SKIPPED=0; FAILED=0

# `nullglob` so an empty push-dir produces an empty loop (not a literal
# "$PUSH_DIR/seed-*.json" string that fails jq).
shopt -s nullglob
for f in "$PUSH_DIR"/seed-*.json; do
    URL_PATH=$(jq -r '.url_path' "$f")
    if [ -z "$URL_PATH" ] || [ "$URL_PATH" = "null" ]; then
        FAILED=$((FAILED+1))
        echo "  ⚠ Seed payload missing url_path: $(basename "$f")" >&2
        continue
    fi
    HTTP_CODE=$(jq -c '{{content, message}}' "$f" | curl -s -o /dev/null -w '%{{http_code}}' \\
        -X POST "$BASE_URL/api/v1/repos/$OWNER/$REPO/contents/$URL_PATH" \\
        --config "$CFG" \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null) || HTTP_CODE=000
    case "$HTTP_CODE" in
        200|201) CREATED=$((CREATED+1)) ;;
        422)     SKIPPED=$((SKIPPED+1)) ;;
        *)
            FAILED=$((FAILED+1))
            echo "  ⚠ Seed POST $URL_PATH returned HTTP $HTTP_CODE" >&2
            ;;
    esac
done

echo "RESULT created=$CREATED skipped=$SKIPPED failed=$FAILED"
"""


def parse_result(stdout: str) -> SeedResult | None:
    """Extract the ``RESULT`` line from remote stdout.

    Returns None if no parseable RESULT line exists (mirrors the
    same-shape parser in secret_sync.py).
    """
    match = _RESULT_PATTERN.search(stdout)
    if match is None:
        return None
    g = match.groupdict()
    return SeedResult(
        created=int(g["created"]),
        skipped=int(g["skipped"]),
        failed=int(g["failed"]),
    )


# ---------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------


ScriptRunner = Callable[[str], subprocess.CompletedProcess[str]]
RsyncRunner = Callable[[Path, str], subprocess.CompletedProcess[str]]


def write_payloads(push_dir: Path, payloads: dict[str, str]) -> None:
    """Write each filename → JSON-text mapping into push_dir.

    Stale ``seed-*.json`` files from previous invocations are removed
    first — without this, a run that produces fewer files than its
    predecessor (or renames them) would leave orphan payloads behind
    that get rsynced + POSTed on the next run. The rsync ``--delete``
    flag handles the remote side; we handle the local side here.

    Other files in push_dir (anything not matching ``seed-*.json``)
    are left alone in case the operator parks unrelated state there.
    """
    push_dir.mkdir(parents=True, exist_ok=True)
    for stale in push_dir.glob("seed-*.json"):
        stale.unlink()
    for name, body in payloads.items():
        (push_dir / name).write_text(body, encoding="utf-8")


def run_seed_for_repo(
    *,
    repo_owner: str,
    repo_name: str,
    root: Path,
    token: str,
    prefix: str = "nexus_seeds/",
    push_dir: Path | None = None,
    script_runner: ScriptRunner | None = None,
    rsync_runner: RsyncRunner | None = None,
) -> SeedResult:
    """Render → write payloads → rsync → exec → parse.

    On a missing/malformed RESULT line, returns ``SeedResult(created=0,
    skipped=0, failed=N)`` where N is the number of files we attempted
    to seed — the assumption being that none of them landed and the
    operator needs every file accounted for in the failure count.
    Diverges from secret_sync.py's defensive parse (which returns
    all-zeros) because here we have a known file count to attribute
    the failure to.

    ``script_runner`` / ``rsync_runner`` are dependency-injection
    seams for tests; production callers leave them None.
    """
    files = list_seed_files(root, prefix=prefix)
    payloads = encode_payloads(files)

    actual_push_dir = push_dir or Path("/tmp/seed-push")  # noqa: S108
    write_payloads(actual_push_dir, payloads)

    run_script = script_runner or (lambda s: _remote.ssh_run_script(s))
    run_rsync = rsync_runner or (lambda src, dst: _remote.rsync_to_remote(src, dst, delete=True))

    run_rsync(actual_push_dir, f"nexus:{_REMOTE_PUSH_DIR}/")

    script = render_remote_loop(token=token, repo_owner=repo_owner, repo_name=repo_name)
    completed = run_script(script)

    # Forward remote diagnostics to local stderr (Modul-1.2 Round-4
    # lesson: warnings about HTTP failures, missing jq, etc. must be
    # visible in the workflow log so operators can debug).
    for line in completed.stdout.splitlines():
        if not line.startswith("RESULT "):
            sys.stderr.write(line + "\n")

    result = parse_result(completed.stdout)
    if result is None:
        # No RESULT line — count as failure (rc=2 territory in the CLI).
        return SeedResult(created=0, skipped=0, failed=len(files))
    return result

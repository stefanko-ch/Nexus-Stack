"""Per-stack ``.infisical.env`` sync from Infisical.

Pulls every secret from every Infisical folder configured for a stack
and writes them to that stack's env-file on the server. One
parametrised :class:`StackTarget` covers all three supported stacks
(jupyter, marimo, kestra); the rendering layer is shared and executed
remotely via :func:`_remote.ssh_run_script` (script via stdin, NOT
argv, so the Infisical token can't leak through ``ps`` / CI logs /
exception messages).

The remote pipeline (curl + jq + sed + atomic-mv) is rendered as bash
because one SSH round-trip beats ~80 small HTTP round-trips for a
typical secret count. Eight rounds of hardening are preserved with
one regression test per round (see ``tests/unit/test_secret_sync.py``):

R1. ``set -euo pipefail`` inside heredoc — remote bash doesn't inherit.
R2. Credential transit (was base64-over-heredoc; now stdin via
    :func:`_remote.ssh_run_script` — no transit-layer encoding needed).
R3. Tmpfile cleanup via ``trap``.
R4. Two-stage jq validation per folder (shape check + extraction).
R5. Key-regex ``^[A-Za-z_][A-Za-z0-9_]*$``.
R6. Multi-line value guard (``\\n`` in decoded value → skip, log key only).
R7. Atomic write via same-dir ``mktemp`` + rename.
R8. Two outage-safety gates (``succeeded == 0`` and ``pushed == 0``)
    — both produce ``wrote=0`` and leave the existing file untouched.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from nexus_deploy import _remote

# Marker block delimiters. Operators rely on the literal greppable
# marker, and the legacy-env strip regex matches the literal prefix.
_END_MARKER = "# === END nexus-secret-sync ==="


# Server-side Infisical endpoint (same as `nexus_deploy.infisical`).
_INFISICAL_BASE_URL = "http://localhost:8070"

# Server-side path prefix for stack directories. Each stack lives at
# /opt/docker-server/stacks/<name>/ — convention enforced by the
# stack-rsync step earlier in the pipeline.
_REMOTE_STACKS_DIR = "/opt/docker-server/stacks"

# RESULT-line parser. Anchor at the start so a stray RESULT substring
# elsewhere in stderr/stdout can't false-match.
_RESULT_PATTERN = re.compile(
    r"^RESULT pushed=(?P<pushed>\d+) "
    r"skipped_name=(?P<skipped_name>\d+) "
    r"skipped_multi=(?P<skipped_multi>\d+) "
    r"failed=(?P<failed>\d+) "
    r"collisions=(?P<collisions>\d+) "
    r"succeeded=(?P<succeeded>\d+) "
    r"wrote=(?P<wrote>[01])$",
    re.MULTILINE,
)

# POSIX shell-identifier rules — only keys matching this regex can be
# emitted as env-var lines without breaking the parser.
_VALID_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class StackTarget:
    """Per-stack parameters for the Infisical secret-sync.

    Three stacks are supported:

    - **jupyter**, **marimo**: write dotenv-style ``KEY="<escaped-value>"``
      lines to ``.infisical.env`` (separate from ``.env``). The value
      is sed-escaped (``\\\\``→``\\\\\\\\``, ``"``→``\\\\"``) and double-
      quoted so dotenv parsers accept characters that would otherwise
      break the line; multi-line values are skipped earlier (their
      newlines couldn't survive a single-line shell-readable form).
      Restart via ``docker compose up -d <stack>`` on change.
      Hardened across the rounds of fixes tracked in #510.
    - **kestra**: write ``SECRET_<KEY>=<base64-value>`` lines to ``.env``
      directly — no quoting (base64 output is already safe for a
      single-line env-var) and no separate ``.infisical.env`` file.
      Force-recreate the container so Kestra's ``EnvVarSecretProvider``
      re-reads the SECRET_* env vars at process start.

    The render pipeline is shared; ``key_prefix``, ``use_base64_values``,
    ``env_file_basename``, ``legacy_env_file_basename``, and
    ``force_recreate`` parameterise the ~5 lines that differ between
    the two output formats.
    """

    name: str  # "jupyter" | "marimo" | "kestra" — paths + marker label.

    # Output-format parameters. Defaults match the original Jupyter/Marimo
    # behavior so existing call sites stay unchanged.
    key_prefix: str = ""  # "" for jupyter/marimo; "SECRET_" for kestra
    use_base64_values: bool = False  # False=plain-escaped, True=raw base64
    env_file_basename: str = ".infisical.env"  # ".env" for kestra
    # legacy_env_file_basename: separate file the sync used to write to
    # before #495 — stripped on each successful run so the new location
    # is the single source of truth. Set to ``None`` for stacks that
    # have no separate legacy file (kestra writes to ``.env`` directly,
    # no migration step needed).
    legacy_env_file_basename: str | None = ".env"
    # Kestra's EnvVarSecretProvider only loads SECRET_* on container
    # start — `compose up -d` alone won't pick them up if the .env hash
    # didn't change in compose's view. --force-recreate guarantees
    # the new env makes it into the JVM. Jupyter/Marimo use plain env
    # injection that takes effect on `up -d` without --force-recreate.
    force_recreate: bool = False

    @property
    def env_file(self) -> str:
        """Server-side path the sync writes to."""
        return f"{_REMOTE_STACKS_DIR}/{self.name}/{self.env_file_basename}"

    @property
    def legacy_env_file(self) -> str | None:
        """Pre-#495 location of the same block. Stripped after successful
        write. ``None`` for stacks where no separate legacy location
        ever existed (e.g. kestra)."""
        if self.legacy_env_file_basename is None:
            return None
        return f"{_REMOTE_STACKS_DIR}/{self.name}/{self.legacy_env_file_basename}"

    @property
    def compose_dir(self) -> str:
        """Where ``docker compose up -d <name>`` runs from on restart."""
        return f"{_REMOTE_STACKS_DIR}/{self.name}"

    @property
    def begin_marker(self) -> str:
        """Marker comment ABOVE the rendered block.

        Operators rely on the leading `# === BEGIN nexus-secret-sync`
        prefix to grep + identify the auto-generated section; the
        wording AFTER that prefix is just for human readers. Jupyter
        and Marimo carry the longer Infisical-attribution comment,
        Kestra uses a shorter form.
        """
        if self.name == "kestra":
            return (
                "# === BEGIN nexus-secret-sync (re-generated each spin-up; do not edit by hand) ==="
            )
        friendly = self.name.capitalize()
        return (
            f"# === BEGIN nexus-secret-sync (Infisical → {friendly} env, "
            "plaintext, regenerated each spin-up — do not edit by hand) ==="
        )


@dataclass(frozen=True)
class SyncResult:
    """Counters parsed from the remote ``RESULT`` line.

    Mirrors the bash counters one-to-one. ``wrote=False`` is the
    "no-touch on outage" signal — Gate 1 (no folder fetch succeeded)
    OR Gate 2 (zero usable secrets across all successful fetches)
    fired, and the existing ``.infisical.env`` was left alone.
    """

    pushed: int
    skipped_invalid_name: int
    skipped_multiline: int
    failed_folders: int
    collisions: int
    succeeded_folders: int
    wrote: bool

    @property
    def is_partial(self) -> bool:
        """True if the sync wrote a file but had failed-folder counts > 0.

        Maps to CLI rc=1 (caller warns + continues). Distinct from
        rc=2 (transport / unexpected exception → caller aborts).
        """
        return self.wrote and self.failed_folders > 0


# ---------------------------------------------------------------------------
# Pure-logic helpers — unit-testable in Python without an SSH round-trip.
# Each one has a matching invariant in test_secret_sync.py.
# ---------------------------------------------------------------------------


def is_safe_envfile_key(key: str) -> bool:
    """POSIX shell-identifier rule for env-file keys.

    Keys that fail this are skipped with `SKIPPED_NAME++`. Examples:
    ``FOO_BAR`` ok, ``1FOO`` rejected (leading digit), ``FOO-BAR``
    rejected (hyphen), ``FOO BAR`` rejected (space), ``""`` rejected.
    """
    return bool(_VALID_KEY_RE.fullmatch(key))


def has_multiline(value: str) -> bool:
    """Detect values that can't be carried portably in env-file format.

    Values containing ``\\n`` are skipped with `SKIPPED_MULTI++`. The
    log line emitted server-side names the KEY only, never the value
    (R6: don't leak secret bytes via the warning channel).
    """
    return "\n" in value


def escape_dotenv_value(value: str) -> str:
    r"""Apply dotenv-safe escapes to a secret value.

    Two replacements, in this order (order matters: backslash first
    so we don't double-escape the escapes from the quote-replacement):
        ``\\`` → ``\\\\``    (literal backslash → escaped backslash)
        ``"``  → ``\\"``     (literal quote → escaped quote)
    Multi-line values are filtered upstream by :func:`has_multiline`,
    so we don't need to escape literal newlines here.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Bash rendering — produces the exact server-side script that
# `_remote.ssh_run_script` will exec via stdin.
# ---------------------------------------------------------------------------


def render_remote_script(
    *,
    target: StackTarget,
    project_id: str,
    infisical_token: str,
    infisical_env: str,
    gitea_token: str = "",
) -> str:
    """Render the remote bash script for one stack's secret sync.

    All inputs are shlex-quoted into single-quoted bash strings — token
    + env values can't break out of the script no matter what they
    contain. The script is fed to ``ssh nexus bash -s`` via stdin
    (:func:`_remote.ssh_run_script`), so neither argv nor ``ps`` ever
    sees the secrets.
    """
    pid_q = shlex.quote(project_id)
    token_q = shlex.quote(infisical_token)
    env_q = shlex.quote(infisical_env)
    gtoken_q = shlex.quote(gitea_token)
    env_file_q = shlex.quote(target.env_file)
    # Legacy env-file is optional: kestra-style targets write to .env
    # directly with no separate legacy file. We render an empty string
    # (NOT a dummy path) so the bash branch can guard with [ -n ... ].
    legacy_q = shlex.quote(target.legacy_env_file or "")
    begin_marker_q = shlex.quote(target.begin_marker)
    end_marker_q = shlex.quote(_END_MARKER)
    folders_url_q = shlex.quote(f"{_INFISICAL_BASE_URL}/api/v1/folders")
    secrets_url_q = shlex.quote(f"{_INFISICAL_BASE_URL}/api/v3/secrets/raw")
    key_prefix_q = shlex.quote(target.key_prefix)

    # The legacy-block strip uses an anchored sed range delete:
    #   `/^# === BEGIN nexus-secret-sync/,/^# === END nexus-secret-sync/d`.
    # The match is on the fixed `# === BEGIN/END nexus-secret-sync`
    # prefix only — no per-stack interpolation — so no Python-side
    # regex escaping is needed. The variable parts of the marker text
    # (Jupyter / Marimo wording) sit AFTER the matched prefix and
    # only matter for the `printf` that writes the new block.
    return f"""set -euo pipefail

PID={pid_q}
ITOK={token_q}
INF_ENV={env_q}
GTOKEN={gtoken_q}
ENV_FILE={env_file_q}
LEGACY_ENV={legacy_q}
BEGIN_MARKER={begin_marker_q}
END_MARKER={end_marker_q}
FOLDERS_URL={folders_url_q}
SECRETS_URL={secrets_url_q}
# Kestra format toggles: KEY_PREFIX prepends to every appended key
# (empty for jupyter/marimo, "SECRET_" for kestra). USE_B64=1 writes
# the raw base64 value (kestra's EnvVarSecretProvider decodes); =0
# uses the plain-escaped form (jupyter/marimo expect plaintext at
# runtime via process env).
KEY_PREFIX={key_prefix_q}
USE_B64={"1" if target.use_base64_values else "0"}

CFG=$(mktemp)
SEEN=$(mktemp)
APPEND=$(mktemp)
NEW_BLOCK=$(mktemp)
TSV=$(mktemp)
# Optional tmpfiles — created later in conditional branches. Initialised
# empty so the trap can safely reference them on early-exit paths
# (jq-missing, outage-gates). Removal is guarded by a non-empty check
# inside the trap so we don't `rm -f ""`.
TMP_OUT=""
LEGACY_TMP=""
chmod 600 "$CFG" "$APPEND" "$NEW_BLOCK" "$TSV"
trap 'rm -f "$CFG" "$SEEN" "$APPEND" "$NEW_BLOCK" "$TSV"; [ -n "$TMP_OUT" ] && rm -f "$TMP_OUT"; [ -n "$LEGACY_TMP" ] && rm -f "$LEGACY_TMP"; true' EXIT
printf 'header = "Authorization: Bearer %s"\\n' "$ITOK" > "$CFG"

if ! command -v jq >/dev/null 2>&1; then
    echo "  ⚠ jq is not installed on the remote VM — Infisical sync needs jq, install with: sudo apt-get install -y jq" >&2
    echo "RESULT pushed=0 skipped_name=0 skipped_multi=0 failed=0 collisions=0 succeeded=0 wrote=0"
    exit 0
fi

PUSHED=0; SKIPPED_NAME=0; SKIPPED_MULTI=0; FAILED=0; COLLISIONS=0; SUCCEEDED=0; WROTE=0

FOLDERS_JSON=$(curl -sS --config "$CFG" --get \\
    --connect-timeout 5 --max-time 15 \\
    --data-urlencode "workspaceId=$PID" \\
    --data-urlencode "environment=$INF_ENV" \\
    "$FOLDERS_URL" || echo '{{}}')
FOLDERS=$(printf '%s' "$FOLDERS_JSON" | jq -r '.folders[]?.name' | LC_ALL=C sort || true)
FOLDERS=$(printf '%s\\n/\\n' "$FOLDERS")

while IFS= read -r FOLDER; do
    [ -z "$FOLDER" ] && continue
    if [ "$FOLDER" = "/" ]; then
        SECRET_PATH="/"; FOLDER_LABEL="<root>"
    else
        SECRET_PATH="/$FOLDER"; FOLDER_LABEL="$FOLDER"
    fi
    SECRETS_JSON=$(curl -sS --config "$CFG" --get \\
        --connect-timeout 5 --max-time 30 \\
        --data-urlencode "workspaceId=$PID" \\
        --data-urlencode "environment=$INF_ENV" \\
        --data-urlencode "secretPath=$SECRET_PATH" \\
        "$SECRETS_URL" || true)
    if ! printf '%s' "$SECRETS_JSON" | jq -e '.secrets | type == "array"' >/dev/null; then
        FAILED=$((FAILED+1))
        echo "  ⚠ Infisical fetch '$FOLDER_LABEL' returned bad shape, skipping" >&2
        continue
    fi
    if ! printf '%s' "$SECRETS_JSON" | jq -r '.secrets[]? | [.secretKey, (.secretValue | @base64)] | @tsv' > "$TSV"; then
        FAILED=$((FAILED+1))
        echo "  ⚠ jq TSV extraction failed for folder '$FOLDER_LABEL' — skipping" >&2
        continue
    fi
    SUCCEEDED=$((SUCCEEDED+1))
    while IFS=$'\\t' read -r KEY VALUE_B64; do
        [ -z "$KEY" ] && continue
        if ! printf '%s' "$KEY" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$'; then
            SKIPPED_NAME=$((SKIPPED_NAME+1)); continue
        fi
        VALUE=$(printf '%s' "$VALUE_B64" | base64 -d || true)
        # Multi-line guard. Bash glob match (NOT `grep -q $'\\n'`):
        # the legacy form processed input line-by-line where the
        # implicit line-terminator could match the pattern, so
        # every non-empty single-line value falsely triggered the
        # skip (resulting in only GITEA_TOKEN ever landing in
        # .infisical.env). bash's case glob compares the variable's
        # bytes directly and only matches genuine embedded newlines.
        #
        # GATED on USE_B64=0 (Jupyter/Marimo plain-text mode):
        # multi-line values can't survive a `KEY="value"` env-file
        # line without escaping, so we skip + warn. In USE_B64=1
        # mode (Kestra) the value transits as base64 and Kestra's
        # EnvVarSecretProvider decodes it server-side — multi-line
        # PEMs / certs / multi-line tokens flow through fine, which
        # matches the legacy Kestra-secret-sync behavior.
        if [ "$USE_B64" = "0" ]; then
            case "$VALUE" in
                *$'\\n'*)
                    SKIPPED_MULTI=$((SKIPPED_MULTI+1))
                    echo "  ⚠ Skipping multi-line secret '$KEY' (folder '$FOLDER_LABEL')" >&2
                    continue
                    ;;
            esac
        fi
        EXISTING=$(awk -F'\\t' -v k="$KEY" '$1 == k {{print $2; exit}}' "$SEEN")
        if [ -n "$EXISTING" ]; then
            COLLISIONS=$((COLLISIONS+1))
            echo "  ⚠ Key collision: '$KEY' in folder '$FOLDER_LABEL' shadowed by earlier value from '$EXISTING' (first-wins)" >&2
            continue
        fi
        printf '%s\\t%s\\n' "$KEY" "$FOLDER_LABEL" >> "$SEEN"
        if [ "$USE_B64" = "1" ]; then
            # Kestra: SECRET_<KEY>=<base64-value>. EnvVarSecretProvider
            # decodes server-side. Newlines / binary content survive
            # the env var via base64.
            printf '%s%s=%s\\n' "$KEY_PREFIX" "$KEY" "$VALUE_B64" >> "$APPEND"
        else
            # Jupyter/Marimo: <KEY>="<escaped-value>". Plain text at
            # runtime via process env; double-backslash + double-quote
            # escapes preserve dotenv-parser semantics.
            ESCAPED_VALUE=$(printf '%s' "$VALUE" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g')
            printf '%s%s="%s"\\n' "$KEY_PREFIX" "$KEY" "$ESCAPED_VALUE" >> "$APPEND"
        fi
        PUSHED=$((PUSHED+1))
    done < "$TSV"
done <<< "$FOLDERS"

if [ -n "$GTOKEN" ] && ! grep -qE "^${{KEY_PREFIX}}GITEA_TOKEN=" "$APPEND"; then
    if [ "$USE_B64" = "1" ]; then
        GTOKEN_B64=$(printf '%s' "$GTOKEN" | base64 | tr -d '\\n')
        printf '%sGITEA_TOKEN=%s\\n' "$KEY_PREFIX" "$GTOKEN_B64" >> "$APPEND"
    else
        ESCAPED_GTOKEN=$(printf '%s' "$GTOKEN" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g')
        printf '%sGITEA_TOKEN="%s"\\n' "$KEY_PREFIX" "$ESCAPED_GTOKEN" >> "$APPEND"
    fi
    PUSHED=$((PUSHED+1))
fi

if [ "$SUCCEEDED" -eq 0 ]; then
    echo "  ⚠ No Infisical folder fetch succeeded — leaving existing $ENV_FILE untouched" >&2
    echo "RESULT pushed=0 skipped_name=$SKIPPED_NAME skipped_multi=$SKIPPED_MULTI failed=$FAILED collisions=$COLLISIONS succeeded=0 wrote=0"
    exit 0
fi

if [ "$PUSHED" -eq 0 ]; then
    echo "  ⚠ Infisical returned $SUCCEEDED folder(s) but zero usable secrets — leaving existing $ENV_FILE untouched" >&2
    echo "RESULT pushed=0 skipped_name=$SKIPPED_NAME skipped_multi=$SKIPPED_MULTI failed=$FAILED collisions=$COLLISIONS succeeded=$SUCCEEDED wrote=0"
    exit 0
fi

{{
    printf '%s\\n' "$BEGIN_MARKER"
    # The separator is its own argument, NOT `-t=`. Ubuntu 26.04 ships
    # uutils rather than GNU coreutils, and its argument parser reads
    # everything after `=` as the option's value — so `-t=` arrives as
    # "separator is the empty string" and sort exits 2 with
    #   sort: separator must be exactly one character long: ''
    # Under `set -e` inside this block that killed the whole
    # secret-sync phase. GNU and BSD sort accept both spellings and
    # produce byte-identical output, so the space costs nothing.
    #
    # Not simply dropping `-t`/`-k`: plain line sort is NOT equivalent.
    # For keys where one is a prefix of another it differs — `A1=…`
    # sorts before `A=…` on the whole line but after it on the key.
    LC_ALL=C sort -t '=' -k1,1 "$APPEND"
    printf '%s\\n' "$END_MARKER"
}} > "$NEW_BLOCK"

[ -f "$ENV_FILE" ] || touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

TMP_OUT=$(mktemp -p "$(dirname "$ENV_FILE")" .infisical.env.XXXXXX)
chmod 600 "$TMP_OUT"
# Strip any existing block, then append the new one. Markers are
# interpolated as fixed strings so operator-edited content
# above/below the auto-generated block stays put.
sed '/^# === BEGIN nexus-secret-sync/,/^# === END nexus-secret-sync/d' "$ENV_FILE" > "$TMP_OUT"
cat "$NEW_BLOCK" >> "$TMP_OUT"
mv "$TMP_OUT" "$ENV_FILE"
chmod 600 "$ENV_FILE"
WROTE=1

# Legacy-strip step: only runs when the target declared a legacy
# location (jupyter/marimo). Kestra targets (LEGACY_ENV=="") skip
# this — they write directly to .env, no migration step needed.
if [ -n "$LEGACY_ENV" ] && [ -f "$LEGACY_ENV" ]; then
    LEGACY_TMP=$(mktemp -p "$(dirname "$LEGACY_ENV")" .env.XXXXXX)
    chmod 600 "$LEGACY_TMP"
    sed '/^# === BEGIN nexus-secret-sync/,/^# === END nexus-secret-sync/d' "$LEGACY_ENV" > "$LEGACY_TMP"
    mv "$LEGACY_TMP" "$LEGACY_ENV"
    # Clear the variable so the trap doesn't try to rm a path that
    # no longer exists (mv consumes the source). `rm -f` would tolerate
    # this anyway, but explicit > implicit.
    LEGACY_TMP=""
fi

echo "RESULT pushed=$PUSHED skipped_name=$SKIPPED_NAME skipped_multi=$SKIPPED_MULTI failed=$FAILED collisions=$COLLISIONS succeeded=$SUCCEEDED wrote=$WROTE"
"""


def parse_result(stdout: str) -> SyncResult | None:
    """Extract the ``RESULT`` line from remote stdout.

    Returns None if no parseable RESULT line exists; the caller maps
    that to the same warn-and-skip path as a fully-skipped sync.
    """
    match = _RESULT_PATTERN.search(stdout)
    if match is None:
        return None
    g = match.groupdict()
    return SyncResult(
        pushed=int(g["pushed"]),
        skipped_invalid_name=int(g["skipped_name"]),
        skipped_multiline=int(g["skipped_multi"]),
        failed_folders=int(g["failed"]),
        collisions=int(g["collisions"]),
        succeeded_folders=int(g["succeeded"]),
        wrote=g["wrote"] == "1",
    )


# ---------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------


# Type aliases for runner injection in tests.
ScriptRunner = Callable[[str], subprocess.CompletedProcess[str]]
CommandRunner = Callable[[str], subprocess.CompletedProcess[str]]


def run_sync_for_stack(
    target: StackTarget,
    *,
    project_id: str,
    infisical_token: str,
    infisical_env: str = "dev",
    gitea_token: str = "",
    host: str = "nexus",
    script_runner: ScriptRunner | None = None,
    command_runner: CommandRunner | None = None,
) -> SyncResult:
    """Render the remote script, exec it via stdin, parse the result.

    On ``wrote=True`` follows up with ``docker compose up -d <stack>``
    via :func:`_remote.ssh_run` (separate ssh-call so the restart's
    exit code can fail independently of the secret-write step).
    Restart failures surface via stderr but don't change the returned
    :class:`SyncResult` — the secret-sync itself was successful.

    ``host`` selects which ssh-config alias the remote calls run
    against; defaults to ``"nexus"`` for back-compat. Orchestrator
    passes its ``self.ssh_host`` so a non-default ``SSH_HOST_ALIAS``
    reaches the secret-sync + post-sync compose-up uniformly
    (PR #533 R7 #1; same plumbing pattern as PR #532 R2 #2 + R4 #1).

    ``script_runner`` and ``command_runner`` are dependency-injection
    seams for tests; production callers leave them None.

    Returns a :class:`SyncResult` with all counters zero + ``wrote=False``
    if the remote script produced no parseable RESULT line.
    """
    run_script = script_runner or (lambda s: _remote.ssh_run_script(s, host=host))
    run_cmd = command_runner or (lambda c: _remote.ssh_run(c, host=host))

    script = render_remote_script(
        target=target,
        project_id=project_id,
        infisical_token=infisical_token,
        infisical_env=infisical_env,
        gitea_token=gitea_token,
    )

    completed = run_script(script)
    # Forward remote diagnostics to the local terminal so the operator
    # sees per-folder warnings (bad-shape, jq TSV failure, multi-line
    # skips, key collisions, outage-gate explanations). The remote
    # script writes these to stderr but `_remote.ssh_run_script` uses
    # merge_stderr=True so they land in stdout alongside the RESULT
    # line. We strip RESULT (it's wire-format, not human-readable) and
    # forward everything else to local stderr.
    for line in completed.stdout.splitlines():
        if not line.startswith("RESULT "):
            sys.stderr.write(line + "\n")
    result = parse_result(completed.stdout)
    if result is None:
        # No RESULT line — return all-zeros. Caller (CLI) maps this
        # to a warn-and-skip path so a transient outage doesn't fail
        # the whole pipeline.
        return SyncResult(
            pushed=0,
            skipped_invalid_name=0,
            skipped_multiline=0,
            failed_folders=0,
            collisions=0,
            succeeded_folders=0,
            wrote=False,
        )

    if result.wrote:
        # Restart on change.
        # ``docker compose up -d <stack>`` recomputes the resolved-config
        # hash and recreates only when env_file content changed. Kestra
        # additionally needs ``--force-recreate`` because its
        # ``EnvVarSecretProvider`` only loads SECRET_* env vars at
        # process start, and a config-hash unchanged from compose's
        # view (e.g. when the SECRET_* values rotated but the file
        # length is identical) wouldn't otherwise trigger a recreate.
        force_flag = " --force-recreate" if target.force_recreate else ""
        restart_cmd = (
            f"cd {shlex.quote(target.compose_dir)} && "
            f"docker compose up -d{force_flag} {shlex.quote(target.name)}"
        )
        try:
            run_cmd(restart_cmd)
        except subprocess.CalledProcessError as exc:
            # Forward the captured docker-compose output so the operator
            # can debug image pulls / compose syntax / network errors.
            # exc.cmd is NOT printed (defence in depth: it carries the
            # literal argv even though the restart command doesn't
            # include secrets).
            sys.stderr.write(
                f"  ⚠ docker compose up -d {target.name} failed "
                f"(rc={exc.returncode}) — output follows:\n"
            )
            captured = exc.stdout or exc.stderr or ""
            for line in captured.splitlines():
                sys.stderr.write(f"      {line}\n")

    return result

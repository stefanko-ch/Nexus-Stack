"""Server bootstrap helpers run before the orchestrator's main loop.

Public surface:

* **``configure_ssh``** — render the ``Host nexus`` block in
  ``~/.ssh/config`` with the Cloudflare Access ProxyCommand. Atomic
  awk-equivalent dedup of any pre-existing block, mode 600 file
  permissions. Aborts (raises :class:`SetupError`) when no Service
  Token is provided — browser-login fallback is impossible in CI
  and we'd rather fail loudly than confuse operators with a hung
  ssh prompt.
* **``wait_for_service_token``** — linear-backoff retry loop
  (5/10/15/20/25s) for Service Token propagation in Cloudflare
  Access. Cloudflare needs ~10s to activate a freshly-rotated
  token; without the initial sleep + retries the first ssh
  attempt nearly always 401s on cold-start deploys.
* **``wait_for_ssh``** — connectivity loop with exponential timeout
  (5s for first 3 attempts, 10s for next 4, 15s thereafter, max 15
  retries). The ramp absorbs slow Hetzner cold-starts without
  converting them into a spurious hard failure.
* **``ensure_jq``** — idempotent ``apt-get install -y jq`` on the
  remote. Bootstrap for VMs that pre-date the cloud-init jq install
  (newer VMs have it baked in via ``tofu/stack/main.tf``); near-no-op
  on healthy VMs.
* **``ensure_rclone``** — idempotent ``apt-get install -y rclone``
  on the remote. MUST run before ``s3_restore.restore_from_s3``;
  without rclone the restore script's bucket-reachability probe
  fails (rc=127 → 2), and the legacy pre-Round-6 code path would
  have silently fresh-started → data loss on next teardown.
  See the function's own docstring for the historical incident.
* **``ensure_data_dirs``** — idempotent ``mkdir -p`` + ``chown`` on
  the Gitea + Dify bind-mount sources under ``/mnt/nexus-data/``.
  Gitea: ``gitea/{repos,lfs}`` (uid 1000) + ``gitea/db`` (uid 70).
  Dify: ``dify/db`` (uid 70 for postgres-alpine) + ``dify/redis``
  (uid 999 for redis-alpine) + ``dify/{storage,weaviate,plugins}``
  (mkdir only — those containers run as root). Called by the
  pipeline AFTER the filesystem half of ``restore_from_s3`` so
  rclone-written files (owned by the SSH user, i.e. root) get
  the ownership the containers expect. RFC 0001 cutover
  replacement for the chown half of the removed
  ``mount_persistent_volume``.
* **``setup_wetty_ssh_agent``** — provision the SSH key + agent
  socket inside the Wetty container so browser-launched shells can
  reach the host without prompting for credentials.

Two transports are used:

1. Local subprocess (``ssh``) for the readiness probes — same
   pattern as :class:`SSHClient.run` but called pre-tunnel, before
   any persistent SSHClient context exists.
2. Server-side bash via :func:`SSHClient.run_script` for ``jq``
   install + data-dir ownership, run from a caller-supplied
   SSHClient provided by the orchestrator.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nexus_deploy.ssh import SSHClient

# Default ssh-config path is resolved INSIDE :func:`configure_ssh`
# (not as a module-level constant) so HOME changes after import
# take effect — important for tests and CI runners that may
# redirect HOME mid-process. Round-4 PR #524 finding: the previous
# module-level constant locked the path at import time, contrary
# to the docstring's claim about call-time resolution.


class SetupError(Exception):
    """Raised for setup-phase errors not modelled by ``CalledProcessError``.

    Used for service-token-missing, max-retries-exhausted, and
    inconsistent-state cases. Subprocess-level failures still surface
    as :class:`subprocess.CalledProcessError` from the standard library.
    """


@dataclass(frozen=True)
class SSHConfigSpec:
    """Inputs for rendering the ``Host nexus`` ssh-config block.

    ``cf_client_id`` and ``cf_client_secret`` together form the
    Cloudflare Access Service Token. When BOTH are non-empty we
    emit the env-var-prefixed ProxyCommand variant that lets
    cloudflared authenticate without a browser. When EITHER is
    missing we raise :class:`SetupError` from :func:`configure_ssh`
    rather than emit the browser-login fallback — the deploy script
    runs in CI where browser login is impossible, and a missing
    token is a configuration error the operator must fix upstream.
    """

    ssh_host: str
    cf_client_id: str | None = None
    cf_client_secret: str | None = None
    host_alias: str = "nexus"
    identity_file: str = "~/.ssh/id_ed25519"

    @property
    def has_service_token(self) -> bool:
        return bool(self.cf_client_id and self.cf_client_secret)


@dataclass(frozen=True)
class SSHReadinessResult:
    """Outcome of a readiness probe loop.

    ``last_error`` carries the captured stderr tail (truncated to
    2000 chars, tail-preserving — same pattern as RsyncResult in
    stack_sync.py Round-2). Used both for diagnostics on success
    (mostly empty) and for the operator log on max-retries-exhausted.
    """

    succeeded: bool
    attempts: int
    last_error: str = ""


@dataclass(frozen=True)
class WettyAgentResult:
    """Outcome of :func:`setup_wetty_ssh_agent`. Tracks 5 idempotent
    steps — re-runs that find nothing to do still return
    successfully with the corresponding flag set to ``False``.

    Only the rendered server-side script knows whether each step ran
    or was a no-op; the result line is parsed back into this
    dataclass for the workflow log + tests.
    """

    keypair_generated: bool  # ssh-keygen ran (False = key already existed)
    pubkey_added: bool  # appended to authorized_keys (False = already present)
    agent_started: bool  # ssh-agent forked (False = socket present + responsive)
    key_added_to_agent: bool  # ssh-add ran (False = key fingerprint already loaded)
    auth_sock_written: bool  # SSH_AUTH_SOCK= written to wetty .env (always True on success)


# VolumeMountResult — REMOVED in RFC 0001 cutover. The
# mount_persistent_volume helper that returned this is gone;
# /mnt/nexus-data is now seeded by s3_restore from R2, and the
# ownership-fixup half of the old mount step lives in
# ensure_data_dirs below.


# ---------------------------------------------------------------------------
# Pure logic — render + dedup helpers.
# ---------------------------------------------------------------------------


def render_ssh_config_block(spec: SSHConfigSpec) -> str:
    """Render the ``Host nexus`` block as a single trailing-newline
    ssh-config snippet.

    Caller must pre-validate Service Token presence — this function
    will happily render a no-token block (matches the legacy
    fallback path), but :func:`configure_ssh` rejects that case
    upstream.
    """
    lines = [
        "",
        f"Host {spec.host_alias}",
        f"  HostName {spec.ssh_host}",
        "  User root",
        f"  IdentityFile {spec.identity_file}",
        "  IdentitiesOnly yes",
    ]
    if spec.has_service_token:
        # ProxyCommand uses the `env VAR=val cmd` form (Round-2 PR
        # #524 finding). The legacy `bash -c 'VAR=val cmd'` form
        # interpolated raw token values inside single quotes — a
        # token containing a single quote (or shell metacharacter)
        # would either break the resulting ssh-config or, worse,
        # change the executed command. Cloudflare Service Token IDs
        # are practically always alphanumeric+UUID-like in current
        # spec, but defence in depth: we shlex-quote the values so
        # the rendered line stays safe regardless of future
        # token-format changes.
        #
        # `env` is a real binary that takes argv-form `KEY=value`
        # pairs (no shell parsing of the assignments) and execs the
        # rest of argv as a command. ssh's ProxyCommand is parsed
        # by /bin/sh, but each whitespace-separated argv after sh's
        # tokenization reaches `env` as a single string — so
        # shlex.quote on the value handles the shell layer, and env
        # consumes the result without re-parsing.
        id_q = shlex.quote(spec.cf_client_id or "")
        secret_q = shlex.quote(spec.cf_client_secret or "")
        proxy = (
            f"ProxyCommand env "
            f"TUNNEL_SERVICE_TOKEN_ID={id_q} "
            f"TUNNEL_SERVICE_TOKEN_SECRET={secret_q} "
            f"cloudflared access ssh --hostname %h"
        )
    else:
        proxy = "ProxyCommand cloudflared access ssh --hostname %h"
    lines.append(f"  {proxy}")
    lines.append("")  # trailing newline so a subsequent block starts cleanly
    return "\n".join(lines)


def strip_existing_block(config_text: str, host_alias: str) -> str:
    """Remove the existing ``Host <alias>`` block from a config text.

    Matches the legacy awk's behaviour: skip starting at ``Host
    <alias>`` line, stop skipping at the next ``Host `` line (which
    is preserved). Idempotent on configs that don't contain the
    block. Unlike the legacy awk, normalizes the result so we never
    leave more than one consecutive blank line at a boundary —
    important when the surrounding bytes are diffed against a
    snapshot.
    """
    out_lines: list[str] = []
    skip = False
    target = f"Host {host_alias}"
    for raw_line in config_text.splitlines():
        stripped = raw_line.strip()
        if stripped == target:
            skip = True
            continue
        # Re-encounter any other `Host ` line ends the skip BEFORE
        # we consume that line — same as the awk: `/^Host / && skip
        # { skip=0 }` runs on the boundary line, then `!skip { print }`
        # prints it.
        if skip and stripped.startswith("Host "):
            skip = False
        if not skip:
            out_lines.append(raw_line)
    # Collapse trailing blanks but preserve one (POSIX text-file convention).
    while len(out_lines) > 1 and out_lines[-1] == "" and out_lines[-2] == "":
        out_lines.pop()
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Side-effect functions
# ---------------------------------------------------------------------------


def configure_ssh(
    spec: SSHConfigSpec,
    *,
    ssh_config_path: Path | None = None,
) -> None:
    """Atomically write/replace the ``Host nexus`` block in ssh-config.

    Algorithm:
    1. Ensure ``~/.ssh`` exists.
    2. Read existing config (empty string if missing).
    3. ``strip_existing_block`` to remove any prior ``Host nexus``.
    4. Append the freshly-rendered block.
    5. Atomic replace via same-dir mktemp + ``os.replace``, mode 0o600.

    Raises :class:`SetupError` when ``spec`` carries no Service Token
    — browser-login is impossible in CI, so failing loudly here beats
    the hung ssh prompt operators would otherwise see.
    """
    if not spec.has_service_token:
        raise SetupError(
            "configure_ssh: Cloudflare Access Service Token "
            "(CF_ACCESS_CLIENT_ID + CF_ACCESS_CLIENT_SECRET) is required. "
            "Browser-login fallback is not supported in CI deployments.",
        )
    # Path.home() resolved here, NOT as a module-level constant —
    # so HOME changes after import (tests, CI scaffolding) take
    # effect immediately. Round-4 PR #524 fix.
    target = ssh_config_path if ssh_config_path is not None else Path.home() / ".ssh" / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    cleaned = strip_existing_block(existing, spec.host_alias)
    new_block = render_ssh_config_block(spec)
    final = (cleaned.rstrip() + "\n" + new_block) if cleaned.strip() else new_block
    # Atomic same-dir tempfile.mkstemp + os.replace (Round-2 PR #524
    # finding): mkstemp gives us a unique name + O_EXCL semantics so
    # we can never collide with a concurrent run, and the kernel
    # creates the file atomically with the file descriptor we hold —
    # no symlink-attack window on a pre-existing path. We then
    # explicitly fchmod to 0o600 to enforce permissions regardless
    # of umask (mkstemp defaults to 0o600 on POSIX, but we belt-and-
    # suspenders).
    import tempfile as _tempfile

    fd, tmp_str = _tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_str)
    fd_owned_by_caller = True
    try:
        # fchmod must run before fdopen takes ownership of the fd.
        # If it raises (e.g. read-only filesystem on the tmp dir),
        # we still own the fd and must close it ourselves to avoid
        # an fd leak across long-running test runs / processes
        # (Round-3 PR #524 finding).
        try:
            os.fchmod(fd, 0o600)
        except Exception:
            os.close(fd)
            fd_owned_by_caller = False
            raise
        # Ownership transfers to the file object below; closing the
        # context manager on success or via the outer except's
        # bubble-up path closes the fd.
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            fd_owned_by_caller = False
            f.write(final)
        tmp_path.replace(target)
    except Exception:
        # Cleanup the tmp file on any write failure; bubble up.
        # If we still own the fd (mkstemp succeeded but every
        # subsequent step before fdopen failed), close it.
        if fd_owned_by_caller:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path.exists():
            tmp_path.unlink()
        raise


# Subprocess seam for testing — production calls subprocess.run, tests
# inject a callable that scripts the retry sequence.
SSHProbeRunner = Callable[[str, float], subprocess.CompletedProcess[str]]


def _default_ssh_probe(host_alias: str, timeout_s: float) -> subprocess.CompletedProcess[str]:
    """Run ``ssh <alias> 'echo ok'`` with a hard ConnectTimeout.

    No ``check=True`` — caller inspects the returncode and decides
    success/retry. ``BatchMode=yes`` ensures we never block waiting
    for an interactive prompt (which would be a CI hang); the loop
    is the only retry mechanism.
    """
    return subprocess.run(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"ConnectTimeout={int(timeout_s)}",
            "-o",
            "BatchMode=yes",
            host_alias,
            "echo ok",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def wait_for_service_token(
    host_alias: str = "nexus",
    *,
    max_retries: int = 6,
    initial_wait_s: float = 10.0,
    backoff_step_s: float = 5.0,
    probe_runner: SSHProbeRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SSHReadinessResult:
    """Poll ssh-with-Service-Token until success or max_retries hit.

    Cloudflare Access needs a few seconds to activate a freshly
    issued Service Token; the initial sleep + linear-backoff loop
    (5/10/15/20/25s = `backoff_step_s` * retry-index) absorbs that
    propagation window without false-failing the deploy.

    ``sleep`` is injectable so tests can fast-forward without
    actually waiting 50+ seconds.
    """
    runner = probe_runner if probe_runner is not None else _default_ssh_probe
    sleep(initial_wait_s)
    last_error = ""
    for attempt in range(1, max_retries + 1):
        completed = runner(host_alias, 15.0)
        if completed.returncode == 0:
            return SSHReadinessResult(succeeded=True, attempts=attempt, last_error="")
        last_error = (completed.stderr or completed.stdout or "")[-2000:].rstrip()
        if attempt < max_retries:
            sleep(backoff_step_s * attempt)
    return SSHReadinessResult(succeeded=False, attempts=max_retries, last_error=last_error)


def wait_for_ssh(
    host_alias: str = "nexus",
    *,
    max_retries: int = 15,
    probe_runner: SSHProbeRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SSHReadinessResult:
    """Poll ssh-readiness with exponential timeout ramp.

    Timeout schedule: 5s for the first 3 attempts, 10s for attempts
    4-7, 15s for the rest (the sleep between attempts matches the
    timeout). The ramp absorbs slow Hetzner cold-starts without
    converting them into a spurious hard failure. PR #524 R2 #1
    fix: the boundary checks are ``< 4`` / ``< 8`` so retries 1-3
    all stay at 5s before bumping — a previous version used
    ``< 3`` / ``< 7`` which bumped one attempt too early.
    """
    runner = probe_runner if probe_runner is not None else _default_ssh_probe
    last_error = ""
    for attempt in range(1, max_retries + 1):
        if attempt < 4:
            timeout_s = 5.0
        elif attempt < 8:
            timeout_s = 10.0
        else:
            timeout_s = 15.0
        completed = runner(host_alias, timeout_s)
        if completed.returncode == 0:
            return SSHReadinessResult(succeeded=True, attempts=attempt, last_error="")
        last_error = (completed.stderr or completed.stdout or "")[-2000:].rstrip()
        if attempt < max_retries:
            sleep(timeout_s)
    return SSHReadinessResult(succeeded=False, attempts=max_retries, last_error=last_error)


def ensure_jq(ssh: SSHClient) -> bool:
    """Install ``jq`` on the remote if not already present.

    Returns ``True`` if ``apt-get install`` actually ran (legacy VM
    bootstrap), ``False`` if the binary was already there (modern
    VMs that have jq baked into cloud-init).

    Raises :class:`subprocess.CalledProcessError` if the install
    fails (caller — orchestrator — maps to red-abort: SFTPGo +
    Kestra register-flow blocks rely on jq, deploy can't continue
    without it).
    """
    check = ssh.run("command -v jq", check=False)
    if check.returncode == 0:
        return False
    install = ssh.run(
        "sudo apt-get update -qq >/dev/null && sudo apt-get install -y -qq jq >/dev/null",
        check=True,
    )
    _ = install
    return True


def ensure_rclone(ssh: SSHClient) -> bool:
    """Install ``rclone`` on the remote if not already present.

    Returns ``True`` if ``apt-get install`` actually ran (fresh VM
    or rebuild), ``False`` if the binary was already there.

    Why this matters — and why it MUST run before
    :func:`s3_restore.restore_from_s3` in the pipeline:

    Pre-RFC-0001 the rendered restore script did ``if ! rclone lsf
    .../latest.txt``. If rclone wasn't installed, that branch
    evaluated as ``!127 == true`` and the script silently exited 0
    with a "fresh-start: no snapshot in S3" message. Operationally:
    every spinup that touched a brand-new VM would *appear* to
    fresh-start (because rclone was missing), and the next teardown
    would happily snapshot the empty local state OVER any real R2
    data — silent data loss.

    Round 6 of PR #555 added a bucket-reachability probe that turns
    this into a loud rc=2, so the loop now FAILS instead of corrupting.
    But the right fix is to ensure rclone is actually installed
    BEFORE the probe runs, which is what this helper does.

    Raises :class:`subprocess.CalledProcessError` on install failure.

    Whatever the distro repo carries is fine, and the restore script is
    written not to care. Ubuntu 24.04 shipped rclone 1.60.1, old enough
    that ``rclone lsf`` returned rc=0 with empty stdout for a missing
    object where newer versions return non-zero; 26.04 carries a newer
    one. ``s3_persistence.render_restore_script`` therefore lists the
    ``snapshots/`` prefix and greps the listing for ``latest.txt``
    rather than probing the object directly, so a missing snapshot is
    an absent line rather than an exit code that differs by version.
    """
    check = ssh.run("command -v rclone", check=False)
    if check.returncode == 0:
        return False
    install = ssh.run(
        "sudo apt-get update -qq >/dev/null && sudo apt-get install -y -qq rclone >/dev/null",
        check=True,
    )
    _ = install
    return True


# ---------------------------------------------------------------------------
# Data-dir ownership — RFC 0001 cutover replacement for the chown
# half of the removed mount_persistent_volume helper.
#
# The Hetzner block volume that used to back /mnt/nexus-data is gone
# (see tofu/control-plane/main.tf for the rationale). Data now lives
# on the server's local SSD, seeded by s3_restore from R2. rclone
# writes files as the SSH user (root); the gitea + postgres
# containers expect uid 1000:1000 and 70:70 respectively, so we
# recursively chown after every restore.
# ---------------------------------------------------------------------------


_ENSURE_DATA_DIRS_SCRIPT = """set -euo pipefail

MOUNT_POINT=/mnt/nexus-data

# --- Gitea bind-mount sources -------------------------------------
# gitea-app container runs as uid 1000; bundled gitea-db (postgres-
# alpine) as uid 70. Both need write access to their bind sources,
# so we recursively chown after every restore (rclone writes files
# as the SSH user, i.e. root).
mkdir -p "$MOUNT_POINT/gitea/repos" "$MOUNT_POINT/gitea/lfs" "$MOUNT_POINT/gitea/db"
chown -R 1000:1000 "$MOUNT_POINT/gitea/repos" "$MOUNT_POINT/gitea/lfs"
chown -R 70:70 "$MOUNT_POINT/gitea/db"

# --- Dify bind-mount sources --------------------------------------
# dify-db is postgres:15-alpine (uid 70). dify-redis is redis:6-
# alpine which uses uid 999. The other three Dify mounts (storage,
# weaviate, plugins) run as root inside the container by default —
# we still mkdir them so Docker doesn't auto-create them under a
# different parent's perms, but no chown needed.
#
# All 5 paths on one mkdir line: avoids the Python-vs-bash
# backslash-line-continuation confusion that comes up in code
# review (Python `\\` in a triple-quoted string → single literal
# backslash → bash line continuation; technically correct but
# easy to misread).
mkdir -p "$MOUNT_POINT/dify/db" "$MOUNT_POINT/dify/redis" "$MOUNT_POINT/dify/storage" "$MOUNT_POINT/dify/weaviate" "$MOUNT_POINT/dify/plugins"
chown -R 70:70 "$MOUNT_POINT/dify/db"
chown -R 999:999 "$MOUNT_POINT/dify/redis"

echo "  ensured data-dir ownership under $MOUNT_POINT/{gitea,dify}" >&2
"""


def ensure_data_dirs(ssh: SSHClient) -> None:
    """Idempotent ``mkdir -p`` + ``chown -R`` of the Gitea + Dify
    bind-mount sources under ``/mnt/nexus-data/``.

    Called by the pipeline AFTER ``s3_restore.restore_from_s3`` —
    rclone-restored files land owned by the SSH user (root), but
    the various containers run as non-root UIDs and expect ownership
    on their bind-mount sources:

    * Gitea app (uid 1000): ``gitea/repos``, ``gitea/lfs``
    * Gitea bundled postgres (uid 70): ``gitea/db``
    * Dify postgres (uid 70): ``dify/db``
    * Dify redis (uid 999): ``dify/redis``
    * Dify storage / weaviate / plugins: container runs as root,
      ``mkdir`` only (no chown — Docker would otherwise auto-create
      the path with whatever the parent dir owner is).

    No-op on a fresh-start spinup (rclone wrote nothing); idempotent
    on a populated dir (chown -R is fine to re-run). Raises
    :class:`subprocess.CalledProcessError` if the remote script fails
    — that's a hard failure: a stack that comes up with mis-owned
    data dirs will misbehave silently, far harder to debug than a
    fail-loud abort here.

    The remote script emits a single ``ensured data-dir ownership
    under /mnt/nexus-data`` line to stdout on success. Forward that
    to local stderr so operators see the confirmation in the
    workflow log (same pattern as :func:`s3_restore.restore_from_s3`).
    """
    completed = ssh.run_script(_ENSURE_DATA_DIRS_SCRIPT, check=True)
    # Forward server-side log lines to local stderr so the
    # confirmation written by the script actually reaches the
    # workflow log. Without this, the echo in
    # ``_ENSURE_DATA_DIRS_SCRIPT`` would be lost — the docstring
    # there implies operators see it.
    for line in completed.stdout.splitlines():
        sys.stderr.write(line + "\n")


# ---------------------------------------------------------------------------
# Wetty SSH-Agent setup — bootstraps the SSH key pair + agent socket
# Wetty needs to log into the host as the same user that runs the
# docker daemon.
# ---------------------------------------------------------------------------


_WETTY_RESULT_RE = re.compile(
    r"^RESULT_WETTY"
    r" keypair_generated=(?P<keypair_generated>[01])"
    r" pubkey_added=(?P<pubkey_added>[01])"
    r" agent_started=(?P<agent_started>[01])"
    r" key_added_to_agent=(?P<key_added_to_agent>[01])"
    r" auth_sock_written=(?P<auth_sock_written>[01])$",
    re.MULTILINE,
)


def render_wetty_agent_script(
    *,
    key_path: str = "/root/.ssh/id_ed25519_wetty",
    key_comment: str = "wetty-auto-generated",
    agent_socket: str = "/tmp/ssh-agent/agent.sock",  # noqa: S108 — server-side path
    wetty_env_file: str = "/opt/docker-server/stacks/wetty/.env",
) -> str:
    """Render the server-side bash that idempotently bootstraps the
    ed25519 key pair, ssh-agent socket, and SSH_AUTH_SOCK injection
    Wetty needs to log into the host.

    The script does six numbered steps; only five of them produce a
    0/1 flag in the final RESULT line (step 1 is a precondition that
    always runs and is not reflected in the result):

    1. mkdir + chmod 700 ``~/.ssh`` (silent precondition — not in the
       RESULT line).
    2. ssh-keygen -t ed25519 the key pair if absent. Fail-fast on a
       non-zero ssh-keygen exit OR missing output files (would
       otherwise produce a misleading ``keypair_generated=1`` while
       downstream steps fail silently). → ``keypair_generated``.
    3. Append the public key to ``authorized_keys`` if not already
       present. → ``pubkey_added``.
    4. Start ssh-agent if the socket isn't there or the agent is
       unresponsive (dead-socket detection — the legacy bash had this).
       → ``agent_started``.
    5. ssh-add the key if its fingerprint isn't already loaded.
       → ``key_added_to_agent``.
    6. Strip any prior ``SSH_AUTH_SOCK=`` line from
       ``stacks/wetty/.env`` and re-append the current socket path.
       → ``auth_sock_written`` (always 1 on the success path; the
       env-var line is unconditional).
    """
    key_q = shlex.quote(key_path)
    comment_q = shlex.quote(key_comment)
    sock_q = shlex.quote(agent_socket)
    env_q = shlex.quote(wetty_env_file)
    return f"""set -uo pipefail
KEY_PATH={key_q}
KEY_COMMENT={comment_q}
SOCKET={sock_q}
ENV_FILE={env_q}
KEYPAIR_GEN=0
PUBKEY_ADD=0
AGENT_STARTED=0
KEY_ADDED=0
AUTH_SOCK_WROTE=0

mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Inline-step numbering matches the docstring's "1. mkdir + chmod 700"
# precondition above. The flags below correspond to docstring steps
# 2-6 (steps that produce a 0/1 in RESULT_WETTY).
#
# Step 2: ssh-keygen if absent. Fail-fast (echo RESULT_WETTY with
# keypair_generated=0 + bail) when ssh-keygen reports non-zero OR
# either of the expected output files ($KEY_PATH / $KEY_PATH.pub)
# isn't on disk afterwards. Without this check, downstream steps
# (cat $KEY_PATH.pub, ssh-keygen -lf for fingerprint) would silently
# fail and we'd report a misleading keypair_generated=1 while Wetty
# can't actually SSH.
# Regenerate if EITHER file is missing — not just $KEY_PATH. A stale
# private key with a missing/corrupted .pub (manual cleanup, partial
# write, fs corruption) would otherwise pass the keygen-skip check
# but later `cat "$KEY_PATH.pub"` would yield empty PUBKEY → the
# authorized_keys append silently no-ops (empty grep -F matches the
# whole file → PUBKEY_ADD stays 0) and Wetty can't actually SSH.
# Removing both files first lets ssh-keygen emit a fresh, consistent
# pair (it would refuse to overwrite an existing $KEY_PATH).
if [ ! -f "$KEY_PATH" ] || [ ! -f "$KEY_PATH.pub" ]; then
    if [ -f "$KEY_PATH" ] || [ -f "$KEY_PATH.pub" ]; then
        echo "  ⚠ Wetty keypair half-present (one of $KEY_PATH / .pub missing) — regenerating" >&2
        rm -f "$KEY_PATH" "$KEY_PATH.pub"
    fi
    if ! ssh-keygen -t ed25519 -f "$KEY_PATH" -N '' -C "$KEY_COMMENT" >/dev/null 2>&1; then
        echo "  ⚠ ssh-keygen failed — Wetty will not have a working SSH key" >&2
        echo "RESULT_WETTY keypair_generated=0 pubkey_added=0 agent_started=0 key_added_to_agent=0 auth_sock_written=0"
        exit 0
    fi
    if [ ! -f "$KEY_PATH" ] || [ ! -f "$KEY_PATH.pub" ]; then
        echo "  ⚠ ssh-keygen reported success but key files missing (filesystem issue?)" >&2
        echo "RESULT_WETTY keypair_generated=0 pubkey_added=0 agent_started=0 key_added_to_agent=0 auth_sock_written=0"
        exit 0
    fi
    chmod 600 "$KEY_PATH"
    chmod 644 "$KEY_PATH.pub"
    KEYPAIR_GEN=1
fi

# Step 3: append pubkey to authorized_keys (idempotent — full-line
# fixed-string match so neither a partial duplicate (existing line
# contains $PUBKEY as substring) nor a substring of $PUBKEY (existing
# line that happens to be a substring of the pubkey we're checking)
# can false-positive. `-F` = fixed string (no regex), `-x` = whole-
# line match (the actual invariant the comment claims).
PUBKEY=$(cat "$KEY_PATH.pub")
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
if ! grep -qFx "$PUBKEY" /root/.ssh/authorized_keys 2>/dev/null; then
    printf '%s\\n' "$PUBKEY" >> /root/.ssh/authorized_keys
    PUBKEY_ADD=1
fi

# Step 4: ssh-agent. Two probes: (a) socket file present, (b) agent
# responsive (`ssh-add -l` exit code). A dead-socket from a previous
# crash needs cleaning up before we can start a fresh agent. After
# starting, validate the agent IS responsive — without the validation,
# `ssh-agent` failing silently (`|| true` was needed for the eval +
# subshell case) would still set AGENT_STARTED=1 and we'd report
# success for a broken socket.
mkdir -p "$(dirname "$SOCKET")"
AGENT_OK=0
if [ -S "$SOCKET" ]; then
    SSH_AUTH_SOCK="$SOCKET" ssh-add -l >/dev/null 2>&1 && AGENT_OK=1
    if [ "$AGENT_OK" = "0" ]; then
        # Stale socket — clean up before forking a fresh agent.
        rm -f "$SOCKET"
    fi
fi
if [ "$AGENT_OK" = "0" ]; then
    # `ssh-agent -a SOCKET -s` prints `SSH_AUTH_SOCK=...; SSH_AGENT_PID=...`
    # to stdout for eval; on success the agent forks and listens on
    # SOCKET. Capture the eval's exit AND validate the result.
    if eval "$(ssh-agent -a "$SOCKET" -s)" >/dev/null 2>&1; then
        # Validate: socket file must exist AND the agent must respond.
        # ssh-add -l exit code: 0=keys loaded, 1=no keys but agent OK,
        # 2=can't connect (the failure case we're guarding against).
        if [ -S "$SOCKET" ] && SSH_AUTH_SOCK="$SOCKET" ssh-add -l >/dev/null 2>&1; then
            AGENT_STARTED=1
        else
            ADD_RC=0
            SSH_AUTH_SOCK="$SOCKET" ssh-add -l >/dev/null 2>&1 || ADD_RC=$?
            # rc=1 (no keys) is OK; rc=2 (can't connect) is a real failure.
            if [ "$ADD_RC" = "1" ]; then
                AGENT_STARTED=1
            else
                echo "  ⚠ ssh-agent started but socket isn't responsive — Wetty SSH-Agent setup incomplete" >&2
                echo "RESULT_WETTY keypair_generated=$KEYPAIR_GEN pubkey_added=$PUBKEY_ADD agent_started=0 key_added_to_agent=0 auth_sock_written=0"
                exit 0
            fi
        fi
    else
        echo "  ⚠ ssh-agent failed to start — Wetty SSH-Agent setup incomplete" >&2
        echo "RESULT_WETTY keypair_generated=$KEYPAIR_GEN pubkey_added=$PUBKEY_ADD agent_started=0 key_added_to_agent=0 auth_sock_written=0"
        exit 0
    fi
fi
export SSH_AUTH_SOCK="$SOCKET"

# Step 5: ssh-add the key if its fingerprint isn't already loaded.
# Set KEY_ADDED=1 only on a successful add (legacy form unconditionally
# set it after `|| true`, which masked an actual ssh-add failure).
KEY_FP=$(ssh-keygen -lf "$KEY_PATH" 2>/dev/null | awk '{{print $2}}' || echo "")
KEY_LOADED=0
if [ -n "$KEY_FP" ]; then
    if ssh-add -l 2>/dev/null | grep -qF "$KEY_FP"; then
        KEY_LOADED=1
    fi
fi
if [ "$KEY_LOADED" = "0" ]; then
    if ssh-add "$KEY_PATH" >/dev/null 2>&1; then
        KEY_ADDED=1
    else
        echo "  ⚠ ssh-add failed — Wetty key not loaded into agent" >&2
        # Don't fail-fast: ssh-add can fail for a non-existent key (we
        # already gated above) or transient agent issue. Leave
        # KEY_ADDED=0 so the operator sees the discrepancy in the
        # RESULT_WETTY line; the key file + agent socket still exist
        # so the operator can ssh-add manually if needed.
        :
    fi
fi

# Step 6: write SSH_AUTH_SOCK= to wetty's .env (idempotent — strip
# any prior line first). Set AUTH_SOCK_WROTE=1 only after the append
# succeeds; an mkdir/permission failure shouldn't be reported as
# "written".
if [ -f "$ENV_FILE" ]; then
    if ! sed -i '/^SSH_AUTH_SOCK=/d' "$ENV_FILE" 2>/dev/null; then
        echo "  ⚠ failed to strip existing SSH_AUTH_SOCK= line from $ENV_FILE — Wetty .env may have stale entries" >&2
    fi
fi
if printf 'SSH_AUTH_SOCK=%s\\n' "$SSH_AUTH_SOCK" >> "$ENV_FILE" 2>/dev/null; then
    AUTH_SOCK_WROTE=1
else
    echo "  ⚠ failed to append SSH_AUTH_SOCK= to $ENV_FILE — Wetty container won't see the agent socket" >&2
    echo "RESULT_WETTY keypair_generated=$KEYPAIR_GEN pubkey_added=$PUBKEY_ADD agent_started=$AGENT_STARTED key_added_to_agent=$KEY_ADDED auth_sock_written=0"
    exit 0
fi

echo "RESULT_WETTY keypair_generated=$KEYPAIR_GEN pubkey_added=$PUBKEY_ADD agent_started=$AGENT_STARTED key_added_to_agent=$KEY_ADDED auth_sock_written=$AUTH_SOCK_WROTE"
"""


def parse_wetty_agent_result(stdout: str) -> WettyAgentResult | None:
    """Parse the RESULT_WETTY line from rendered-script stdout. Returns
    None if no parseable line exists (caller treats as soft failure)."""
    match = _WETTY_RESULT_RE.search(stdout)
    if match is None:
        return None
    g = match.groupdict()
    return WettyAgentResult(
        keypair_generated=g["keypair_generated"] == "1",
        pubkey_added=g["pubkey_added"] == "1",
        agent_started=g["agent_started"] == "1",
        key_added_to_agent=g["key_added_to_agent"] == "1",
        auth_sock_written=g["auth_sock_written"] == "1",
    )


def setup_wetty_ssh_agent(
    ssh: SSHClient,
    *,
    key_path: str = "/root/.ssh/id_ed25519_wetty",
    key_comment: str = "wetty-auto-generated",
    agent_socket: str = "/tmp/ssh-agent/agent.sock",  # noqa: S108
    wetty_env_file: str = "/opt/docker-server/stacks/wetty/.env",
) -> WettyAgentResult | None:
    """Render + run the wetty-agent setup script. Returns None on
    unparseable output (soft failure — operator sees the script's
    forwarded stderr; the deploy continues without aborting since
    Wetty is a non-critical UI service).

    ``check=True``: the rendered script ALWAYS terminates with
    ``exit 0`` (fail-fast paths emit a parseable all-zero RESULT line
    + ``exit 0``), so a non-zero returncode here can only mean the
    SSH transport itself broke (rc=255, connection drop, ...). Letting
    ``CalledProcessError`` propagate so the CLI handler maps it to
    rc=2 ("transport failure") instead of silently returning None and
    falling through to the rc=1 "soft fail" branch — caught in
    #530 R4.
    """
    script = render_wetty_agent_script(
        key_path=key_path,
        key_comment=key_comment,
        agent_socket=agent_socket,
        wetty_env_file=wetty_env_file,
    )
    completed = ssh.run_script(script, check=True)
    # Forward non-RESULT diagnostic lines (the script's own ⚠ /
    # ssh-keygen errors etc.) to the local terminal. SSHClient.run_script
    # uses merge_stderr=True by default, so the script's stderr is
    # already folded into completed.stdout — iterating stdout here
    # captures both the rendered bash's `echo … >&2` warnings AND any
    # plain stdout, while skipping the parseable RESULT_WETTY line
    # itself (which the parser below consumes).
    for line in completed.stdout.splitlines():
        if not line.startswith("RESULT_WETTY"):
            sys.stderr.write(line + "\n")
    return parse_wetty_agent_result(completed.stdout)

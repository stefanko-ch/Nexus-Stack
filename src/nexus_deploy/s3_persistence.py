"""S3-backed persistence for stack data (RFC 0001).

Replaces the per-stack Hetzner Block Storage volume with Cloudflare
R2 as the canonical persistence layer. Server local SSD becomes
ephemeral cache; on spinup we restore from R2, on teardown we
snapshot to R2 *atomically* (verify before destroy).

The module itself is endpoint-agnostic — it talks to anything
S3-compatible via the :class:`S3Endpoint` constructor argument. The
defaults and docs reflect R2 because that's the v1.0 storage
provider per RFC 0001 decision #1; the same module can drive
Hetzner Object Storage or AWS S3 by passing a different endpoint.

This module follows the same pattern as ``setup.py``: pure rendering
functions that return server-side bash. Actual execution happens via
:class:`SSHClient` in the orchestrator pipeline. Two upsides:

1. Tests are subprocess-free — we assert on the rendered string.
2. The SSHClient already handles connection pooling, error
   propagation and structured logging; we don't reinvent that.

Public surface:

* :class:`S3Endpoint` — frozen ``(endpoint, region, access_key,
  secret_key, bucket)`` tuple. The credentials are intentionally
  passed in rather than read from the environment so the rendered
  script never relies on ambient state — and so unit tests can
  inject a fixture without touching real R2 credentials.
* :class:`SnapshotManifest` — Python-level dataclass + JSON
  serialiser for the snapshot metadata. The version-1.0 *rendered*
  bash writes a slim manifest (timestamp, stack, template version)
  and relies on rclone's ETag check for integrity, so v1.0
  ``manifest.json`` files in S3 carry no per-component checksums.
  This dataclass + :func:`manifest_for_components` exist for
  callers that need to compute and emit per-component checksums
  client-side — currently used only by tests and a planned v1.1
  cleanup-and-verify script. See "Open question 1" in
  ``docs/proposals/0001-s3-persistence.md``.
* :func:`render_rclone_config` — produces a ``[cloudflare-r2]``
  rclone profile block from an :class:`S3Endpoint`. Written to
  ``~/.config/rclone/rclone.conf`` on the server. Idempotent — the
  block is identified by name and replaced wholesale on every
  spinup so credential rotation is a single render away.
* :func:`render_snapshot_script` — bash that stops the relevant
  docker compose stacks (graceful drain, not ``pause``), runs
  ``pg_dump`` for each Postgres database we care about, rsyncs
  ``/var/lib/nexus-data/`` to S3, writes the manifest, and exits
  with rc=0 only if every ``rclone check`` passed. Caller is
  responsible for treating rc≠0 as "abort teardown — leave the
  server up".
* :func:`render_restore_script` — bash that reads
  ``snapshots/latest.txt`` (a single-line pointer to the active
  snapshot timestamp; v1.0 does NOT download/parse
  ``manifest.json`` — integrity is checked at snapshot-write
  time via ``rclone check``, not on restore), then rclone-syncs
  the snapshot tree to ``/var/lib/nexus-data/``,
  and runs ``pg_restore`` for each Postgres dump. Idempotent on
  the empty-S3 case (first-time spinup).

Why no client-side rclone bindings: rclone is a Go binary that
ships as a single static executable. Driving it via subprocess
from Python on the orchestrator would mean a) shipping rclone in
the dev environment, b) reasoning about cross-platform binary
selection, c) duplicating the credential handling we already need
to do remote-side. Generating bash that the remote runs keeps the
boundary clean.

Design choices for v1.0 (see RFC 0001 in
``docs/proposals/0001-s3-persistence.md`` for the full reasoning):

* **Cloudflare R2**, not Hetzner Object Storage — the project
  already uses R2 for the Tofu state backend, the
  ``cloudflare/cloudflare`` provider is already wired up, and R2
  has zero egress fees + region-agnostic access. The earlier
  Hetzner-OS proposal would have introduced a parallel storage
  system and a per-region egress cost for non-EU compute.
* **Bucket per stack** — one R2 bucket per ``<class>-<user>``
  slug. Easier blast-radius isolation than ``<bucket>/<stack>/...``
  prefixes.
* **rsync (rclone) for everything in v1.0** — Forgejo LFS and Dify
  storage have native S3 backends but that's deferred to v1.1.
  v1.0 keeps the docker-compose layout untouched and drives
  persistence purely via rclone sync of the bind-mount directory.
* **Snapshot-versioning strategy**: timestamped directories under
  ``snapshots/<ISO8601>/`` plus a ``snapshots/latest.txt`` pointer
  file. Retention (30-day NoncurrentVersionExpiration via R2
  lifecycle policy) is enforced by ``scripts/init-s3-bucket.sh``
  in v1.0 — the script enables bucket versioning and applies the
  lifecycle rule via the S3 API at bucket-bootstrap time. v1.1
  may migrate this to a Tofu resource once the
  ``cloudflare/cloudflare`` provider grows a first-class R2
  lifecycle resource. Either way, it stays out of scope for
  this module — the module only writes objects, never configures
  the bucket itself.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Identifier shape — protects the rendered bash from injection
# ---------------------------------------------------------------------------

# S3-region identifier shape. R2 uses ``auto`` as the region (R2
# is a single global namespace with edge replication, no traditional
# region routing). For Hetzner Object Storage the equivalent is a
# location code like ``fsn1`` / ``hel1`` / ``nbg1``. We accept any
# lowercase alnum-with-dashes value so the module supports both
# providers from the same charset gate. The bucket name follows S3
# rules (3-63 chars, lowercase, digits, hyphens). We're strict on
# both because they're interpolated into rendered bash without
# further escaping; a value containing ``$``, ``;`` or backticks
# would let an attacker who controlled the value execute arbitrary
# commands on the server.
_S3_REGION = re.compile(r"^[a-z0-9-]+$")
_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_ACCESS_KEY = re.compile(r"^[A-Za-z0-9]+$")
# S3-style secret keys are base64-ish across providers (R2 emits
# 40-64 chars; Hetzner / AWS similar). We allow the full set of
# base64 + URL-safe characters so we don't reject a future format
# change, but still gate against bash metacharacters.
_SECRET_KEY = re.compile(r"^[A-Za-z0-9+/=_-]+$")
# Postgres identifier shape — applies to both database names and
# role names interpolated into rendered SQL (``DROP DATABASE
# {pg.database}``, ``CREATE DATABASE ... OWNER {pg.user}``). PG
# itself permits a wider character set when identifiers are
# double-quoted, but we deliberately don't accept that complexity:
# every database/user we manage today matches this strict shape, and
# an attacker who controls the value should be rejected at config
# time, not handled with quoting acrobatics.
#
# Note: this charset **includes hyphens** because real role names in
# the project use them (``nexus-forgejo`` in stacks/forgejo/docker-
# compose.yml, ``nexus-dify`` in stacks/dify/docker-compose.yml).
# Hyphens are valid inside double-quoted SQL identifiers but invalid
# unquoted, so :func:`_quote_sql_ident` below double-quotes the
# rendered SQL identifier unconditionally.
_PG_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
# S3 object-key shape — applies to ``RsyncTarget.s3_subpath`` which is
# interpolated into double-quoted bash strings like
# ``"$BUCKET/$SNAPSHOT_PREFIX/{sub}"``. ``shlex.quote`` does NOT make
# a value safe inside double quotes (``$(...)`` and backticks still
# expand). Restrict to a strict path-segment shape: lowercase alnum +
# hyphen + dot + forward-slash for nesting. No ``..``, no leading
# slash, no quotes/dollars/backticks/spaces/newlines.
_S3_SUBPATH = re.compile(r"^[a-z0-9][a-z0-9./-]*[a-z0-9]$|^[a-z0-9]$")
# Endpoint URL shape — the rclone config writes ``endpoint = <value>``
# verbatim; whitespace or newlines would corrupt the file. Accept
# scheme + ://, then a conservative URL char set covering host/port/
# path. Real R2 endpoints (https://<account_id>.r2.cloudflarestorage.com)
# and Hetzner endpoints (https://fsn1.your-objectstorage.com) both
# match cleanly; injection attempts don't.
_ENDPOINT_URL = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")


class S3PersistenceError(Exception):
    """Raised when an :class:`S3Endpoint` is constructed with values
    that would be unsafe to interpolate into a rendered bash script.

    We surface this as an exception (not a silent ``ValueError``) so
    the CLI handler can give the operator a clear "your config has
    a bad value" message rather than a confusing rendered-bash
    failure later in the pipeline.
    """


# ---------------------------------------------------------------------------
# Endpoint + manifest data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class S3Endpoint:
    """S3-compatible storage connection coordinates.

    All five fields are required: missing credentials are an error
    surfaced at construction time, not at script-render time, so the
    operator gets a stack trace that points at the *source* of the
    missing value (config, secret store, …) rather than a confusing
    rclone error on the remote.

    ``endpoint`` is the full URL (e.g.
    ``https://<account_id>.r2.cloudflarestorage.com`` for R2,
    ``https://fsn1.your-objectstorage.com`` for Hetzner Object
    Storage) so we don't have to assume the URL shape. ``region``
    is the short code required by the S3 v4 signing protocol —
    ``auto`` for R2, the location code (``fsn1`` / ``hel1`` /
    ``nbg1``) for Hetzner.
    """

    endpoint: str
    region: str
    access_key: str
    secret_key: str
    bucket: str

    def __post_init__(self) -> None:
        # Endpoint must be an http(s) URL — trivial guard against
        # accidentally passing the bucket name into the endpoint slot.
        if not self.endpoint.startswith(("http://", "https://")):
            raise S3PersistenceError(
                f"S3Endpoint.endpoint must start with http(s)://: {self.endpoint!r}",
            )
        # The endpoint URL gets interpolated verbatim into the
        # rendered rclone config (key=value lines). The http(s)://
        # prefix check alone doesn't catch whitespace, newlines, or
        # control characters — any of which would corrupt the config
        # file (split the value across multiple keys, inject extra
        # lines) the moment rclone parses it. Tighten to the URL
        # character set: scheme + `://` + RFC-3986 unreserved/host
        # characters + optional port + optional path. Real Hetzner
        # endpoints (e.g. ``https://fsn1.your-objectstorage.com``)
        # are well inside this set; an injection attempt is not.
        if not _ENDPOINT_URL.fullmatch(self.endpoint):
            raise S3PersistenceError(
                "S3Endpoint.endpoint contains characters that would corrupt the "
                f"rendered rclone config (whitespace/newlines/control chars): {self.endpoint!r}",
            )
        for name, value, pattern in (
            ("region", self.region, _S3_REGION),
            ("bucket", self.bucket, _BUCKET_NAME),
            ("access_key", self.access_key, _ACCESS_KEY),
            ("secret_key", self.secret_key, _SECRET_KEY),
        ):
            if not pattern.fullmatch(value):
                raise S3PersistenceError(
                    f"S3Endpoint.{name} contains characters that would be unsafe to "
                    f"interpolate into rendered bash; got {value!r}",
                )


@dataclass(frozen=True)
class ComponentSnapshot:
    """One component's contribution to the snapshot manifest.

    Tracks size + checksum so the restore-side can detect a partial
    or corrupt upload before it pollutes the live system. ``path``
    is the relative S3 key under the snapshot's timestamped
    directory; the remote bash uses it both as the rclone source and
    as the lookup key in the manifest.
    """

    name: str
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SnapshotManifest:
    """The ``manifest.json`` written at the root of every snapshot.

    Versioned: a future v2 manifest can carry additional fields
    without breaking forward-compat — the restore-side reads
    ``version`` and dispatches accordingly. For v1.0 we keep one
    flat shape covering the four components we care about today
    (Forgejo repos+lfs+postgres, Dify storage+postgres+weaviate).
    """

    version: int = 1
    created_at: str = ""
    stack: str = ""
    template_version: str = ""
    components: tuple[ComponentSnapshot, ...] = field(default_factory=tuple)

    def to_json(self) -> str:
        """Serialise to indented JSON — written to ``manifest.json``
        at the root of the timestamped snapshot directory.

        Indented because it's read by humans during ops/debugging,
        and 200-300 bytes of whitespace per manifest doesn't move
        the needle on storage cost or transfer time at our snapshot
        cadence — for R2 specifically, egress is free.
        """
        return json.dumps(
            {
                **asdict(self),
                "components": [asdict(c) for c in self.components],
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> SnapshotManifest:
        """Parse a manifest written by an earlier teardown.

        Raises :class:`S3PersistenceError` for any structural
        problem so the caller (restore script) can hard-fail
        before pulling potentially-corrupt data.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise S3PersistenceError(
                f"manifest.json is not valid JSON: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise S3PersistenceError(
                f"manifest.json root must be an object, got {type(data).__name__}",
            )
        version = data.get("version")
        if version != 1:
            raise S3PersistenceError(
                f"manifest.json version {version!r} is not supported (expected 1)",
            )
        components_raw = data.get("components", [])
        if not isinstance(components_raw, list):
            raise S3PersistenceError(
                "manifest.json 'components' must be a list",
            )
        # Each component must be a dict with the four expected keys.
        # The previous implementation indexed straight into ``c[...]``
        # which raised KeyError/TypeError on corrupt input — a class
        # of failure the docstring explicitly promises to surface as
        # S3PersistenceError. Validate each entry explicitly so a
        # malformed manifest produces an actionable error rather than
        # a confusing KeyError stack trace from the restore path.
        components: list[ComponentSnapshot] = []
        for idx, c in enumerate(components_raw):
            if not isinstance(c, dict):
                raise S3PersistenceError(
                    f"manifest.json components[{idx}] must be an object, got {type(c).__name__}",
                )
            for key in ("name", "path", "size_bytes", "sha256"):
                if key not in c:
                    raise S3PersistenceError(
                        f"manifest.json components[{idx}] is missing required key {key!r}",
                    )
            try:
                components.append(
                    ComponentSnapshot(
                        name=str(c["name"]),
                        path=str(c["path"]),
                        size_bytes=int(c["size_bytes"]),
                        sha256=str(c["sha256"]),
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise S3PersistenceError(
                    f"manifest.json components[{idx}] has a bad value: {exc}",
                ) from exc
        return cls(
            version=1,
            created_at=str(data.get("created_at", "")),
            stack=str(data.get("stack", "")),
            template_version=str(data.get("template_version", "")),
            components=tuple(components),
        )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


# rclone profile name. Used as the destination prefix in rclone
# commands (``rclone sync /local cloudflare-r2:bucket/path``).
# Picked at module level so the config-render and the script-render
# can't drift apart. Naming the profile after the v1.0 provider (R2)
# keeps things obvious in the rendered scripts; if we ever switch
# providers in the future we can rename here without changing any
# caller — the constant is the single source of truth.
RCLONE_PROFILE = "cloudflare-r2"


def _quote_sql_ident(name: str) -> str:
    """Double-quote a Postgres identifier for safe SQL interpolation.

    Real role names in the project use hyphens (``nexus-forgejo``,
    ``nexus-dify``) — hyphens are illegal inside *unquoted* SQL
    identifiers but valid inside double-quoted ones. Always
    emitting the quoted form means the rendered SQL works for
    both shapes without case-by-case logic.

    The input is already charset-gated by :data:`_PG_IDENTIFIER`,
    so it never contains a literal ``"``; we still double any that
    appear, belt-and-suspenders, in case a future caller bypasses
    the gate.
    """
    return '"' + name.replace('"', '""') + '"'


def render_rclone_config(endpoint: S3Endpoint) -> str:
    """Render the ``[cloudflare-r2]`` rclone profile block.

    The output is the *full* config file content, not a diff.
    Caller writes it atomically to ``~/.config/rclone/rclone.conf``
    on the server (overwrite-with-tempfile pattern) so a partial
    write can't leave the file in a state where rclone reads
    half-old half-new credentials.

    ``provider = Cloudflare`` tells rclone to apply R2-specific
    quirks (no checksum-on-multipart, no STORAGE_CLASS, etc.). If
    the caller passes a Hetzner endpoint instead, this is wrong —
    but v1.0 ships with R2 only, and the profile name is fixed at
    module level. A future provider-agnostic refactor would lift
    the ``provider`` value to a constructor argument.
    """
    return (
        f"[{RCLONE_PROFILE}]\n"
        "type = s3\n"
        "provider = Cloudflare\n"
        "env_auth = false\n"
        f"access_key_id = {endpoint.access_key}\n"
        f"secret_access_key = {endpoint.secret_key}\n"
        f"endpoint = {endpoint.endpoint}\n"
        f"region = {endpoint.region}\n"
        # `acl = private` is the R2 default but spelling it out
        # makes the intent explicit and protects against a future
        # rclone-default change.
        "acl = private\n"
    )


@dataclass(frozen=True)
class PostgresDumpTarget:
    """One Postgres database to dump on teardown / restore on spinup.

    ``container`` is the docker-compose service name (e.g.
    ``forgejo-db``); ``database`` is the PG database name (often the
    same as ``user``); ``user`` is the role used for pg_dump and
    pg_restore. We pass these in (rather than infer them) so the
    same module supports any new stateful stack — the caller in
    pipeline.py decides which databases to back up.

    All three fields are charset-validated at construction so the
    rendered bash + SQL never sees a value that could break out of
    interpolation. ``container`` matches the Hetzner-region shape
    (alnum + dash, lowercase) — every docker-compose service in
    this codebase uses that style. ``database`` and ``user`` match
    the strict Postgres-identifier subset (``[A-Za-z_][A-Za-z0-9_-]*``)
    we use across all stacks; we deliberately don't accept the
    wider double-quoted-identifier space because no service we ship
    needs it and it would force quoting acrobatics in the rendered
    SQL.
    """

    container: str
    database: str
    user: str

    def __post_init__(self) -> None:
        if not _S3_REGION.fullmatch(self.container):
            raise S3PersistenceError(
                f"PostgresDumpTarget.container must match docker-service-name shape "
                f"(lowercase alnum + dash): {self.container!r}",
            )
        for name, value in (("database", self.database), ("user", self.user)):
            if not _PG_IDENTIFIER.fullmatch(value):
                raise S3PersistenceError(
                    f"PostgresDumpTarget.{name} must match strict PG identifier shape "
                    f"([A-Za-z_][A-Za-z0-9_-]*): {value!r}",
                )


@dataclass(frozen=True)
class RsyncTarget:
    """One filesystem subtree to mirror to/from S3.

    ``local_path`` is the absolute path under
    ``/var/lib/nexus-data/`` (the post-volume layout). ``s3_subpath``
    is the relative key under the snapshot's timestamped directory
    — kept short and stable across snapshots so a future
    diff-based optimisation has a useful key to compare against.

    Charset validation: ``s3_subpath`` is interpolated into bash
    *inside* double-quoted strings (``"$BUCKET/$PREFIX/{sub}"``),
    where ``shlex.quote()`` doesn't help — ``$()`` and backticks
    still expand inside double quotes. We enforce a strict
    path-segment shape at construction so the rendered bash can't
    be tricked into executing the value as a command substitution.
    ``local_path`` is interpolated with ``shlex.quote`` outside any
    double quotes, so its only requirement is absolute-path
    (the rendered script does ``mkdir -p`` etc. against it).
    """

    name: str
    local_path: str
    s3_subpath: str

    def __post_init__(self) -> None:
        if not self.local_path.startswith("/"):
            raise S3PersistenceError(
                f"RsyncTarget.local_path must be absolute: {self.local_path!r}",
            )
        if not _S3_SUBPATH.fullmatch(self.s3_subpath):
            raise S3PersistenceError(
                "RsyncTarget.s3_subpath must match strict path-segment shape "
                "(lowercase alnum + hyphen + dot + forward-slash, no leading "
                f"slash, no `..`): {self.s3_subpath!r}",
            )
        if ".." in self.s3_subpath.split("/"):
            raise S3PersistenceError(
                f"RsyncTarget.s3_subpath must not contain '..' segments: {self.s3_subpath!r}",
            )


def render_snapshot_script(
    *,
    endpoint: S3Endpoint,
    stack_slug: str,
    template_version: str,
    timestamp: str,
    postgres_targets: Iterable[PostgresDumpTarget],
    rsync_targets: Iterable[RsyncTarget],
    stop_compose_files: Iterable[str] = (),
) -> str:
    """Render the bash that snapshots the live stack to R2.

    Steps the rendered script performs (in order, ``set -euo
    pipefail`` throughout — first failure aborts):

    1. ``pg_dump -F c | gzip`` for each postgres target into
       ``/tmp/nexus-snapshot/postgres/<db>.dump.gz`` (custom
       binary format, gzipped — works with the matching
       ``gunzip | pg_restore`` on the spinup side). Runs FIRST
       while the postgres containers are still running — pg_dump
       is a client tool that requires a live server. The earlier
       "stop first, dump second" form failed every snapshot
       with "container is not running". pg_dump's MVCC gives a
       consistent snapshot internally; the small window between
       dump and stop may lose writes that happened in that gap
       (acceptable for a teardown use case at low traffic).
       Per-target skip if the container isn't running (``docker
       inspect --format='{{.State.Running}}'``).
    2. ``docker compose stop`` for every file in
       ``stop_compose_files``. Graceful drain with the default
       10s timeout: app processes finish in-flight requests and
       close DB connections cleanly. We deliberately do NOT use
       ``docker compose pause`` — that's a cgroup-freezer SIGSTOP
       and hard-kills in-flight writes mid-transaction. Runs
       AFTER pg_dump so the DB is up at dump time. Per-file skip
       if the compose file isn't on disk (stack not deployed).
    3. ``rclone sync`` each rsync target's ``local_path`` into the
       timestamped R2 directory ``snapshots/<timestamp>/<s3_subpath>``.
       Only the listed targets are walked — db/ and redis/ subdirs
       under /var/lib/nexus-data are NOT included (Postgres state is
       captured separately via pg_dump, Redis is regeneratable).
    4. Upload the postgres dumps under
       ``snapshots/<timestamp>/postgres/<db>.dump.gz``.
    5. Write a slim ``manifest.json`` (stack, timestamp, template
       version — no per-component checksums in v1.0; we rely on
       rclone's ETag/per-object hash check for integrity). Upload
       it to ``snapshots/<timestamp>/manifest.json``.
    6. **Atomicity gate** — run ``rclone check --one-way`` once
       per source: the workdir tree (containing manifest +
       postgres dumps) PLUS each RsyncTarget's local_path against
       its R2 destination. Each check captures two rcs via
       ``PIPESTATUS`` (rclone's own exit, and the drift-grep's
       exit), neither maskable by ``|| true``. Any failure
       accumulates into ``verify_failed=1`` and the script aborts
       BEFORE touching the ``snapshots/latest.txt`` pointer —
       this is the "verified-before-pointing-latest" invariant
       the caller relies on for atomic teardown.
    7. Update ``snapshots/latest.txt`` to contain the new
       timestamp. Pipeline.py interprets script rc=0 as
       "proceed to tofu destroy"; any non-zero rc means
       "abort teardown, leave server up".

    Side note on shlex.quote: every interpolated value is gated
    upstream by the dataclass constructors' charset checks; we
    still ``shlex.quote`` belt-and-suspenders to keep the rendered
    bash safe even if a future caller bypasses validation.
    """
    if not _BUCKET_NAME.fullmatch(stack_slug):
        raise S3PersistenceError(
            f"stack_slug must match S3 bucket-name shape: {stack_slug!r}",
        )
    # ISO-8601 with safe filesystem chars only (no ``:``, since some
    # tools — including rclone on Windows-share remotes — choke on
    # colons). Caller decides the format; we just verify it's
    # injection-safe.
    if not re.fullmatch(r"[0-9A-Za-z_-]+", timestamp):
        raise S3PersistenceError(
            f"timestamp must be alphanumeric/underscore/dash only: {timestamp!r}",
        )

    pg_targets = tuple(postgres_targets)
    rs_targets = tuple(rsync_targets)
    stop_files = tuple(stop_compose_files)

    bucket_url = f"{RCLONE_PROFILE}:{shlex.quote(endpoint.bucket)}"
    snapshot_prefix = f"snapshots/{shlex.quote(timestamp)}"

    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Generated by nexus_deploy.s3_persistence — do not edit by hand.",
        "set -euo pipefail",
        "",
        f"STACK={shlex.quote(stack_slug)}",
        f"TIMESTAMP={shlex.quote(timestamp)}",
        f"TEMPLATE_VERSION={shlex.quote(template_version)}",
        f"BUCKET={bucket_url}",
        f"SNAPSHOT_PREFIX={snapshot_prefix}",
        "WORKDIR=/tmp/nexus-snapshot",
        "POSTGRES_DIR=$WORKDIR/postgres",
        # Verify-phase scratch files (rclone-check stderr/stdout)
        # MUST live OUTSIDE $WORKDIR — verify_one writes them and
        # the first verify_one call compares $WORKDIR vs S3. If
        # they lived in $WORKDIR they'd appear as untracked extras
        # and rclone would report "differences found", failing
        # every snapshot. Took until today's first real run to
        # surface (no test exercised the bash-level verify path).
        "LOG_DIR=/tmp/nexus-snapshot-logs",
        "",
        'echo "→ snapshot: preparing workdir"',
        'rm -rf "$WORKDIR" "$LOG_DIR"',
        'mkdir -p "$POSTGRES_DIR" "$LOG_DIR"',
        "",
    ]

    # Order matters here. pg_dump MUST run BEFORE compose-stop,
    # not after — ``docker compose stop`` halts the postgres
    # container, after which ``docker exec <container> pg_dump``
    # fails with "container is not running". The original RFC-0001
    # design (stop → drain → dump) assumed pg_dump could read the
    # on-disk data dir directly after a graceful stop, but pg_dump
    # is a CLIENT tool that needs a running server. We accept the
    # small inconsistency window (apps may write new rows between
    # pg_dump and compose-stop) — pg_dump's MVCC snapshot is
    # internally consistent, and the post-dump writes are simply
    # lost on restore. For the v1.0 teardown use case (deliberate
    # shutdown at low traffic) this is acceptable; if a future
    # use case needs hard-stop consistency, the right answer is
    # filesystem-level snapshot of ``/mnt/nexus-data/<stack>/db``
    # AFTER compose-stop, not pg_dump.
    if pg_targets:
        lines.append('echo "→ snapshot: dumping postgres databases (online)"')
        for pg in pg_targets:
            container = shlex.quote(pg.container)
            db = shlex.quote(pg.database)
            user = shlex.quote(pg.user)
            # File naming: ``<database>.dump.gz`` (custom binary
            # pg_dump format, gzipped) — matches the restore-side
            # filename and the RFC's stated S3 layout. Earlier this
            # said ``.sql.gz`` which was misleading since the body
            # is NOT plain SQL (``-F c`` produces a binary archive).
            dump_file = f"$POSTGRES_DIR/{pg.database}.dump.gz"
            # Skip if the postgres container isn't RUNNING on this
            # server. Two distinct skip cases:
            #   - container doesn't exist (stack not deployed)
            #   - container exists but is stopped (previous crashed
            #     run, or operator stopped it manually)
            # Both have the same outcome: no dump captured. We
            # explicitly check ``.State.Running == "true"`` rather
            # than just ``docker inspect`` because the latter
            # succeeds for stopped containers, and we already hit
            # that bug once (compose-stop happened before pg_dump
            # in an earlier revision, leaving the container stopped
            # but inspectable).
            lines.append(
                f"if [ \"$(docker inspect --format='{{{{.State.Running}}}}' "
                f'{container} 2>/dev/null)" = "true" ]; then',
            )
            lines.append(
                f"  docker exec {container} pg_dump -U {user} -d {db} -F c | gzip -9 > {dump_file}",
            )
            lines.append("else")
            lines.append(
                f'  echo "  (skip: container {pg.container} not running — stack not deployed or stopped)"',
            )
            lines.append("fi")
        lines.append("")

    if stop_files:
        lines.append('echo "→ snapshot: stopping compose stacks (graceful 10s drain)"')
        for compose_file in stop_files:
            quoted = shlex.quote(compose_file)
            # ``docker compose stop`` (not ``pause``) — ``pause`` is
            # SIGSTOP via the cgroup freezer and hard-kills in-flight
            # writes. ``stop`` sends SIGTERM with a 10s grace window
            # for the container to flush + close. Runs AFTER pg_dump
            # above (so the DB is still up when pg_dump runs).
            #
            # The previous form used a blanket ``|| echo "non-fatal"``
            # which would swallow every non-zero exit — missing
            # compose file, docker-daemon down, permission issue,
            # syntax error in YAML, etc. Those are all real failures
            # that should abort the snapshot, not warnings the
            # operator quietly ignores. Per CLAUDE.md "Never silently
            # swallow errors in critical operations."
            #
            # We branch on the SPECIFIC happy "stack is already
            # down" case via ``docker compose ps -q``: if the
            # command SUCCEEDS (rc=0) AND its stdout is EMPTY,
            # there are no running containers → safe to skip stop.
            # Any other situation (ps itself fails, or it succeeds
            # and lists running containers) takes us into the
            # ``compose stop`` branch — where ``set -e`` will abort
            # the snapshot on any non-zero exit, surfacing missing-
            # compose-file / daemon-down / YAML-syntax errors as
            # the real failures they are.
            lines.append(f"COMPOSE_FILE={quoted}")
            # Skip cleanly if the compose file isn't on disk —
            # ``stop_compose_files`` is a static list of stacks the
            # persistence layer KNOWS ABOUT; whether a given stack
            # is actually deployed on this server is decided by D1
            # (enabled_services). A stack absent from disk just
            # means it isn't enabled here, not an error.
            lines.append('if [ ! -f "$COMPOSE_FILE" ]; then')
            lines.append(
                f'  echo "  (skip: compose file {compose_file} not on disk — stack not deployed)"',
            )
            lines.append("else")
            lines.append("  set +e")
            lines.append('  PS_OUT=$(docker compose -f "$COMPOSE_FILE" ps -q 2>/dev/null)')
            lines.append("  PS_RC=$?")
            lines.append("  set -e")
            lines.append('  if [ "$PS_RC" -eq 0 ] && [ -z "$PS_OUT" ]; then')
            lines.append(
                f'    echo "  (skip: compose stack at {compose_file} already down)"',
            )
            lines.append("  else")
            lines.append('    docker compose -f "$COMPOSE_FILE" stop')
            lines.append("  fi")
            lines.append("fi")
        lines.append("")

    lines.append('echo "→ snapshot: uploading filesystem trees"')
    for rs in rs_targets:
        local = shlex.quote(rs.local_path)
        sub = shlex.quote(rs.s3_subpath)
        # And again: skip if the source directory isn't on disk
        # (stack not deployed → no data to snapshot). Without this
        # guard rclone sync would fail with "directory not found"
        # and abort the whole snapshot. ``--create-empty-src-dirs``
        # below preserves the structure on the S3 side when the
        # source IS present but empty (different case).
        lines.append(f"if [ -d {local} ]; then")
        lines.append(
            f'  rclone sync --create-empty-src-dirs {local} "$BUCKET/$SNAPSHOT_PREFIX/{sub}"',
        )
        lines.append("else")
        lines.append(
            f'  echo "  (skip: data dir {rs.local_path} not on disk — stack not deployed)"',
        )
        lines.append("fi")
    lines.append("")

    if pg_targets:
        lines.append('echo "→ snapshot: uploading postgres dumps"')
        lines.append(
            'rclone sync "$POSTGRES_DIR" "$BUCKET/$SNAPSHOT_PREFIX/postgres"',
        )
        lines.append("")

    lines.extend(
        [
            'echo "→ snapshot: writing manifest"',
            'cat > "$WORKDIR/manifest.json" <<EOF',
            "{",
            '  "version": 1,',
            '  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",',
            '  "stack": "$STACK",',
            '  "timestamp": "$TIMESTAMP",',
            '  "template_version": "$TEMPLATE_VERSION"',
            "}",
            "EOF",
            'rclone copyto "$WORKDIR/manifest.json" "$BUCKET/$SNAPSHOT_PREFIX/manifest.json"',
            "",
            'echo "→ snapshot: verifying upload (rclone check)"',
            # Atomicity gate. Three classes of source need verifying:
            #
            #   a. ``$WORKDIR`` — locally-staged manifest.json + the
            #      postgres dumps under $POSTGRES_DIR.
            #   b. each :class:`RsyncTarget`.local_path — the
            #      filesystem trees uploaded directly from
            #      /var/lib/nexus-data/<...>. These were NOT in
            #      $WORKDIR (we synced them straight from the live
            #      mount), so a $WORKDIR-only check would have left
            #      the bulk of the persisted state unverified.
            #
            # We run ``rclone check`` once per source, accumulating
            # any failure into a single ``verify_failed`` flag. Two
            # distinct rcs per check (rclone's own exit and the
            # grep-for-drift) are captured via ``PIPESTATUS`` so
            # neither can be masked by ``|| true``.
            #
            # ``--one-way`` keeps each comparison source→S3 only, so
            # a stale orphan in S3 from a previous failed snapshot
            # can't by itself fail the gate.
            "verify_failed=0",
            "verify_one() {",
            '  local src="$1"',
            '  local dst="$2"',
            '  local label="$3"',
            # Same skip-on-missing semantics as the snapshot blocks
            # above. If the source dir isn't on disk (stack not
            # deployed) the corresponding rclone sync was already
            # skipped, so there's nothing for rclone check to
            # compare — verifying a missing source against an empty
            # S3 prefix would fail with "directory not found" and
            # mark the whole verify as drifted. Treat absent source
            # as benign-skip with an explicit log line.
            '  if [ ! -d "$src" ]; then',
            '    echo "  (skip verify: source $src not on disk — stack not deployed)"',
            "    return",
            "  fi",
            "  set +e",
            # Pipeline is three-stage: rclone | tee | grep. PIPESTATUS
            # indexes accordingly:
            #   [0] = rclone (the actual integrity check)
            #   [1] = tee   (just buffering output; ~always succeeds)
            #   [2] = grep  (0 = drift markers found, 1 = clean)
            # An earlier revision captured drift_rc=[1] (tee), which
            # always succeeds, so the gate effectively reported
            # "drift found" on every snapshot and would have aborted
            # every real teardown. Capturing [2] (grep) makes drift
            # detection actually correct.
            '  rclone check "$src" "$dst" '
            '--one-way --combined - 2>"$LOG_DIR/rclone-check.err" '
            '| tee "$LOG_DIR/rclone-check.out" '
            '| grep -qE "^[-*]"',
            # CRITICAL: copy PIPESTATUS to a local array IMMEDIATELY,
            # in ONE command. Every subsequent command (including the
            # ``local`` builtin) overwrites PIPESTATUS with its own
            # single-element exit code, so doing two separate
            # ``local rclone_rc=${PIPESTATUS[0]}; local drift_rc=
            # ${PIPESTATUS[2]}`` would have ``set -u`` complain about
            # ``PIPESTATUS[2]: unbound variable`` on the second line
            # (the first ``local`` clobbered PIPESTATUS to a
            # 1-element array). This was a latent bug since RFC-0001
            # day 1 — bash -n syntax checks didn't catch it; pure-
            # string tests didn't notice; nobody ever actually ran
            # the verify phase against real S3 until today.
            '  local pipeline_status=("${PIPESTATUS[@]}")',
            "  local rclone_rc=${pipeline_status[0]}",
            "  local drift_rc=${pipeline_status[2]}",
            "  set -e",
            '  if [ "$rclone_rc" -ne 0 ]; then',
            '    echo "✗ snapshot-failed: rclone check ${label} errored (rc=$rclone_rc)" >&2',
            '    cat "$LOG_DIR/rclone-check.err" >&2 || true',
            "    verify_failed=1",
            "    return",
            "  fi",
            '  if [ "$drift_rc" -eq 0 ]; then',
            '    echo "✗ snapshot-failed: rclone check ${label} found drift" >&2',
            '    cat "$LOG_DIR/rclone-check.out" >&2',
            "    verify_failed=1",
            "    return",
            "  fi",
            '  echo "  ✓ verified ${label}"',
            "}",
            "",
            'verify_one "$WORKDIR" "$BUCKET/$SNAPSHOT_PREFIX" "workdir(manifest+postgres)"',
        ]
        + [
            f"verify_one {shlex.quote(rs.local_path)} "
            f'"$BUCKET/$SNAPSHOT_PREFIX/{shlex.quote(rs.s3_subpath)}" '
            f"{shlex.quote('rsync:' + rs.name)}"
            for rs in rs_targets
        ]
        + [
            "",
            'if [ "$verify_failed" -ne 0 ]; then',
            '  echo "✗ snapshot-failed: one or more verifications drifted; not pointing snapshots/latest at $TIMESTAMP" >&2',
            "  exit 2",
            "fi",
            "",
            'echo "→ snapshot: pointing snapshots/latest at $TIMESTAMP"',
            'echo "$TIMESTAMP" > "$WORKDIR/latest.txt"',
            'rclone copyto "$WORKDIR/latest.txt" "$BUCKET/snapshots/latest.txt"',
            "",
            'echo "✓ snapshot complete: $SNAPSHOT_PREFIX"',
        ],
    )

    return "\n".join(lines) + "\n"


def render_restore_script(
    *,
    endpoint: S3Endpoint,
    postgres_targets: Iterable[PostgresDumpTarget],
    rsync_targets: Iterable[RsyncTarget],
    local_root: str = "/var/lib/nexus-data",
    phase: Literal["all", "filesystem", "postgres"] = "all",
) -> str:
    """Render the bash that restores a snapshot from R2 to the local
    filesystem.

    Idempotent on the empty-S3 case (first-time spinup) — the
    rendered script:

    1. Probes bucket reachability via ``rclone lsd "$BUCKET"``. If
       that fails (auth / endpoint / network), exits with rc=2 and
       a clear error — NOT treated as "fresh-start", because that
       would silently turn a credentials problem into empty local
       state and the next teardown would overwrite real R2 data
       with empty snapshots.
    2. Reads ``snapshots/latest.txt`` to get the active timestamp.
       If the file is missing (but the bucket itself listed fine
       above), it short-circuits with ``echo 'fresh-start: no
       snapshot in S3, leaving local state empty'`` and exits 0.
       Pipeline.py then proceeds with a clean docker-compose up
       just like a brand-new install. Also validates the timestamp
       matches the safe-path regex before substituting it into any
       rclone command — defends against a malformed/tampered
       ``latest.txt``.
    3. ``rclone sync`` each RsyncTarget's S3 subpath into the
       matching ``local_path`` (which is the absolute path on the
       server — not always under ``local_root``; callers may
       restore to e.g. ``/opt/data``). ``local_root`` is only used
       to ``mkdir -p`` the top-level data directory.
    4. ``rclone sync`` the postgres dumps from
       ``snapshots/<ts>/postgres/`` into a scratch workdir.
    5. For each postgres target: ``DROP DATABASE IF EXISTS
       "<db>" WITH (FORCE);`` → ``CREATE DATABASE "<db>" OWNER
       "<user>";`` → ``gunzip -c <db>.dump.gz | pg_restore -U
       <user> -d <db> --no-owner --no-acl``. SQL identifiers are
       always double-quoted (real role names use hyphens, e.g.
       ``nexus-forgejo``, which are invalid as unquoted PG idents).
       The container is assumed to already be running
       (compose-up ran first).

    Order matters: filesystem trees restored before pg_restore so
    any postgres init script reading FS config files sees the FS
    in place. Reversing this would race on first start.

    Does NOT touch ``snapshots/latest.txt`` — the active snapshot
    pointer is owned by the snapshot side. A restore is purely
    read-only against R2.

    The ``phase`` parameter splits the restore for callers that
    can't run both halves in one shot (the spinup pipeline can't —
    ``docker exec pg_restore`` needs the forgejo-db / dify-db
    containers running, which only happens after compose-up,
    while the filesystem rsync MUST happen before compose-up so
    the containers come up with the right bind-mount data):

    * ``"filesystem"`` — rsync targets only; skip the postgres
      block. Containers don't need to be running.
    * ``"postgres"`` — pg_restore via docker exec only; skip the
      rsync block. Containers MUST already be running.
    * ``"all"`` (default) — both halves, matches the legacy
      single-shot teardown-side behaviour and keeps the
      tests/snapshot-replay path unchanged.
    """
    if phase not in ("all", "filesystem", "postgres"):
        # Fail loud — if a caller passes a typo like "fs" or
        # "filesystems", both include_fs and include_pg below would
        # become False and the rendered script would exit 0 after
        # only the latest.txt lookup, silently skipping the actual
        # restore. ValueError surfaces the bug at render time
        # instead of at run time as a confusing no-op.
        raise ValueError(
            f"render_restore_script: phase must be one of "
            f"('all', 'filesystem', 'postgres'), got {phase!r}"
        )

    pg_targets = tuple(postgres_targets)
    rs_targets = tuple(rsync_targets)
    bucket_url = f"{RCLONE_PROFILE}:{shlex.quote(endpoint.bucket)}"

    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Generated by nexus_deploy.s3_persistence — do not edit by hand.",
        "set -euo pipefail",
        "",
        f"BUCKET={bucket_url}",
        f"LOCAL_ROOT={shlex.quote(local_root)}",
        "WORKDIR=/tmp/nexus-restore",
        "",
        'mkdir -p "$WORKDIR" "$LOCAL_ROOT"',
        "",
        'echo "→ restore: looking up latest snapshot"',
        # Probe bucket reachability BEFORE deciding "fresh-start". A
        # missing ``latest.txt`` is a legitimate empty-bucket state
        # (first-time spin-up), but the same ``rclone lsf`` failure
        # also fires on auth/endpoint/network errors. Without this
        # extra probe a misconfigured R2 credential would silently
        # be treated as "no snapshot" → empty restore → next teardown
        # snapshots empty state over real data. So: list the bucket
        # root first; if that fails it's an access problem (rc=2).
        # An empty bucket lists fine (returns no entries), so the
        # genuine first-spin-up path still reaches the latest.txt
        # check below and exits 0 with the fresh-start message.
        'if ! rclone lsd "$BUCKET" --max-depth 1 >/dev/null 2>&1; then',
        '  echo "✗ restore-failed: bucket $BUCKET is not reachable" >&2',
        '  echo "  (check R2 credentials / endpoint / bucket name)" >&2',
        "  exit 2",
        "fi",
        # Detect "no snapshot yet" by listing the parent prefix and
        # checking whether ``latest.txt`` is among the entries.
        # Critically: a non-zero exit from this listing is a HARD
        # ERROR (rc=2), not "fresh-start" — otherwise a transient
        # S3 blip between the bucket-reachability probe above and
        # this call would silently empty local state, and the next
        # teardown would overwrite real R2 data with empty snapshots.
        #
        # Two distinct empty-prefix vs missing-file paths:
        #   - bucket reachable, prefix empty (no objects under
        #     ``snapshots/``) → genuine first spin-up, fresh-start
        #     (rc=0 from listing, empty stdout, grep returns
        #     non-zero).
        #   - bucket reachable, prefix has objects but no
        #     ``latest.txt`` → orphan snapshot trees from a failed
        #     ``snapshot_to_s3`` (atomicity guarantee: latest.txt is
        #     the LAST thing written). Still fresh-start — the
        #     orphans cost storage but don't affect restoration.
        #   - listing itself fails (auth/network/perm) → exit 2
        #     loud, so the operator sees the real cause instead of
        #     a silent fresh-start that paves over real data.
        #
        # Don't suppress stderr — rclone's diagnostic on failure is
        # what tells the operator whether it's auth, network, or
        # bucket policy. Quiet on success.
        'SNAPSHOT_LISTING=""',
        'if ! SNAPSHOT_LISTING=$(rclone lsf "$BUCKET/snapshots/"); then',
        '  echo "✗ restore-failed: cannot list $BUCKET/snapshots/" >&2',
        '  echo "  (auth / network / bucket policy — see rclone error above)" >&2',
        "  exit 2",
        "fi",
        'if ! printf "%s\\n" "$SNAPSHOT_LISTING" | grep -qxF "latest.txt"; then',
        '  echo "fresh-start: no snapshot in S3, leaving local state empty"',
        "  exit 0",
        "fi",
        'rclone copyto "$BUCKET/snapshots/latest.txt" "$WORKDIR/latest.txt"',
        # Defence in depth — same rclone-1.60.1 quirk: copyto can
        # return rc=0 without writing the destination. If the lsf
        # check above somehow passed but the file still isn't on
        # disk, fail loud rather than letting the next ``tr -d``
        # leak its kernel-level "No such file or directory" out
        # as the only diagnostic.
        'if [ ! -s "$WORKDIR/latest.txt" ]; then',
        '  echo "✗ restore-failed: rclone copyto did not produce $WORKDIR/latest.txt" >&2',
        '  echo "  (file missing or empty — likely rclone version mismatch or transient S3 issue)" >&2',
        "  exit 2",
        "fi",
        'TIMESTAMP=$(tr -d "\\r\\n" < "$WORKDIR/latest.txt")',
        'if [[ ! "$TIMESTAMP" =~ ^[0-9A-Za-z_-]+$ ]]; then',
        '  echo "✗ restore-failed: latest.txt has invalid timestamp" >&2',
        "  exit 2",
        "fi",
        'SNAPSHOT_PREFIX="snapshots/$TIMESTAMP"',
        'echo "→ restore: using snapshot $SNAPSHOT_PREFIX"',
        "",
    ]

    include_fs = phase in ("all", "filesystem")
    include_pg = phase in ("all", "postgres")

    if rs_targets and include_fs:
        lines.append('echo "→ restore: pulling filesystem trees"')
        for rs in rs_targets:
            sub = shlex.quote(rs.s3_subpath)
            # Use rs.local_path directly — it's already an absolute
            # path. We deliberately don't recompose under local_root
            # because callers may want to restore to a different
            # absolute path (e.g. /opt/data on a future stack) and
            # the value is already injection-safe via shlex.quote.
            #
            # ``local_root`` is still used as the parent dir for
            # mkdir at the top of the script (so the very first
            # rsync target lands in a created directory). It does
            # NOT govern restore destinations.
            local = shlex.quote(rs.local_path)
            lines.append(
                f'rclone sync "$BUCKET/$SNAPSHOT_PREFIX/{sub}" {local} --create-empty-src-dirs',
            )
        lines.append("")

    if pg_targets and include_pg:
        lines.append('echo "→ restore: pulling postgres dumps"')
        lines.append(
            'rclone sync "$BUCKET/$SNAPSHOT_PREFIX/postgres" "$WORKDIR/postgres"',
        )
        lines.append('echo "→ restore: applying postgres dumps"')
        for pg in pg_targets:
            container = shlex.quote(pg.container)
            db_cli = shlex.quote(pg.database)
            user_cli = shlex.quote(pg.user)
            # SQL identifiers — must be DOUBLE-QUOTED in the rendered
            # SQL because real role names use hyphens (``nexus-forgejo``,
            # ``nexus-dify``) which are invalid as unquoted PG
            # identifiers. ``_quote_sql_ident`` handles the doubling
            # of any literal ``"`` in the value (defensive — values
            # are already charset-gated by ``_PG_IDENTIFIER`` so they
            # can't contain quotes today). The SQL goes inside a
            # ``-c "..."`` bash argument that is itself double-quoted,
            # so the inner ``"`` characters need bash-escaping → we
            # use a single-quoted bash argument instead.
            db_sql = _quote_sql_ident(pg.database)
            user_sql = _quote_sql_ident(pg.user)
            dump_file = f"$WORKDIR/postgres/{pg.database}.dump.gz"
            # Symmetric "stack not deployed" handling matching the
            # snapshot-side guards. Two cases:
            #   - No dump file under WORKDIR/postgres/ — the
            #     snapshot side skipped this DB (container wasn't
            #     running at snapshot time). Without the guard, the
            #     subsequent ``gunzip`` would fail with "No such
            #     file" and abort restore.
            #   - Dump file exists but the container isn't running
            #     on this stack (different stack composition between
            #     snapshot and restore — e.g. dify enabled when
            #     snapshotted but not when restored). Without the
            #     guard, ``docker exec dify-db psql`` fails with
            #     "No such container" rc=1 and aborts restore.
            # Either case → skip with an explicit log line; the
            # forgejo-only restore path still proceeds normally.
            lines.append(f"if [ ! -f {dump_file} ]; then")
            lines.append(
                f'  echo "  (skip: no dump for {pg.database} — stack not snapshotted)"',
            )
            lines.append(
                f"elif [ \"$(docker inspect --format='{{{{.State.Running}}}}' "
                f'{container} 2>/dev/null)" != "true" ]; then',
            )
            lines.append(
                f'  echo "  (skip: container {pg.container} not running '
                f'— stack not deployed on this restore target)"',
            )
            lines.append("else")
            # We drop+recreate the database to guarantee a clean
            # restore. pg_restore --clean would do something similar
            # but is fragile across PG versions; the explicit
            # drop+create is portable.
            #
            # ``-c '<SQL>'`` (single-quoted bash arg) so the inner
            # double-quoted SQL identifiers don't need escaping.
            lines.append(
                f"  docker exec {container} psql -U {user_cli} -d postgres "
                f"-c 'DROP DATABASE IF EXISTS {db_sql} WITH (FORCE);'",
            )
            lines.append(
                f"  docker exec {container} psql -U {user_cli} -d postgres "
                f"-c 'CREATE DATABASE {db_sql} OWNER {user_sql};'",
            )
            lines.append(
                f"  gunzip -c {dump_file} | "
                f"docker exec -i {container} pg_restore -U {user_cli} -d {db_cli} "
                "--no-owner --no-acl",
            )
            lines.append("fi")
        lines.append("")

    lines.append('echo "✓ restore complete from $SNAPSHOT_PREFIX"')

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Manifest helpers (used by tests + future cleanup script)
# ---------------------------------------------------------------------------


def manifest_for_components(
    *,
    stack: str,
    template_version: str,
    created_at: str,
    components: Mapping[str, tuple[int, str]],
) -> SnapshotManifest:
    """Build a :class:`SnapshotManifest` from a sized+hashed component map.

    Helper for callers that compute checksums client-side (e.g. unit
    tests, a future cleanup-and-verify script). The on-server bash
    in :func:`render_snapshot_script` builds a slimmer manifest
    without per-component checksums in v1.0 — the rclone check on
    upload covers the integrity property cheaply, and computing
    sha256 over multi-GB rsync trees on the server adds material
    minutes to teardown.

    ``created_at`` should be an ISO-8601 string (e.g.
    ``2026-05-11T04:00:00Z``); it lands on the manifest's
    ``created_at`` field. Previously this parameter was named
    ``timestamp`` and silently ignored — misleading API, fixed
    here by renaming + actually using it.

    The version-1.1 plan is to revisit this and either (a) make the
    rendered bash compute and emit per-component sha256 (slower
    teardown, more robust restore) or (b) trust rclone's own
    integrity check entirely and remove this helper.
    """
    return SnapshotManifest(
        version=1,
        created_at=created_at,
        stack=stack,
        template_version=template_version,
        components=tuple(
            ComponentSnapshot(name=name, path=name, size_bytes=size, sha256=sha)
            for name, (size, sha) in sorted(components.items())
        ),
    )

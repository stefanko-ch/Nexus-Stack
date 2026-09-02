"""PostgreSQL major-version preflight for the stacks about to start.

PostgreSQL refuses to start against a data directory written by an older
major. The container then restart-loops and everything behind that
database is down::

    FATAL:  database files are incompatible with server
    DETAIL: The data directory was initialized by PostgreSQL version 16,
            which is not compatible with this version 18.

Nothing is lost quietly — ``compose_runner`` counts the stack as failed
and the smoke check marks it ``RESTARTING`` — but the operator sees
"compose up failed" and has to go find the log line to learn that the
cause is a major mismatch and the fix is a dump/restore rather than a
retry. This closes that gap by checking before anything starts (#734).

**Only the snapshot lifecycle can reach it.** A ``rebuild`` teardown
destroys the data directory with the server, so the database is recreated
from the application's own migrations and a major bump is free. A
``snapshot`` teardown preserves it physically in the Hetzner disk image,
where it outlives the image tag that wrote it. The six databases in
``s3_restore``'s ``PostgresDumpTarget`` list are a third path again:
``pg_dump``/``pg_restore`` is logical and crosses majors on its own.

**Where PG_VERSION lives depends on the major**, which is why the scan
looks in four places rather than one. Up to 17 the image mounts
``/var/lib/postgresql/data`` and writes ``PG_VERSION`` at its root. From
18 the recommended layout mounts ``/var/lib/postgresql`` one level up,
with the cluster at ``<major>/docker`` inside it. A stack may also pin
``PGDATA`` to a subdirectory. The volume is searched for whichever of
these exists, exactly as the image's own entrypoint scans for a legacy
cluster.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

# `postgres:<digits>` and nothing else. Deliberately strict: matching on
# the substring "postgres" also catches `postgrest/postgrest:v14.12`,
# which is an HTTP layer over a database rather than a database, has no
# data directory, and would be reported as an unparseable major forever.
_POSTGRES_IMAGE = re.compile(r"\bpostgres:(\d+)")

# Candidate locations of PG_VERSION inside the mounted volume, relative to
# its root. Order matters only for reporting; at most one exists.
_PG_VERSION_CANDIDATES = (
    "PG_VERSION",  # <=17, volume at /var/lib/postgresql/data
    "pgdata/PG_VERSION",  # explicit PGDATA under the same mount
    "data/PG_VERSION",  # volume one level up, pre-18 cluster inside
    "*/docker/PG_VERSION",  # 18+, cluster at <major>/docker
)


@dataclass(frozen=True)
class PgContainer:
    """One PostgreSQL service the deploy is about to start."""

    stack: str
    """Directory under ``stacks/`` — also the compose project name, since
    ``compose_runner`` runs ``cd stacks/<name> && docker compose up``."""

    service: str
    """Compose service name, for the message the operator reads."""

    source: str
    """Where the data directory lives: a named volume as written in the
    compose file, or an absolute host path for a bind mount."""

    is_bind: bool
    """True for a host path. Both forms need checking under the snapshot
    lifecycle — the disk image carries ``/mnt/nexus-data`` back exactly as
    it carries a named volume, so a bind-mounted cluster meets the same
    wall. The S3 ``PostgresDumpTarget`` list covers three of these on the
    *rebuild* path, where the dump is logical and crosses majors, but that
    path never sees this failure at all."""

    expected_major: int
    """Major from the image tag in the compose file.

    The tag there is a fallback — ``${IMAGE_X:-postgres:18-alpine}`` — and
    the deploy may override it from ``tofu output image_versions``. Using
    the fallback is safe because all three agree by construction: the
    override is derived from ``services.yaml``, and
    ``test_compose_fallbacks_match_the_declared_version`` fails the suite
    if a fallback ever drifts from it.
    """

    @property
    def qualified_volume(self) -> str:
        """What the operator has to name to remove it — a bind path as
        given, a named volume with the Compose project prefix."""
        return self.source if self.is_bind else f"{self.stack}_{self.source}"


@dataclass(frozen=True)
class Mismatch:
    stack: str
    service: str
    volume: str
    found_major: str
    expected_major: int
    is_bind: bool = False
    """`volume` is a host path, not a named volume — which changes both
    what it is called and how it is discarded."""


@dataclass(frozen=True)
class PreflightResult:
    checked: int
    """Containers whose volume existed and held a cluster."""

    absent: int
    """Probed, and there is no cluster there yet — a first start."""

    unverified: tuple[str, ...]
    """Containers nothing could be established for, as ``stack/service``.

    Kept apart from ``absent`` because they are different statements:
    "there is no data directory" is a finding, "the check could not look"
    is the lack of one. Folding them together would let a broken probe
    read as a clean bill of health.

    Three ways in: the probe emitted no line at all, the docker daemon was
    down so a named volume's location was unknowable, or PG_VERSION held
    something that is not a major.
    """

    mismatches: tuple[Mismatch, ...]

    @property
    def ok(self) -> bool:
        """No mismatch found. Deliberately not "and everything was
        checked": an unverifiable container should not block a deploy that
        would otherwise proceed — the caller reports it instead."""
        return not self.mismatches


class ScriptRunner(Protocol):
    def __call__(self, script: str, *, host: str) -> str: ...


def discover_pg_containers(stacks_dir: Path) -> list[PgContainer]:
    """Every PostgreSQL service across the stack compose files.

    Included when the image tag names a major and something is mounted
    under ``/var/lib/postgresql`` — named volume or bind mount alike.

    Bind mounts were excluded in the first draft, on the reasoning that
    ``/mnt/nexus-data`` is covered by the S3 layer. That is true and
    beside the point: the S3 dump is logical and only runs on the rebuild
    path, which cannot reach this failure anyway. On the snapshot path the
    disk image carries those directories back byte for byte, so
    ``dify-db``, ``forgejo-db`` and ``gitea-db`` hit the same wall as any
    named volume — and they were the three the exclusion dropped.
    """
    found: list[PgContainer] = []
    for compose in sorted(stacks_dir.glob("*/docker-compose.yml")):
        parsed = yaml.safe_load(compose.read_text())
        # One odd file must cost only itself. Without these two guards a
        # compose file parsing to a list makes `.get` raise, the phase
        # catches it and reports "partial", and every *other* stack goes
        # unchecked — the check disabled by a file it was not asked about.
        # The per-service guard below already worked this way; these are
        # the two levels above it.
        if not isinstance(parsed, dict):
            continue
        services = parsed.get("services")
        if not isinstance(services, dict):
            continue
        for service, spec in services.items():
            if not isinstance(spec, dict):
                continue
            match = _POSTGRES_IMAGE.search(str(spec.get("image", "")))
            if match is None:
                continue
            mount = _data_mount_for(spec)
            if mount is None:
                continue
            source, is_bind = mount
            found.append(
                PgContainer(
                    stack=compose.parent.name,
                    service=str(service),
                    source=source,
                    is_bind=is_bind,
                    expected_major=int(match.group(1)),
                )
            )
    return found


def _data_mount_for(spec: dict[str, object]) -> tuple[str, bool] | None:
    """``(source, is_bind)`` for the data directory, or None.

    Matches on the container-side path rather than the source, since the
    source is arbitrary — `postgres-data`, `evidence-db-data`,
    `/mnt/nexus-data/gitea/db` — while the target is always under
    /var/lib/postgresql.

    Both Compose volume syntaxes are read. Every stack uses the short
    string form today, but a long-form mapping would otherwise be skipped
    *silently*: the service drops out of the probe, and the mismatch this
    module exists to catch reaches `compose up` unannounced.
    """
    volumes = spec.get("volumes")
    if not isinstance(volumes, list):
        return None
    for entry in volumes:
        parsed = _parse_volume_entry(entry)
        if parsed is None:
            continue
        source, target, is_bind = parsed
        if not target.startswith("/var/lib/postgresql"):
            continue
        return source, is_bind
    return None


def _parse_volume_entry(entry: object) -> tuple[str, str, bool] | None:
    """``(source, target, is_bind)`` for one Compose ``volumes`` entry."""
    if isinstance(entry, str):
        if ":" not in entry:
            return None
        source, target = entry.split(":")[:2]
        return source, target, source.startswith((".", "/"))
    if isinstance(entry, dict):
        src = entry.get("source")
        tgt = entry.get("target")
        if not isinstance(src, str) or not isinstance(tgt, str):
            # `type: tmpfs` carries a target and no source; nothing to probe.
            return None
        # `type` is authoritative where present. A long-form bind may name
        # a relative source ("./initdb"), which the leading-character test
        # would read as a named volume.
        kind = entry.get("type")
        is_bind = kind == "bind" if isinstance(kind, str) else src.startswith((".", "/"))
        return src, tgt, is_bind
    return None


def render_preflight_script(containers: list[PgContainer]) -> str:
    """Bash that reads each volume's PG_VERSION and reports one line each.

    Reads the host path from ``docker volume inspect`` rather than
    guessing ``/var/lib/docker/volumes/...``: the docker root is
    configurable, and inspect is the only thing that knows where it is.

    Emits ``PGCHECK <stack> <service> <found> <expected>`` per container,
    with ``found`` set to ``-`` when the volume or the cluster is absent.
    Comparing here rather than in bash keeps the decision, the message and
    its tests in one language.
    """
    # One `docker info` up front, rather than reading each volume's
    # inspect failure as an answer. Both a stopped daemon and a
    # not-yet-created volume make `docker volume inspect` exit 1, and the
    # second is the normal case on a first deploy — so per-volume failure
    # cannot distinguish them. Asking once can: with docker up, a missing
    # volume genuinely means no cluster; with docker down, nothing about
    # named volumes is knowable and saying "absent" would be a finding
    # nobody established.
    lines = [
        "set -uo pipefail",
        "",
        "if docker info >/dev/null 2>&1; then DOCKER=ok; else DOCKER=unavailable; fi",
        'echo "PGPROBE docker $DOCKER"',
        "",
    ]
    for c in containers:
        lines.append(
            f"STACK={shlex.quote(c.stack)}; SVC={shlex.quote(c.service)}; WANT={c.expected_major}"
        )
        if c.is_bind:
            lines.append(f"MP={shlex.quote(c.source)}")
        else:
            lines.append(f"VOL={shlex.quote(c.qualified_volume)}")
            lines.append(
                'MP=$(docker volume inspect "$VOL" '
                "--format '{{.Mountpoint}}' 2>/dev/null || true)"
            )
        lines.append('FOUND="-"')
        lines.append('if [ -d "$MP" ]; then')
        lines.append(
            "  for rel in " + " ".join(shlex.quote(p) for p in _PG_VERSION_CANDIDATES) + "; do"
        )
        lines.append('    for f in "$MP"/$rel; do')
        lines.append(
            '      if [ -s "$f" ]; then FOUND=$(tr -d "[:space:]" < "$f" 2>/dev/null); break 2; fi'
        )
        lines.append("    done")
        lines.append("  done")
        # A PG_VERSION that stat says is non-empty but yields nothing —
        # unreadable, or whitespace only. Left empty it emits a
        # four-field PGCHECK line, and `parse_result` drops malformed
        # lines, so the container reaches `unverified` by way of its own
        # answer going missing. That works, and it is the shape this repo
        # calls out: the indicator must be the answer, not a by-product.
        lines.append('  if [ -z "$FOUND" ]; then FOUND="?"; fi')
        # `-` has to keep meaning "no cluster here", because that is what
        # lets the phase pass. A directory that cannot be listed, or one
        # holding files this probe does not recognise, establishes no such
        # thing — report it as undetermined and let the phase say so.
        lines.append('  if [ "$FOUND" = "-" ]; then')
        lines.append('    if ENTRIES=$(ls -A "$MP" 2>/dev/null); then')
        lines.append('      [ -n "$ENTRIES" ] && FOUND="?"')
        lines.append("    else")
        lines.append('      FOUND="?"')
        lines.append("    fi")
        lines.append("  fi")
        if not c.is_bind:
            # inspect named a mountpoint, so the volume exists; a bind
            # source that is simply not there is a genuine `-`.
            lines.append('elif [ -n "$MP" ]; then')
            lines.append('  FOUND="?"')
        lines.append("fi")
        lines.append('echo "PGCHECK $STACK $SVC $FOUND $WANT"')
        lines.append("")
    return "\n".join(lines)


def parse_result(stdout: str, containers: list[PgContainer]) -> PreflightResult:
    """Turn the ``PGCHECK`` lines into a verdict.

    The script emits one line per container unconditionally, so a missing
    line means the probe did not run there. Those are listed separately
    rather than counted as absent — see ``PreflightResult.unverified``.
    """
    by_key = {(c.stack, c.service): c for c in containers}
    checked = 0
    absent = 0
    mismatches: list[Mismatch] = []
    unreadable: list[str] = []
    seen: set[tuple[str, str]] = set()

    # A stopped daemon makes every named volume unknowable. Bind mounts
    # are unaffected — those paths are read straight off the filesystem,
    # so their answers stand on their own.
    docker_down = "PGPROBE docker unavailable" in stdout
    blind = {(c.stack, c.service) for c in containers if docker_down and not c.is_bind}

    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) != 5 or parts[0] != "PGCHECK":
            continue
        _, stack, service, found, want = parts
        if (stack, service) in blind:
            # Leave it out of `seen`, so it lands in `unverified` below.
            continue
        seen.add((stack, service))
        if found == "-":
            absent += 1
            continue
        if found == "?":
            unreadable.append(f"{stack}/{service} (data directory could not be read)")
            continue
        if not found.isdigit():
            # A PG_VERSION holding something other than a major is a
            # damaged directory, not a version. Comparing it would report
            # a mismatch naming a PostgreSQL release that does not exist,
            # which sends the operator looking for the wrong problem.
            unreadable.append(f"{stack}/{service} (PG_VERSION reads {found!r})")
            continue
        checked += 1
        if found != want:
            container = by_key.get((stack, service))
            mismatches.append(
                Mismatch(
                    stack=stack,
                    service=service,
                    volume=container.qualified_volume if container else "",
                    found_major=found,
                    expected_major=int(want),
                    is_bind=container.is_bind if container else False,
                )
            )

    unverified = tuple(
        [f"{c.stack}/{c.service}" for c in containers if (c.stack, c.service) not in seen]
        + unreadable
    )
    return PreflightResult(
        checked=checked, absent=absent, unverified=unverified, mismatches=tuple(mismatches)
    )


def format_failure(mismatches: tuple[Mismatch, ...]) -> str:
    """The message an operator reads instead of hunting through logs.

    Names both versions and both ways out, because the wrong instinct
    here is to re-run the deploy — which reproduces the restart loop
    exactly.
    """
    out = [
        "❌ PostgreSQL data directory was written by a different major version.",
        "",
        "   Starting these containers would fail with 'database files are",
        "   incompatible with server' and leave them restart-looping:",
        "",
    ]
    for m in mismatches:
        where = "bind mount" if m.is_bind else "volume"
        out.append(
            f"     {m.stack}/{m.service}: data is PostgreSQL {m.found_major}, "
            f"image is {m.expected_major}  ({where} {m.volume})"
        )
    out += [
        "",
        "   Re-running the deploy will not help — it reproduces the same loop.",
        "   Two ways out, per database:",
        "",
        "     1. Migrate the data. Start the OLD major against the volume,",
        "        `pg_dump` it, start the new one against an empty volume and",
        "        `pg_restore` into it.",
        "     2. Discard the data, if the stack can rebuild it, then deploy",
        "        again. A bind mount is emptied rather than removed, so that",
        "        the ownership `setup` gave the directory survives:",
        "",
    ]
    for m in mismatches:
        # `find -mindepth 1 -delete` over `rm -rf <dir>/*`: it takes
        # dotfiles too, and leaves the directory itself in place.
        # Quoted because the line is meant to be copy-pasted. `shlex.quote`
        # leaves an ordinary /mnt/nexus-data path untouched, so this costs
        # nothing in the common case and keeps the odd one executable.
        target = shlex.quote(m.volume)
        out.append(
            f"        find {target} -mindepth 1 -delete"
            if m.is_bind
            else f"        docker volume rm {target}"
        )
    out += [
        "",
        "   Reached only under the snapshot lifecycle — a rebuild teardown",
        "   drops the volume with the server, so the same bump is free there.",
        "   See docs/admin-guides/snapshot-lifecycle.md.",
    ]
    return "\n".join(out)


def run_preflight(
    enabled: list[str],
    *,
    stacks_dir: Path,
    host: str = "nexus",
    script_runner: ScriptRunner | None = None,
) -> PreflightResult:
    """Render → exec → parse, for the enabled stacks only.

    Restricting to ``enabled`` is not an optimisation: a disabled stack's
    volume may well hold an old cluster, and reporting it would block a
    deploy over a database nothing is about to start. The check has to
    describe the run that is happening.
    """
    wanted = set(enabled)
    containers = [c for c in discover_pg_containers(stacks_dir) if c.stack in wanted]
    if not containers:
        return PreflightResult(checked=0, absent=0, unverified=(), mismatches=())

    runner = script_runner or _default_runner
    stdout = runner(render_preflight_script(containers), host=host)
    return parse_result(stdout, containers)


def _default_runner(script: str, *, host: str) -> str:
    from nexus_deploy import _remote

    # check=False: a non-zero status means the probe itself could not run.
    # Raising here would turn "could not look" into "must not deploy",
    # which is the wrong trade for a check that only ever prevents a
    # restart loop. Containers with no PGCHECK line land in
    # `PreflightResult.unverified`, which the caller reports — so the gap
    # is visible without being fatal.
    return _remote.ssh_run_script(script, host=host, check=False).stdout

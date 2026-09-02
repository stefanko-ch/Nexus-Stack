"""The PostgreSQL major-version preflight (#734).

The rendered bash runs for real against fixture directories — the same
approach as tests/unit/test_repo_secret_script.py — because the part worth
testing is whether it finds a PG_VERSION wherever the image happens to put
it, and that is a filesystem question rather than a string question.

Bind mounts are used throughout for the probe tests: a named volume needs
`docker volume inspect` to resolve, and shimming that would test the shim.
The bind path and the volume path differ only in how the mountpoint is
obtained, which `test_named_volumes_are_resolved_through_docker` covers on
its own.
"""

from __future__ import annotations

import shlex
import subprocess
import textwrap
from pathlib import Path

import pytest

from nexus_deploy.pg_preflight import (
    _POSTGRES_IMAGE,
    Mismatch,
    PgContainer,
    discover_pg_containers,
    format_failure,
    parse_result,
    render_preflight_script,
    run_preflight,
)


def _bind(stack: str, path: Path, major: int) -> PgContainer:
    return PgContainer(
        stack=stack, service=f"{stack}-db", source=str(path), is_bind=True, expected_major=major
    )


def _probe(containers: list[PgContainer]) -> str:
    proc = subprocess.run(
        ["bash", "-c", render_preflight_script(containers)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


# ---------------------------------------------------------------------------
# Finding PG_VERSION where the image actually puts it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("relative", "label"),
    [
        ("PG_VERSION", "<=17: volume at /var/lib/postgresql/data"),
        ("pgdata/PG_VERSION", "explicit PGDATA under the same mount"),
        ("data/PG_VERSION", "volume one level up, pre-18 cluster inside"),
        ("18/docker/PG_VERSION", "18+: cluster at <major>/docker"),
    ],
)
def test_a_cluster_is_found_in_every_supported_layout(
    tmp_path: Path, relative: str, label: str
) -> None:
    """All four layouts exist in this repo simultaneously.

    Nineteen stacks still mount `/var/lib/postgresql/data`, five use the
    18 layout one level up, and the shared `postgres` stack pins PGDATA to
    a subdirectory. A check that knew only one of them would pass by
    finding nothing, which is the failure mode worth guarding: absent and
    fine are the same output.
    """
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("16\n")

    out = _probe([_bind("s", tmp_path, 18)])

    assert "PGCHECK s s-db 16 18" in out, f"not found for {label}"


def test_a_mismatch_is_reported_with_both_versions(tmp_path: Path) -> None:
    (tmp_path / "PG_VERSION").write_text("16\n")
    containers = [_bind("shared", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert not result.ok
    assert result.checked == 1
    (mismatch,) = result.mismatches
    assert mismatch.found_major == "16"
    assert mismatch.expected_major == 18


def test_a_matching_major_is_silent(tmp_path: Path) -> None:
    (tmp_path / "18" / "docker").mkdir(parents=True)
    (tmp_path / "18" / "docker" / "PG_VERSION").write_text("18\n")
    containers = [_bind("evidence", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert result.ok
    assert result.checked == 1
    assert result.absent == 0


def test_an_empty_directory_is_absent_not_a_mismatch(tmp_path: Path) -> None:
    """A first start, and the common case on the rebuild lifecycle.

    Reporting it would block every deploy that creates a database.
    """
    containers = [_bind("fresh", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert result.ok
    assert result.absent == 1
    assert result.checked == 0


def test_a_missing_directory_is_absent(tmp_path: Path) -> None:
    containers = [_bind("gone", tmp_path / "never-created", 18)]

    result = parse_result(_probe(containers), containers)

    assert result.ok
    assert result.absent == 1


def test_an_empty_pg_version_file_is_not_read_as_a_version(tmp_path: Path) -> None:
    """A zero-byte PG_VERSION is a half-written directory, not a cluster.

    Treating it as a version would compare "" against the major and report
    a mismatch naming a version nobody has. Nor is it `absent`: the
    directory is not empty, so something is there and this probe could not
    say what — the deploy proceeds, but the phase reports partial.
    """
    (tmp_path / "PG_VERSION").write_text("")
    containers = [_bind("half", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert result.ok
    assert result.absent == 0
    assert result.unverified == ("half/half-db (data directory could not be read)",)


# ---------------------------------------------------------------------------
# Result semantics
# ---------------------------------------------------------------------------


def test_a_container_the_probe_said_nothing_about_is_unverified(tmp_path: Path) -> None:
    """Not folded into `absent`, which would read as "checked, nothing there".

    A probe that could not run is the absence of a finding, and letting it
    look like a clean result is the silent outcome this module removes.
    """
    containers = [_bind("a", tmp_path, 18), _bind("b", tmp_path, 18)]

    result = parse_result("PGCHECK a a-db - 18\n", containers)

    assert result.unverified == ("b/b-db",)
    assert result.absent == 1
    assert result.ok, "an unverifiable container must not block a deploy on its own"


def test_unparseable_lines_are_ignored_rather_than_guessed_at(tmp_path: Path) -> None:
    """The probe's stdout carries whatever the remote shell also wrote."""
    containers = [_bind("a", tmp_path, 18)]

    result = parse_result(
        "Warning: something unrelated\nPGCHECK a a-db 16 18\ndebug noise\n", containers
    )

    assert len(result.mismatches) == 1
    assert result.unverified == ()


# ---------------------------------------------------------------------------
# Discovery over the real compose files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("postgres:18-alpine", "18"),
        ("${IMAGE_EVIDENCE_DB:-postgres:18-alpine}", "18"),
        ("postgres:14-alpine", "14"),
        ("postgrest/postgrest:v14.12", None),
        ("postgres-exporter:latest", None),
        ("timescale/timescaledb:2.14.2-pg16", None),
    ],
)
def test_the_image_pattern_matches_a_server_and_nothing_adjacent(
    image: str, expected: str | None
) -> None:
    """`postgres:<digits>` and nothing else.

    Pinned directly rather than through discovery, because discovery does
    not actually depend on it: `postgrest` has no mount under
    /var/lib/postgresql, so it drops out on that check whatever the
    pattern does. Loosening the regex to a lazy substring match leaves the
    end-to-end assertion green — verified by trying it — so without this
    test the pattern is unpinned and the guard is accidental.

    timescaledb is the one that would actually slip through a loose
    pattern: it *is* a PostgreSQL server with a data directory, but its
    tag names the PG major as a suffix, and reading `2` from `2.14.2` as
    the major would report a mismatch against every real cluster.
    """
    match = _POSTGRES_IMAGE.search(image)

    assert (match.group(1) if match else None) == expected


def test_postgrest_is_not_discovered_as_a_database() -> None:
    """The end-to-end half of the above: whatever excludes it, it is out."""
    stacks = {c.stack for c in discover_pg_containers(Path("stacks"))}

    assert "postgrest" not in stacks


def test_bind_mounted_databases_are_checked_too() -> None:
    """dify, forgejo and gitea keep their clusters under /mnt/nexus-data.

    They were excluded in the first draft because the S3 layer covers
    them — true, and irrelevant: that dump is logical and only runs on the
    rebuild path, which never meets this failure. The snapshot path
    restores those directories physically, so they hit the same wall.
    """
    by_stack = {c.stack: c for c in discover_pg_containers(Path("stacks"))}

    for stack in ("dify", "forgejo", "gitea"):
        assert stack in by_stack, f"{stack} must be checked"
        assert by_stack[stack].is_bind
        assert by_stack[stack].qualified_volume.startswith("/mnt/nexus-data/")


def test_named_volumes_are_resolved_through_docker() -> None:
    """The compose project name prefixes the volume, and the mountpoint
    comes from `docker volume inspect` rather than a guess at
    /var/lib/docker — the docker root is configurable."""
    containers = discover_pg_containers(Path("stacks"))
    evidence = next(c for c in containers if c.stack == "evidence")

    assert evidence.qualified_volume == "evidence_evidence-db-data"
    assert "docker volume inspect" in render_preflight_script([evidence])


def test_every_discovered_container_declares_a_known_major() -> None:
    """A tag the regex cannot parse would silently drop that database from
    the check, which looks identical to having no databases."""
    containers = discover_pg_containers(Path("stacks"))

    assert containers, "discovery found nothing — the glob or the regex is wrong"
    assert all(9 <= c.expected_major <= 99 for c in containers)


def test_only_enabled_stacks_are_probed(tmp_path: Path) -> None:
    """A disabled stack's volume may hold an old cluster, and blocking a
    deploy over a database nothing is about to start would describe a run
    that is not happening."""
    seen: list[str] = []

    def runner(script: str, *, host: str) -> str:
        seen.append(script)
        return ""

    run_preflight(["evidence"], stacks_dir=Path("stacks"), script_runner=runner)

    (script,) = seen
    assert "evidence" in script
    assert "hedgedoc" not in script


def test_no_enabled_postgres_means_no_remote_call() -> None:
    called = False

    def runner(script: str, *, host: str) -> str:
        nonlocal called
        called = True
        return ""

    result = run_preflight(["grafana"], stacks_dir=Path("stacks"), script_runner=runner)

    assert not called
    assert result.ok


# ---------------------------------------------------------------------------
# The message
# ---------------------------------------------------------------------------


def test_the_failure_message_carries_what_the_operator_needs(tmp_path: Path) -> None:
    """Both versions, the volume to act on, and that a retry is not it.

    The wrong instinct here is to re-run the deploy, which reproduces the
    restart loop exactly — so the message has to say so rather than only
    describe the state.
    """
    (tmp_path / "PG_VERSION").write_text("16\n")
    containers = [_bind("shared", tmp_path, 18)]

    message = format_failure(parse_result(_probe(containers), containers).mismatches)

    assert "PostgreSQL 16" in message
    assert "image is 18" in message
    assert str(tmp_path) in message
    assert "Re-running the deploy will not help" in message
    assert "pg_dump" in message
    # A bind mount, so the discard command has to be the one that works
    # on a directory — see the dedicated test below.
    assert f"find {tmp_path} -mindepth 1 -delete" in message
    assert "snapshot lifecycle" in message


def test_the_rendered_script_is_valid_bash() -> None:
    script = render_preflight_script(discover_pg_containers(Path("stacks")))

    proc = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr


def test_paths_with_spaces_survive_the_shell(tmp_path: Path) -> None:
    """Every value reaching bash is shlex-quoted. Nothing in this repo has
    a space today, which is exactly why an unquoted expansion would go
    unnoticed until someone's path did."""
    awkward = tmp_path / "a dir with spaces"
    awkward.mkdir()
    (awkward / "PG_VERSION").write_text("16\n")
    containers = [_bind("odd", awkward, 18)]

    result = parse_result(_probe(containers), containers)

    assert len(result.mismatches) == 1


def test_module_docstring_names_the_lifecycle_that_can_reach_this() -> None:
    """The check is unreachable on the rebuild path, and someone reading
    the module should learn that before wondering why it never fires."""
    from nexus_deploy import pg_preflight

    assert pg_preflight.__doc__ is not None
    doc = textwrap.dedent(pg_preflight.__doc__)
    assert "snapshot" in doc
    assert "rebuild" in doc


# ---------------------------------------------------------------------------
# When the probe itself cannot answer
# ---------------------------------------------------------------------------


def test_a_stopped_docker_daemon_makes_named_volumes_unverified(tmp_path: Path) -> None:
    """Not `absent`, which would read as "checked, no cluster there".

    The distinction needs a separate question, because `docker volume
    inspect` exits 1 both when the daemon is down and when the volume has
    simply not been created — and the second is the normal case on a first
    deploy. Reading per-volume failure as "unknowable" would flag every
    first deploy; reading it as "absent" hides a dead daemon. The script
    asks `docker info` once instead.
    """
    named = PgContainer(
        stack="evidence", service="evidence-db", source="db-data", is_bind=False, expected_major=18
    )

    result = parse_result(
        "PGPROBE docker unavailable\nPGCHECK evidence evidence-db - 18\n", [named]
    )

    assert result.unverified == ("evidence/evidence-db",)
    assert result.absent == 0
    assert result.checked == 0


def test_a_stopped_daemon_does_not_taint_bind_mounts(tmp_path: Path) -> None:
    """Those paths are read off the filesystem, so their answers stand."""
    (tmp_path / "PG_VERSION").write_text("16\n")
    containers = [_bind("gitea", tmp_path, 17)]

    result = parse_result("PGPROBE docker unavailable\n" + _probe(containers), containers)

    assert result.unverified == ()
    assert len(result.mismatches) == 1


def test_the_script_reports_the_daemon_state_before_anything_else() -> None:
    """Verified against a real stopped daemon rather than a stub: with
    docker down on this machine the line reads `unavailable`, and with it
    up the same script reads `ok`."""
    script = render_preflight_script([])

    assert "docker info" in script
    assert 'echo "PGPROBE docker $DOCKER"' in script


def test_a_pg_version_that_is_not_a_number_is_unverified(tmp_path: Path) -> None:
    """A damaged directory, not a version.

    Comparing it would report a mismatch naming a PostgreSQL release that
    does not exist, sending the operator after the wrong problem.
    """
    containers = [_bind("odd", tmp_path, 18)]

    result = parse_result("PGCHECK odd odd-db garbage 18\n", containers)

    assert result.mismatches == ()
    assert result.checked == 0
    assert len(result.unverified) == 1
    assert "garbage" in result.unverified[0]


# ---------------------------------------------------------------------------
# Malformed compose entries must not take the discovery down
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("volumes", "why"),
    [
        (None, "no volumes key at all"),
        ([], "empty volumes list"),
        ("postgres-data:/var/lib/postgresql/data", "a string where a list belongs"),
        ([{"type": "volume", "source": "d"}], "long-form mount with no target"),
        (["postgres-data"], "an anonymous volume, no colon"),
        ([42], "an entry that is neither a string nor a mapping"),
        (["./conf:/etc/postgresql/postgresql.conf"], "a mount that is not the data dir"),
    ],
)
def test_a_service_without_a_recognisable_data_mount_is_skipped(
    tmp_path: Path, volumes: object, why: str
) -> None:
    """Discovery walks every stack, so one odd entry must not raise.

    Skipping is right where the data directory genuinely cannot be located
    — but it has to skip rather than crash the deploy before compose-up.
    A long-form mount naming a target is *not* in this list; see
    `test_a_long_form_data_mount_is_discovered`.
    """
    stack = tmp_path / "odd"
    stack.mkdir()
    spec: dict[str, object] = {"image": "postgres:18-alpine"}
    if volumes is not None:
        spec["volumes"] = volumes
    (stack / "docker-compose.yml").write_text(
        __import__("yaml").safe_dump({"services": {"odd-db": spec}})
    )

    assert discover_pg_containers(tmp_path) == [], f"should skip: {why}"


def test_a_compose_file_with_no_services_is_skipped(tmp_path: Path) -> None:
    stack = tmp_path / "empty"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text("services:\n")

    assert discover_pg_containers(tmp_path) == []


# ---------------------------------------------------------------------------
# Long-form compose mounts are read, not silently skipped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "source", "is_bind", "why"),
    [
        (
            {"type": "volume", "source": "db-data", "target": "/var/lib/postgresql"},
            "db-data",
            False,
            "long-form named volume",
        ),
        (
            {"type": "bind", "source": "/mnt/nexus-data/x/db", "target": "/var/lib/postgresql"},
            "/mnt/nexus-data/x/db",
            True,
            "long-form bind by absolute path",
        ),
        (
            {"type": "bind", "source": "./db", "target": "/var/lib/postgresql/data"},
            "./db",
            True,
            "relative bind — only `type` says it is one",
        ),
    ],
)
def test_a_long_form_data_mount_is_discovered(
    tmp_path: Path, entry: dict[str, str], source: str, is_bind: bool, why: str
) -> None:
    """Skipping one would be silent, and silence here reads as success.

    A service that drops out of discovery is not reported as unverified —
    nothing knows it existed. The mismatch this module exists to catch
    would reach compose-up unannounced, which is the one outcome the phase
    must never produce.
    """
    stack = tmp_path / "lf"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text(
        __import__("yaml").safe_dump(
            {"services": {"lf-db": {"image": "postgres:18-alpine", "volumes": [entry]}}}
        )
    )

    found = discover_pg_containers(tmp_path)

    assert len(found) == 1, f"not discovered: {why}"
    assert found[0].source == source
    assert found[0].is_bind is is_bind


# ---------------------------------------------------------------------------
# `absent` has to mean "verified empty", because it is what lets the deploy run
# ---------------------------------------------------------------------------


def test_a_directory_that_cannot_be_listed_is_unverified_not_absent(tmp_path: Path) -> None:
    """The dangerous reading: unreadable looks exactly like uninitialised.

    Both leave the probe with no PG_VERSION. Counting the first as absent
    lets the phase pass on a directory whose major nobody established —
    here one holding PostgreSQL 17 under an image asking for 18.
    """
    data = tmp_path / "locked"
    data.mkdir()
    (data / "PG_VERSION").write_text("17\n")
    data.chmod(0o000)
    containers = [_bind("locked", data, 18)]
    try:
        result = parse_result(_probe(containers), containers)
    finally:
        data.chmod(0o755)

    assert result.absent == 0
    assert len(result.unverified) == 1
    assert "locked/locked-db" in result.unverified[0]


def test_a_non_empty_directory_with_no_cluster_is_unverified(tmp_path: Path) -> None:
    """A layout none of the four candidates match must not read as empty.

    An uninitialised volume is empty. Files this probe does not recognise
    mean it looked in the wrong place, not that there is nothing there.
    """
    (tmp_path / "something").write_text("x")
    containers = [_bind("odd", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert result.absent == 0
    assert result.unverified == ("odd/odd-db (data directory could not be read)",)


def test_a_genuinely_empty_directory_is_still_absent(tmp_path: Path) -> None:
    """The counterpart — first deploy has to stay quiet, not go partial."""
    containers = [_bind("fresh", tmp_path, 18)]

    result = parse_result(_probe(containers), containers)

    assert result.absent == 1
    assert result.unverified == ()
    assert result.ok


# ---------------------------------------------------------------------------
# The recovery command has to exist for the thing it names
# ---------------------------------------------------------------------------


def test_a_bind_mount_is_named_and_discarded_as_a_directory() -> None:
    """`docker volume rm /mnt/nexus-data/gitea/db` removes nothing.

    Three of the six persisted databases are bind mounts, so the wrong
    command is the likely one. It fails with 'no such volume' and sends
    the operator looking for a volume that was never there.
    """
    text = format_failure(
        (
            Mismatch("gitea", "gitea-db", "/mnt/nexus-data/gitea/db", "16", 17, is_bind=True),
            Mismatch("shared", "postgres", "postgres_pg-data", "17", 18, is_bind=False),
        )
    )

    assert "bind mount /mnt/nexus-data/gitea/db" in text
    assert "find /mnt/nexus-data/gitea/db -mindepth 1 -delete" in text
    assert "docker volume rm /mnt/nexus-data/gitea/db" not in text
    # The named volume keeps the command that does work for it.
    assert "volume postgres_pg-data" in text
    assert "docker volume rm postgres_pg-data" in text


# ---------------------------------------------------------------------------
# The answer has to be the signal, never a side effect of a broken line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "mode", "why"),
    [
        ("17\n", 0o000, "exists and is non-empty, but cannot be read"),
        ("   \n", 0o644, "readable, but holds nothing once whitespace is stripped"),
    ],
)
def test_a_pg_version_that_yields_nothing_says_so_itself(
    tmp_path: Path, content: str, mode: int, why: str
) -> None:
    """`[ -s ]` calls stat, which needs no read permission on the file.

    So the guard passes and the read that follows produces an empty
    string. Emitting that would make a four-field PGCHECK line, and
    `parse_result` drops malformed lines — the container would still reach
    `unverified`, but by way of its own answer going missing rather than
    by giving one. CLAUDE.md names that shape: the indicator must not be a
    by-product. Assert the field count, since that is what breaks.
    """
    (tmp_path / "PG_VERSION").write_text(content)
    (tmp_path / "PG_VERSION").chmod(mode)
    containers = [_bind("mute", tmp_path, 18)]
    try:
        out = _probe(containers)
    finally:
        (tmp_path / "PG_VERSION").chmod(0o644)

    line = next(x for x in out.splitlines() if x.startswith("PGCHECK"))
    assert len(line.split()) == 5, f"malformed line for: {why}"
    assert line == "PGCHECK mute mute-db ? 18"

    result = parse_result(out, containers)
    assert result.absent == 0
    assert result.unverified == ("mute/mute-db (data directory could not be read)",)


def test_the_discard_command_stays_a_valid_shell_command(tmp_path: Path) -> None:
    """The line exists to be copy-pasted, so it has to survive the paste.

    An unquoted path with a space splits into two arguments: `find` reads
    the first as its starting point and the second as an expression, and
    the operator gets an error naming neither. Quoting is free for the
    ordinary /mnt/nexus-data paths — `shlex.quote` leaves those alone.
    """
    odd = tmp_path / "with space"
    odd.mkdir()
    text = format_failure((Mismatch("odd", "db", str(odd), "16", 17, is_bind=True),))

    command = next(x for x in text.splitlines() if "find" in x).strip()
    assert command == f"find {shlex.quote(str(odd))} -mindepth 1 -delete"

    # Executable as printed: run it and confirm it emptied the directory.
    (odd / "PG_VERSION").write_text("16\n")
    assert subprocess.run(["bash", "-c", command], check=False).returncode == 0
    assert list(odd.iterdir()) == []
    assert odd.is_dir(), "the directory itself must survive, ownership with it"

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

import subprocess
import textwrap
from pathlib import Path

import pytest

from nexus_deploy.pg_preflight import (
    _POSTGRES_IMAGE,
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
    a mismatch naming a version nobody has.
    """
    (tmp_path / "PG_VERSION").write_text("")

    result = parse_result(_probe([_bind("half", tmp_path, 18)]), [_bind("half", tmp_path, 18)])

    assert result.ok
    assert result.absent == 1


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
    assert "docker volume rm" in message
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

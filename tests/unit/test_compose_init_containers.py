"""A failing one-shot init container fails its stack (#976).

The rendered compose-up script runs for real against a stand-in `docker` on
PATH. Each test describes the stack's containers as `docker inspect` would
report them, possibly changing from one poll to the next, and checks the
RESULT line and the message the script prints.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from nexus_deploy import compose_runner

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bash_version() -> tuple[int, int]:
    out = subprocess.run(
        ["bash", "-c", "echo ${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return int(out[0]), int(out[1])


# The rendered script expands possibly empty arrays under `set -u`, which
# bash only allows from 4.4 on. The server runs bash 5; macOS ships 3.2.
needs_modern_bash = pytest.mark.skipif(
    _bash_version() < (4, 4), reason="needs bash 4.4+, as the server has"
)

# `docker` stand-in. Behaviour comes from $FAKE_DOCKER_STATE, a JSON file:
#   {"ps": "<docker ps output>",
#    "init": {"<id>": {"service": "...", "states": ["<inspect line>", ...]}}}
# Each `docker inspect` of an id returns the next state in its list, and
# keeps returning the last one.
_FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, sys
state_file = os.environ["FAKE_DOCKER_STATE"]
state = json.load(open(state_file))
args = sys.argv[1:]
if args[:1] == ["compose"] and "up" in args:
    sys.exit(0)
if args[:1] == ["compose"] and "config" in args:
    if state.get("config_fails"):
        sys.exit(1)
    services = {"flowise"} | {c["service"] for c in state["init"].values() if not c.get("orphan")}
    print("\n".join(sorted(services)))
    sys.exit(0)
if args[:1] == ["compose"] and "ps" in args:
    if state.get("ps_fails"):
        sys.exit(1)
    wanted = args[-1]
    for cid, c in state["init"].items():
        if c["service"] == wanted:
            print(cid)
    sys.exit(0)
if args[:1] == ["ps"]:
    print(state["ps"])
    sys.exit(0)
if args[:1] == ["inspect"]:
    cid = args[-1]
    c = state["init"][cid]
    seen = c.setdefault("seen", 0)
    line = c["states"][min(seen, len(c["states"]) - 1)]
    c["seen"] = seen + 1
    json.dump(state, open(state_file, "w"))
    print(line)
    sys.exit(0)
sys.exit(0)
"""


def _run(
    tmp_path: Path,
    init: dict[str, dict[str, object]],
    *,
    wait_s: int = 30,
    **flags: bool,
) -> subprocess.CompletedProcess[str]:
    stacks = tmp_path / "stacks"
    (stacks / "flowise").mkdir(parents=True)
    (stacks / "flowise" / "docker-compose.yml").write_text("services: {}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(_FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")  # polling without waiting
    (bin_dir / "sleep").chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"ps": "flowise", "init": init, **flags}))

    script = compose_runner.render_remote_script(parents=[], leaves=["flowise"], init_wait_s=wait_s)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DOCKER_STATE": str(state),
    }
    return subprocess.run(
        ["bash", "-c", _with_stacks_dir(script, stacks)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _with_stacks_dir(script: str, stacks: Path) -> str:
    lines = script.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("STACKS_DIR="):
            lines[i] = f"STACKS_DIR={stacks}"
            break
    else:  # pragma: no cover - the script always sets it
        raise AssertionError("no STACKS_DIR line in the rendered script")
    return "\n".join(lines)


def _inspect(
    status: str, code: int, restarts: int = 0, policy: str = "no", maximum: int = 0
) -> str:
    return f"/flowise-init {status} {code} {restarts} {policy} {maximum}"


@needs_modern_bash
def test_an_init_that_succeeds_leaves_the_stack_started(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        {
            "i1": {
                "service": "flowise-init",
                "states": [_inspect("running", 0), _inspect("exited", 0)],
            }
        },
    )
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


@needs_modern_bash
def test_an_init_that_exits_non_zero_fails_the_stack(tmp_path: Path) -> None:
    result = _run(tmp_path, {"i1": {"service": "flowise-init", "states": [_inspect("exited", 1)]}})
    assert "RESULT started=0 failed=1" in result.stdout, result.stderr
    assert "flowise init failed: flowise-init exited with 1" in result.stderr


@needs_modern_bash
def test_a_restarting_init_is_waited_for_until_it_succeeds(tmp_path: Path) -> None:
    """on-failure:3: a non-zero exit with restarts left is not final."""
    states = [
        _inspect("exited", 1, restarts=0, policy="on-failure", maximum=3),
        _inspect("restarting", 1, restarts=1, policy="on-failure", maximum=3),
        _inspect("exited", 0, restarts=1, policy="on-failure", maximum=3),
    ]
    result = _run(tmp_path, {"i1": {"service": "flowise-init", "states": states}})
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


@needs_modern_bash
def test_an_init_that_used_up_its_restarts_fails_the_stack(tmp_path: Path) -> None:
    states = [_inspect("exited", 1, restarts=3, policy="on-failure", maximum=3)]
    result = _run(tmp_path, {"i1": {"service": "flowise-init", "states": states}})
    assert "RESULT started=0 failed=1" in result.stdout, result.stderr


@needs_modern_bash
def test_an_init_still_running_at_the_deadline_fails_the_stack(tmp_path: Path) -> None:
    result = _run(
        tmp_path, {"i1": {"service": "flowise-init", "states": [_inspect("running", 0)]}}, wait_s=0
    )
    assert "RESULT started=0 failed=1" in result.stdout, result.stderr
    assert "still running after 0s" in result.stderr


@needs_modern_bash
def test_a_stack_without_an_init_container_is_not_held_up(tmp_path: Path) -> None:
    result = _run(tmp_path, {})
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


@needs_modern_bash
@pytest.mark.parametrize("name", ["flowise-initializer", "init", "flowise-init-db"])
def test_only_services_named_dash_init_count(tmp_path: Path, name: str) -> None:
    result = _run(tmp_path, {"i1": {"service": name, "states": [_inspect("exited", 1)]}})
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


def test_every_unwaited_one_shot_service_is_named_dash_init() -> None:
    """The check finds init containers by name. A one-shot service that no
    other service waits for, under another name, would fail unnoticed."""
    offenders = []
    for compose_file in sorted((REPO_ROOT / "stacks").glob("*/docker-compose.yml")):
        services = (yaml.safe_load(compose_file.read_text()) or {}).get("services") or {}
        waited = {
            dep
            for svc in services.values()
            if isinstance(svc.get("depends_on"), dict)
            for dep, cond in svc["depends_on"].items()
            if isinstance(cond, dict) and cond.get("condition") == "service_completed_successfully"
        }
        for name, svc in services.items():
            # Compose's default restart policy is "no": a service without one
            # is one-shot as far as this rule is concerned.
            restart = str(svc.get("restart", "no"))
            one_shot = restart in ("no", "False") or restart.startswith("on-failure")
            if one_shot and name not in waited and not name.endswith("-init"):
                offenders.append(f"{compose_file.parent.name}/{name}")
    assert not offenders, (
        f"one-shot services nothing waits for, not named `-init`: {offenders}. "
        f"Rename them, or make the main service depends_on them with "
        f"service_completed_successfully."
    )


@needs_modern_bash
def test_unlimited_restarts_are_waited_for_until_the_deadline(tmp_path: Path) -> None:
    """on-failure without a limit reports a maximum of 0: not used up."""
    states = [
        _inspect("exited", 1, restarts=5, policy="on-failure", maximum=0),
        _inspect("exited", 0, restarts=6, policy="on-failure", maximum=0),
    ]
    result = _run(tmp_path, {"i1": {"service": "flowise-init", "states": states}})
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


@needs_modern_bash
def test_an_orphaned_init_container_is_not_this_stacks_init(tmp_path: Path) -> None:
    """A container of a service no longer in the compose file is ignored."""
    result = _run(
        tmp_path,
        {"old": {"service": "flowise-old-init", "orphan": True, "states": [_inspect("exited", 1)]}},
    )
    assert "RESULT started=1 failed=0" in result.stdout, result.stderr


@needs_modern_bash
@pytest.mark.parametrize("flag", ["config_fails", "ps_fails"])
def test_a_lookup_that_fails_fails_the_stack(tmp_path: Path, flag: str) -> None:
    result = _run(
        tmp_path,
        {"i1": {"service": "flowise-init", "states": [_inspect("exited", 0)]}},
        **{flag: True},
    )
    assert "RESULT started=0 failed=1" in result.stdout, result.stderr
    assert "could not" in result.stderr

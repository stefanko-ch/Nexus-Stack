"""The pull-request check that builds changed stack images.

`.github/workflows/stack-image-builds.yaml` builds every stack image a pull
request touches and runs the stack's `image-test.sh` inside it. Three things
are pinned here: which stacks the detection script selects, that the
workflow builds an image the way compose does, and that every proven stack
which builds an image ships a test for it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STACKS_DIR = REPO_ROOT / "stacks"
SCRIPT = REPO_ROOT / ".github" / "scripts" / "changed-image-stacks.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "stack-image-builds.yaml"
SERVICES = yaml.safe_load((REPO_ROOT / "services.yaml").read_text())["services"]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("changed_image_stacks", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECT = _load_script()


@pytest.fixture
def stacks(tmp_path: Path) -> Path:
    """Three stacks: one with an image and a test, one with an image, one without."""
    root = tmp_path / "stacks"
    for name in ("tested", "untested", "plain"):
        (root / name).mkdir(parents=True)
        (root / name / "docker-compose.yml").write_text("services: {}\n")
    (root / "tested" / "Dockerfile").write_text("FROM scratch\n")
    (root / "tested" / "image-test.sh").write_text("#!/bin/bash\n")
    (root / "untested" / "Dockerfile").write_text("FROM scratch\n")
    return root


# ---- which stacks are selected ------------------------------------------------------


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ([], []),
        (["README.md", "src/nexus_deploy/ssh.py"], []),
        (["stacks/tested/Dockerfile"], ["tested"]),
        (["stacks/tested/requirements.txt"], ["tested"]),
        (["stacks/tested/scripts/migrate.sh"], ["tested"]),
        (["stacks/untested/docker-compose.yml"], ["untested"]),
        (["stacks/plain/docker-compose.yml"], []),
        (["stacks/gone/Dockerfile"], []),
        (["stacks/tested"], []),
        (["docs/stacks/tested/Dockerfile"], []),
        (["stacks/untested/Dockerfile", "stacks/tested/Dockerfile"], ["tested", "untested"]),
    ],
)
def test_a_stack_is_built_when_its_folder_changed_and_it_has_a_dockerfile(
    stacks: Path, changed: list[str], expected: list[str]
) -> None:
    assert SELECT.stacks_to_build(changed, stacks) == expected


@pytest.mark.parametrize("check_file", SELECT.CHECK_FILES)
def test_a_change_to_the_check_builds_every_tested_image(stacks: Path, check_file: str) -> None:
    assert SELECT.stacks_to_build([check_file], stacks) == ["tested"]
    assert SELECT.stacks_to_build([check_file, "stacks/untested/Dockerfile"], stacks) == [
        "tested",
        "untested",
    ]


def test_the_files_that_count_as_the_check_exist() -> None:
    missing = [path for path in SELECT.CHECK_FILES if not (REPO_ROOT / path).is_file()]
    assert not missing, f"CHECK_FILES names files that are not there: {missing}"


def test_the_script_prints_a_json_list(stacks: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(stacks)],
        input="stacks/tested/Dockerfile\n\nREADME.md\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == ["tested"]


def test_a_missing_stacks_directory_is_an_error_not_an_empty_list(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nowhere")],
        input="stacks/tested/Dockerfile\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


# ---- the workflow --------------------------------------------------------------------


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(loaded, dict)
    return loaded


def test_the_workflow_runs_when_a_stack_or_the_check_changes() -> None:
    # PyYAML reads the bare key `on` as the boolean True.
    paths = _workflow()[True]["pull_request"]["paths"]
    assert "stacks/**" in paths
    for check_file in SELECT.CHECK_FILES:
        assert check_file in paths, f"a change to {check_file} would not run the check"


def test_the_diff_reports_paths_the_selection_can_match() -> None:
    """Two git defaults would each hide a stack from the selection.

    Rename detection reports a file moved out of a stack folder under its new
    path only. `core.quotePath` prints a non-ASCII path quoted and escaped,
    so its first component is `"stacks` and matches nothing.
    """
    run = next(
        str(step["run"])
        for step in _workflow()["jobs"]["detect"]["steps"]
        if step.get("id") == "list"
    )
    diff = next(line for line in run.splitlines() if "git " in line and " diff " in line)
    assert "--no-renames" in diff, diff
    assert "-c core.quotePath=false" in diff, diff
    assert "--name-only" in diff, diff


def test_a_path_with_non_ascii_characters_selects_its_stack(stacks: Path) -> None:
    assert SELECT.stacks_to_build(["stacks/tested/dätä/übersicht.sql"], stacks) == ["tested"]


def test_no_expression_inside_a_run_block() -> None:
    offending = [
        f"{job}/{step.get('name', '?')}: {line.strip()}"
        for job, body in _workflow()["jobs"].items()
        for step in body["steps"]
        for line in str(step.get("run", "")).splitlines()
        if "${{" in line
    ]
    assert not offending, "expressions belong in `env:`, not in `run:`:\n" + "\n".join(offending)


def _stacks_with_dockerfile() -> list[str]:
    return sorted(p.parent.name for p in STACKS_DIR.glob("*/Dockerfile"))


@pytest.mark.parametrize("name", _stacks_with_dockerfile())
def test_compose_builds_the_image_the_way_the_check_does(name: str) -> None:
    """The check runs `docker build stacks/<name>`: folder as context, `Dockerfile`, no args.

    A stack whose compose file builds differently would pass here on an
    image nobody deploys.
    """
    compose = yaml.safe_load((STACKS_DIR / name / "docker-compose.yml").read_text())
    builds = [s["build"] for s in compose["services"].values() if "build" in s]
    assert builds, f"stacks/{name} has a Dockerfile that no compose service builds"
    for build in builds:
        if isinstance(build, str):
            assert build == ".", f"stacks/{name}: build context {build!r}"
            continue
        assert build.get("context", ".") == ".", f"stacks/{name}: build context {build!r}"
        assert build.get("dockerfile", "Dockerfile") == "Dockerfile", f"stacks/{name}: {build!r}"
        extra = set(build) - {"context", "dockerfile"}
        assert not extra, f"stacks/{name}: the check does not pass these build options: {extra}"


# ---- the image tests -----------------------------------------------------------------


def _proven_with_dockerfile() -> list[str]:
    return [n for n in _stacks_with_dockerfile() if SERVICES.get(n, {}).get("tier") == "proven"]


def test_some_proven_stack_builds_an_image() -> None:
    assert _proven_with_dockerfile(), "the parametrised test below would check nothing"


@pytest.mark.parametrize("name", _proven_with_dockerfile())
def test_a_proven_stack_that_builds_an_image_ships_a_test_for_it(name: str) -> None:
    test = STACKS_DIR / name / "image-test.sh"
    assert test.is_file(), (
        f"stacks/{name} is proven and builds its own image, but has no image-test.sh. "
        f"Without one the pull-request check only proves that the image builds."
    )
    assert os.access(test, os.X_OK), f"{test.relative_to(REPO_ROOT)} is not executable"
    assert "set -euo pipefail" in test.read_text(), (
        f"{test.relative_to(REPO_ROOT)} must stop at the first failing command"
    )

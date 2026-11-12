"""The release gate for the proven stacks (#712, phase 2).

`release-gate.yml` runs spin-up -> create -> teardown -> spin-up -> verify ->
teardown. Pinned here: the workflow's shape (the final teardown always runs,
both spin-ups use one token, every call hands over the lock), the teardown
being callable, the probe runner against a stand-in ssh, and that every
proven stack ships a probe.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RUNNER = REPO_ROOT / ".github" / "scripts" / "run-lifecycle-probes.sh"
SERVICES = yaml.safe_load((REPO_ROOT / "services.yaml").read_text())["services"]
PROVEN = sorted(n for n, e in SERVICES.items() if e.get("tier") == "proven")


def _workflow(name: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((WORKFLOWS / name).read_text())
    assert isinstance(loaded, dict)
    return loaded


# ---- the probes ------------------------------------------------------------------


def test_there_are_proven_stacks() -> None:
    assert PROVEN, "the parametrised tests below would check nothing"


@pytest.mark.parametrize("name", PROVEN)
def test_every_proven_stack_ships_a_lifecycle_probe(name: str) -> None:
    probe = REPO_ROOT / "stacks" / name / "lifecycle-probe.sh"
    assert probe.is_file(), (
        f"stacks/{name} is proven but has no lifecycle-probe.sh; the release gate "
        f"would fail on it. Write one with `create` and `verify`."
    )
    assert os.access(probe, os.X_OK), f"{probe.relative_to(REPO_ROOT)} is not executable"
    text = probe.read_text()
    assert "set -euo pipefail" in text
    for action in ("create", "verify"):
        assert action in text, f"{probe.relative_to(REPO_ROOT)} does not handle `{action}`"
    assert "unknown action" in text, "an unknown action must fail, not fall through to one"


# ---- the workflow ----------------------------------------------------------------


def test_the_gate_runs_the_cycle_in_order() -> None:
    jobs = _workflow("release-gate.yml")["jobs"]
    assert jobs["spin-up-create"]["needs"] == "check"
    assert jobs["teardown-between"]["needs"] == "spin-up-create"
    assert jobs["spin-up-verify"]["needs"] == "teardown-between"
    assert jobs["spin-up-create"]["with"]["lifecycle_probe"] == "create"
    assert jobs["spin-up-verify"]["with"]["lifecycle_probe"] == "verify"
    assert (
        jobs["spin-up-create"]["with"]["lifecycle_token"]
        == jobs["spin-up-verify"]["with"]["lifecycle_token"]
    ), "verify must look for what create wrote"


def test_the_final_teardown_runs_whatever_failed_before() -> None:
    job = _workflow("release-gate.yml")["jobs"]["teardown-final"]
    assert "always()" in job["if"], "a failed probe would otherwise leave a server running"
    assert set(job["needs"]) == {"check", "spin-up-create", "teardown-between", "spin-up-verify"}
    assert job["uses"] == "./.github/workflows/teardown.yml"


def test_every_called_lifecycle_workflow_is_told_the_gate_holds_the_lock() -> None:
    gate = _workflow("release-gate.yml")
    assert gate["concurrency"]["group"] == "infrastructure"
    called = [j for j in gate["jobs"].values() if "uses" in j]
    assert len(called) == 4
    for job in called:
        assert job["with"]["caller_holds_infrastructure_lock"] is True, job


def test_the_gate_refuses_without_the_confirmation() -> None:
    gate = _workflow("release-gate.yml")
    run = gate["jobs"]["check"]["steps"][0]["run"]
    assert '"$CONFIRM" != "TEARDOWN"' in run
    assert "${{" not in run


# ---- the callable teardown ---------------------------------------------------------


def test_the_teardown_can_be_called_and_reads_inputs_either_way() -> None:
    text = (WORKFLOWS / "teardown.yml").read_text()
    assert "github.event.inputs" not in text, (
        "github.event.inputs is empty in a called workflow; use inputs.confirm"
    )
    on = _workflow("teardown.yml")[True]  # PyYAML reads the key `on` as True
    assert "confirm" in on["workflow_call"]["inputs"]
    assert "caller_holds_infrastructure_lock" in on["workflow_call"]["inputs"]


def test_the_spin_up_probe_step_fails_the_run_and_takes_its_inputs_from_env() -> None:
    steps = _workflow("spin-up.yml")["jobs"]["spin-up"]["steps"]
    step = next(s for s in steps if s.get("name") == "Lifecycle probe")
    assert step["if"] == "inputs.lifecycle_probe != ''"
    assert not step.get("continue-on-error"), "a failing probe is the gate failing"
    assert step["env"]["PROBE_ACTION"] == "${{ inputs.lifecycle_probe }}"
    assert "${{" not in step["run"]


# ---- the probe runner, against a stand-in ssh ----------------------------------------

_FAKE_SSH = """#!/usr/bin/env bash
# ssh -o BatchMode=yes nexus bash -s -- <action> <token>   (probe on stdin)
calls_file="$(dirname "$0")/calls"
echo $(( $(cat "$calls_file" 2>/dev/null || echo 0) + 1 )) > "$calls_file"
if [ -n "${DROP_FIRST:-}" ] && [ ! -f "$(dirname "$0")/dropped" ]; then
  touch "$(dirname "$0")/dropped"
  exit 255
fi
shift 4   # -o BatchMode=yes nexus bash ; leaves: -s -- action token
shift 2   # -s --
exec bash -s -- "$@"
"""


def _repo(tmp_path: Path, probes: dict[str, str], proven: list[str]) -> Path:
    repo = tmp_path / "repo"
    (repo / ".github" / "scripts").mkdir(parents=True)
    (repo / ".github" / "scripts" / "run-lifecycle-probes.sh").write_text(RUNNER.read_text())
    (repo / "services.yaml").write_text(
        yaml.safe_dump({"services": {n: {"tier": "proven"} for n in proven} | {"other": {}}})
    )
    for name, body in probes.items():
        (repo / "stacks" / name).mkdir(parents=True)
        (repo / "stacks" / name / "lifecycle-probe.sh").write_text(body)
    return repo


def _run(
    tmp_path: Path, repo: Path, action: str = "create", token: str = "gate-1-1", **env: str
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "ssh").write_text(_FAKE_SSH)
    (bin_dir / "ssh").chmod(0o755)
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "sleep").chmod(0o755)
    # `timeout <s> ssh ...`: GNU timeout is not on macOS; this one just runs
    # the command, and exits 124 when told to by the test.
    (bin_dir / "timeout").write_text(
        '#!/bin/sh\nshift\n[ -n "$FAKE_TIMEOUT" ] && exit 124\nexec "$@"\n'
    )
    (bin_dir / "timeout").chmod(0o755)
    return subprocess.run(
        ["bash", ".github/scripts/run-lifecycle-probes.sh"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PROBE_ACTION": action,
            "PROBE_TOKEN": token,
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )


_OK = 'echo "ran $1 with $2"\n'
_FAIL = 'echo "artefact gone"; exit 1\n'


def test_all_probes_passing_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a": _OK, "b": _OK}, ["a", "b"])
    result = _run(tmp_path, repo, "verify", "gate-7-1")
    assert result.returncode == 0, result.stdout
    assert "ran verify with gate-7-1" in result.stdout
    assert "all 2 proven stacks passed" in result.stdout


def test_one_failing_probe_fails_the_step_after_running_the_rest(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a": _FAIL, "b": _OK}, ["a", "b"])
    result = _run(tmp_path, repo)
    assert result.returncode == 1
    assert "a: create failed" in result.stdout
    assert "ran create" in result.stdout, "b still ran"
    assert "1 passed, 1 failed" in result.stdout


def test_a_proven_stack_without_a_probe_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a": _OK}, ["a", "b"])
    result = _run(tmp_path, repo)
    assert result.returncode == 1
    assert "b: no stacks/b/lifecycle-probe.sh" in result.stdout


def test_no_proven_stack_at_all_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {}, [])
    result = _run(tmp_path, repo)
    assert result.returncode == 1
    assert "names no proven stack" in result.stdout


@pytest.mark.parametrize(
    ("action", "token"), [("delete", "gate-1"), ("create", "x; rm -rf /"), ("create", "")]
)
def test_bad_action_or_token_is_refused(tmp_path: Path, action: str, token: str) -> None:
    repo = _repo(tmp_path, {"a": _OK}, ["a"])
    result = _run(tmp_path, repo, action, token)
    assert result.returncode == 2
    assert not (tmp_path / "bin" / "calls").exists(), "nothing reached the server"


def test_a_dropped_connection_is_retried_once(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a": _OK}, ["a"])
    result = _run(tmp_path, repo, DROP_FIRST="1")
    assert result.returncode == 0, result.stdout
    assert "retrying once" in result.stdout
    assert (tmp_path / "bin" / "calls").read_text().strip() == "2"


@pytest.mark.parametrize("name", PROVEN)
def test_a_docker_exec_fed_a_heredoc_keeps_stdin_open(name: str) -> None:
    """Without -i, docker exec does not pass stdin on: the heredoc is lost and
    `python3 -` runs nothing, which reads as a probe that passed."""
    probe = REPO_ROOT / "stacks" / name / "lifecycle-probe.sh"
    for line in probe.read_text().splitlines():
        if "docker exec" in line and "<<" in line:
            assert " -i " in line or " -i\t" in line, f"{probe.name}: {line.strip()}"


def test_a_probe_that_hangs_fails_instead_of_holding_the_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a": _OK}, ["a"])
    result = _run(tmp_path, repo, FAKE_TIMEOUT="1")
    assert result.returncode == 1
    assert "no answer within" in result.stdout
    assert "a: create failed (exit 124)" in result.stdout


def test_every_curl_in_a_probe_is_bounded() -> None:
    for name in PROVEN:
        probe = REPO_ROOT / "stacks" / name / "lifecycle-probe.sh"
        for line in probe.read_text().splitlines():
            if line.strip().startswith("#"):
                continue
            if "curl " in line and "docker exec" not in line:
                assert "--max-time" in line, f"{probe.name}: {line.strip()}"

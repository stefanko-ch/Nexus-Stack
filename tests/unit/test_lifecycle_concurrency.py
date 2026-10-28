"""Lifecycle workflows never overlap on the same server (#801).

Every workflow that changes the server queues in one concurrency group,
`infrastructure`. spin-up.yml is the awkward one: it is dispatched on its
own, and it is also called by initial-setup.yaml and spin-up-snapshot.yml,
which already hold that group. A called workflow joining its caller's group
deadlocks, so spin-up.yml picks its group from an input that only a call
carries. These tests pin both halves: a dispatch takes the lock, a call
that says its caller holds the lock does not, and every caller holds the
lock it says it holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SPIN_UP = "spin-up.yml"
LOCK_INPUT = "caller_holds_infrastructure_lock"

# Every workflow that creates, changes or destroys the server.
LIFECYCLE = [
    "initial-setup.yaml",
    "spin-up.yml",
    "spin-up-snapshot.yml",
    "teardown.yml",
    "teardown-snapshot.yml",
    "destroy-all.yml",
    "update-from-upstream.yml",
]


def _load(name: str) -> dict[Any, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    assert isinstance(data, dict)
    return data


def _triggers(wf: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = wf.get("on", wf.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _group_for(inputs: dict[str, Any], run_id: str = "42") -> str:
    """Evaluate spin-up.yml's group expression for the given inputs.

    The expression is `A && B || C`, which GitHub evaluates like Python's
    `and`/`or`. Asserting its exact text first keeps this evaluation tied to
    what the workflow really says.
    """
    group = _load(SPIN_UP)["concurrency"]["group"]
    assert group == (
        "${{ inputs." + LOCK_INPUT + " && format('spin-up-called-{0}', github.run_id)"
        " || 'infrastructure' }}"
    )
    return (inputs.get(LOCK_INPUT) and f"spin-up-called-{run_id}") or "infrastructure"


@pytest.mark.parametrize("name", [n for n in LIFECYCLE if n != SPIN_UP])
def test_lifecycle_workflows_share_the_infrastructure_group(name: str) -> None:
    concurrency = _load(name)["concurrency"]
    assert concurrency == {"group": "infrastructure", "cancel-in-progress": False}


def test_spin_up_never_cancels_a_run_in_progress() -> None:
    # A spin-up killed midway can leave OpenTofu state locked and stacks
    # half-deployed; queueing is the safe choice, as for the other six.
    assert _load(SPIN_UP)["concurrency"]["cancel-in-progress"] is False


def test_a_dispatched_spin_up_takes_the_lock() -> None:
    triggers = _triggers(_load(SPIN_UP))
    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    # Absent from the dispatch form, so a dispatch can never opt out.
    assert LOCK_INPUT not in dispatch_inputs
    assert _group_for({}) == "infrastructure"


def test_a_called_spin_up_does_not_join_its_callers_group() -> None:
    assert _group_for({LOCK_INPUT: True}) == "spin-up-called-42"


def test_a_caller_that_does_not_say_it_holds_the_lock_takes_it() -> None:
    # Fails closed: a new caller that forgets the input queues in
    # `infrastructure`, or deadlocks loudly if it holds the group itself,
    # instead of running unlocked beside a teardown.
    call_input = _triggers(_load(SPIN_UP))["workflow_call"]["inputs"][LOCK_INPUT]
    assert call_input["type"] == "boolean"
    assert call_input["default"] is False
    assert _group_for({LOCK_INPUT: call_input["default"]}) == "infrastructure"


def _callers() -> list[tuple[str, dict[str, Any]]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for job in (_load(path.name).get("jobs") or {}).values():
            if str(job.get("uses", "")).endswith(f"/{SPIN_UP}"):
                found.append((path.name, job))
    return found


def test_the_callers_are_the_ones_the_comment_names() -> None:
    assert sorted({name for name, _ in _callers()}) == [
        "initial-setup.yaml",
        "spin-up-snapshot.yml",
    ]


@pytest.mark.parametrize(("name", "job"), _callers(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_caller_holds_the_lock_it_relies_on(name: str, job: dict[str, Any]) -> None:
    assert _load(name)["concurrency"]["group"] == "infrastructure"
    # Without it the call would join the caller's own group: a deadlock.
    assert (job.get("with") or {}).get(LOCK_INPUT) is True


# A run waiting on the group has status `pending`, which is neither
# `queued` nor `in_progress`. Both places that ask "is a lifecycle run
# active?" must count it, or the dashboard re-enables Spin Up (and a second
# dispatch cancels the waiting run) and the scheduled-teardown worker reads
# the state from an older completed run.
_REPO = WORKFLOWS.parents[1]


@pytest.mark.parametrize(
    "path",
    ["control-plane/functions/api/status.js", "control-plane/worker/src/index.js"],
)
def test_active_run_checks_count_a_waiting_run(path: str) -> None:
    source = (_REPO / path).read_text()
    assert "r.status !== 'completed'" in source
    assert "r.status === 'queued'" not in source

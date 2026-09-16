"""An instance repository moves to a Nexus-Stack release by one dispatch (#879).

The operator tears the stack down, dispatches
`.github/workflows/update-from-upstream.yml`, and spins the stack up again.
The workflow in between refuses a stack that is not torn down, fast-forwards
main to the release tag, and runs Setup: Control Plane.

Three kinds of checks:

- `update-from-upstream.sh` against real git repositories in a temporary
  directory: an upstream with release tags, a bare `origin`, and a clone of
  it. Every outcome the script distinguishes is produced for real, and the
  test reads `origin` afterwards rather than trusting the script's words.
- `lifecycle-state.sh` against runs lists shaped like the GitHub API.
- Workflow rules: dispatch only, never a spin-up, never a forced push, and
  the state check runs before main is moved.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SCRIPT = REPO_ROOT / ".github" / "scripts" / "update-from-upstream.sh"
STATE_SCRIPT = REPO_ROOT / ".github" / "scripts" / "lifecycle-state.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "update-from-upstream.yml"


# ---------------------------------------------------------------------------
# update-from-upstream.sh, against real repositories
# ---------------------------------------------------------------------------


def _git_env(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }


class _Repos:
    """upstream (tags v1.0.0, v1.1.0), origin (bare), instance (clone of origin)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.env = _git_env(root)
        (root / ".gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
        self.upstream = root / "upstream"
        self.origin = root / "origin.git"
        self.instance = root / "instance"
        self.output = root / "github_output"

        self.git(root, "init", "-q", str(self.upstream))
        self.v100 = self.commit(self.upstream, "one")
        self.git(self.upstream, "tag", "-a", "v1.0.0", "-m", "release 1.0.0")
        self.v110 = self.commit(self.upstream, "two")
        self.git(self.upstream, "tag", "-a", "v1.1.0", "-m", "release 1.1.0")
        # Exists upstream, but is not shaped like a release tag.
        self.git(self.upstream, "tag", "not-a-release")

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, repo: Path, name: str) -> str:
        (repo / f"{name}.txt").write_text(name)
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-q", "-m", name)
        return self.git(repo, "rev-parse", "HEAD")

    def make_instance(self, at: str) -> None:
        """origin and instance share upstream's history up to `at`."""
        self.git(self.root, "init", "-q", "--bare", str(self.origin))
        self.git(self.upstream, "push", "-q", str(self.origin), f"{at}:refs/heads/main")
        self.git(self.root, "clone", "-q", str(self.origin), str(self.instance))

    def make_template_copy(self) -> None:
        """What "Use this template" produces: the files, in one new commit.

        The commit must differ from upstream's. Same tree, message, author
        and second would be the very same commit, and so shared history.
        """
        self.git(self.root, "init", "-q", "--bare", str(self.origin))
        self.git(self.root, "init", "-q", str(self.instance))
        (self.instance / "one.txt").write_text("one")
        self.git(self.instance, "add", ".")
        self.git(self.instance, "commit", "-q", "-m", "Initial commit")
        self.git(self.instance, "remote", "add", "origin", str(self.origin))
        self.git(self.instance, "push", "-q", "origin", "main")

    def origin_main(self) -> str:
        return self.git(self.origin, "rev-parse", "refs/heads/main")

    def run(self, tag: str, expected: str | None = None) -> subprocess.CompletedProcess[str]:
        """`expected` defaults to what the tag really resolves to upstream."""
        if expected is None:
            probe = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                cwd=self.upstream,
                env=self.env,
                capture_output=True,
                text=True,
            )
            expected = probe.stdout.strip() or "0" * 40
        self.output.write_text("")
        return subprocess.run(
            ["bash", str(UPDATE_SCRIPT), str(self.upstream), tag, expected],
            cwd=self.instance,
            env={**self.env, "GITHUB_OUTPUT": str(self.output)},
            capture_output=True,
            text=True,
        )

    def outputs(self) -> dict[str, str]:
        pairs = (line.split("=", 1) for line in self.output.read_text().splitlines())
        # Later lines win, as they do for GitHub's own parser.
        return dict(pairs)


@pytest.fixture
def repos(tmp_path: Path) -> _Repos:
    return _Repos(tmp_path)


def test_a_stack_one_release_behind_is_fast_forwarded(repos: _Repos) -> None:
    repos.make_instance(at=repos.v100)

    result = repos.run("v1.1.0")

    assert result.returncode == 0, result.stderr
    assert repos.origin_main() == repos.v110
    out = repos.outputs()
    assert out == {"from": repos.v100, "to": repos.v110, "moved": "true"}


def test_a_stack_at_the_release_is_left_alone(repos: _Repos) -> None:
    repos.make_instance(at=repos.v110)

    result = repos.run("v1.1.0")

    assert result.returncode == 0, result.stderr
    assert "Nothing to do" in result.stdout
    assert repos.origin_main() == repos.v110
    assert repos.outputs()["moved"] == "false"


def test_an_older_release_is_never_applied(repos: _Repos) -> None:
    """A downgrade is a no-op, not a reset: main already contains v1.0.0."""
    repos.make_instance(at=repos.v110)

    result = repos.run("v1.0.0")

    assert result.returncode == 0, result.stderr
    assert "already contains v1.0.0" in result.stdout
    assert repos.origin_main() == repos.v110
    assert repos.outputs()["moved"] == "false"


def test_own_commits_stop_the_update_and_are_listed(repos: _Repos) -> None:
    repos.make_instance(at=repos.v100)
    own = repos.commit(repos.instance, "local-change")
    repos.git(repos.instance, "push", "-q", "origin", "main")

    result = repos.run("v1.1.0")

    assert result.returncode == 1
    assert "cannot be fast-forwarded" in result.stderr
    assert "local-change" in result.stderr
    assert repos.origin_main() == own
    assert repos.outputs()["moved"] == "false"


def test_a_template_copy_is_refused_with_a_pointer_to_the_docs(repos: _Repos) -> None:
    repos.make_template_copy()
    before = repos.origin_main()

    result = repos.run("v1.1.0")

    assert result.returncode == 1
    assert "share no history" in result.stderr
    assert "Updating to a new" in result.stderr
    assert repos.origin_main() == before


def test_a_tag_that_moved_since_validation_is_not_pushed(repos: _Repos) -> None:
    """The caller validated v1.1.0 at one commit; the fetch finds another."""
    repos.make_instance(at=repos.v100)

    result = repos.run("v1.1.0", expected=repos.v100)

    assert result.returncode == 1
    assert "The tag moved during this run" in result.stderr
    assert repos.origin_main() == repos.v100
    assert repos.outputs()["moved"] == "false"


@pytest.mark.parametrize("expected", ["", "abc123", "v1.1.0"])
def test_an_expected_commit_that_is_not_a_full_sha_is_refused(repos: _Repos, expected: str) -> None:
    repos.make_instance(at=repos.v100)

    result = repos.run("v1.1.0", expected=expected)

    assert result.returncode == 1
    assert "not a full commit SHA" in result.stderr
    assert repos.origin_main() == repos.v100


def test_a_refused_push_leaves_main_and_says_so(repos: _Repos) -> None:
    """origin moved after the checkout: the plain push must be rejected."""
    repos.make_instance(at=repos.v100)
    other = repos.root / "other"
    repos.git(repos.root, "clone", "-q", str(repos.origin), str(other))
    moved = repos.commit(other, "concurrent")
    repos.git(other, "push", "-q", "origin", "main")

    result = repos.run("v1.1.0")

    assert result.returncode == 1
    assert "push was refused" in result.stderr
    assert repos.origin_main() == moved
    assert repos.outputs()["moved"] == "false"


@pytest.mark.parametrize("tag", ["1.1.0", "v1.1", "main", "v1.1.0;rm", "not-a-release", ""])
def test_anything_but_a_release_tag_is_refused_before_fetching(repos: _Repos, tag: str) -> None:
    repos.make_instance(at=repos.v100)

    result = repos.run(tag)

    assert result.returncode == 1
    assert "not a release tag" in result.stderr
    assert repos.origin_main() == repos.v100


def test_a_release_upstream_does_not_have_is_refused(repos: _Repos) -> None:
    repos.make_instance(at=repos.v100)

    result = repos.run("v9.9.9")

    assert result.returncode == 1
    assert "Could not fetch v9.9.9" in result.stderr
    assert repos.origin_main() == repos.v100


def test_the_script_never_forces() -> None:
    code = "\n".join(
        line for line in UPDATE_SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    pushes = re.findall(r"git push[^\n]*", code)
    assert pushes, "the script is expected to push"
    for push in pushes:
        assert "--force" not in push, push
        assert " -f" not in push, push
        assert '"+' not in push, push
    for rewrite in ("git merge ", "git rebase", "reset --hard"):
        assert rewrite not in code, rewrite


# ---------------------------------------------------------------------------
# lifecycle-state.sh
# ---------------------------------------------------------------------------


def _run(
    workflow: str, created: str, status: str = "completed", conclusion: str | None = "success"
) -> dict[str, Any]:
    return {
        "path": f".github/workflows/{workflow}",
        "created_at": created,
        "status": status,
        "conclusion": conclusion,
    }


def _state(runs: list[dict[str, Any]]) -> str:
    result = subprocess.run(
        ["bash", str(STATE_SCRIPT)],
        input=json.dumps({"workflow_runs": runs}),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], "unknown"),
        ([_run("python-tests.yml", "2026-09-16T10:00:00Z")], "unknown"),
        ([_run("spin-up.yml", "2026-09-16T10:00:00Z")], "deployed"),
        ([_run("initial-setup.yaml", "2026-09-16T10:00:00Z")], "deployed"),
        (
            [
                _run("spin-up.yml", "2026-09-16T10:00:00Z"),
                _run("teardown.yml", "2026-09-16T11:00:00Z"),
            ],
            "torn-down",
        ),
        (
            [
                _run("teardown-snapshot.yml", "2026-09-16T11:00:00Z"),
                _run("spin-up-snapshot.yml", "2026-09-16T10:00:00Z"),
            ],
            "torn-down",
        ),
        (
            [
                _run("teardown.yml", "2026-09-16T10:00:00Z"),
                _run("spin-up.yml", "2026-09-16T11:00:00Z"),
            ],
            "deployed",
        ),
        ([_run("destroy-all.yml", "2026-09-16T11:00:00Z")], "destroyed"),
        # A failed teardown may have left the server running.
        (
            [
                _run("spin-up.yml", "2026-09-16T10:00:00Z"),
                _run("teardown.yml", "2026-09-16T11:00:00Z", conclusion="failure"),
            ],
            "unknown",
        ),
        # A failed spin-up may or may not have built a server.
        (
            [
                _run("teardown.yml", "2026-09-16T10:00:00Z"),
                _run("spin-up.yml", "2026-09-16T11:00:00Z", conclusion="failure"),
            ],
            "unknown",
        ),
        (
            [
                _run("teardown.yml", "2026-09-16T11:00:00Z"),
                _run("spin-up.yml", "2026-09-16T10:00:00Z", status="in_progress", conclusion=None),
            ],
            "busy",
        ),
        # Same start second, different kinds: order unknowable, in both list orders.
        (
            [
                _run("spin-up.yml", "2026-09-16T11:00:00Z"),
                _run("teardown.yml", "2026-09-16T11:00:00Z"),
            ],
            "unknown",
        ),
        (
            [
                _run("teardown.yml", "2026-09-16T11:00:00Z"),
                _run("spin-up.yml", "2026-09-16T11:00:00Z"),
            ],
            "unknown",
        ),
        # Same second, same kind: still clear.
        (
            [
                _run("teardown.yml", "2026-09-16T11:00:00Z"),
                _run("teardown-snapshot.yml", "2026-09-16T11:00:00Z"),
            ],
            "torn-down",
        ),
        (
            [
                _run("teardown.yml", "2026-09-16T10:00:00Z"),
                _run(
                    "spin-up-snapshot.yml", "2026-09-16T11:00:00Z", status="queued", conclusion=None
                ),
            ],
            "busy",
        ),
    ],
)
def test_lifecycle_state(runs: list[dict[str, Any]], expected: str) -> None:
    assert _state(runs) == expected


# ---------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------


def _workflow() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(data, dict)
    return data


def _steps() -> list[dict[str, Any]]:
    steps = _workflow()["jobs"]["update"]["steps"]
    assert isinstance(steps, list)
    return steps


def _step(name: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(_steps()):
        if step.get("name") == name:
            return index, step
    raise AssertionError(f"no step named {name!r}")


def test_only_a_person_can_start_it() -> None:
    # PyYAML reads the bare key `on` as the boolean True.
    raw: dict[Any, Any] = _workflow()
    triggers = raw["on"] if "on" in raw else raw[True]
    assert set(triggers) == {"workflow_dispatch"}


def test_it_never_starts_a_spin_up_or_a_teardown() -> None:
    text = WORKFLOW.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    dispatched = set(re.findall(r"gh workflow run\s+(\S+)", code))
    dispatched |= set(re.findall(r"actions/workflows/([^/\s]+)/dispatches", code))
    assert dispatched == {"setup-control-plane.yaml"}


def test_the_state_is_checked_before_main_moves() -> None:
    check, step = _step("Require a torn-down stack")
    move, _ = _step("Fast-forward main")
    assert check < move
    # The step must stop for anything but a torn-down or destroyed stack.
    # Only the `case "$STATE"` block: the loop above has a case of its own.
    run = step["run"].split('case "$STATE" in', 1)[1]
    for state in ("deployed", "busy"):
        block = re.search(rf"\n\s+{state}\)(.*?);;", run, re.S)
        assert block, state
        assert "exit 1" in block.group(1), state
    fallback = re.search(r"\n\s+\*\)(.*?);;", run, re.S)
    assert fallback, "the unknown state needs its own branch"
    assert "exit 1" in fallback.group(1)


def test_the_state_check_reads_every_workflow_the_state_script_knows() -> None:
    _, step = _step("Require a torn-down stack")
    listed = set(re.findall(r"[a-z-]+\.ya?ml", step["run"]))
    known = set(re.findall(r'"([a-z-]+\.ya?ml)"', STATE_SCRIPT.read_text()))
    assert listed == known


def test_the_control_plane_is_updated_only_after_a_move_on_a_torn_down_stack() -> None:
    _, step = _step("Update the Control Plane")
    condition = step["if"]
    assert "steps.update.outputs.moved == 'true'" in condition
    assert "steps.state.outputs.state == 'torn-down'" in condition


def test_the_control_plane_run_is_the_one_this_dispatch_created() -> None:
    """The dispatch returns its run id; nothing is looked up by time.

    A lookup by start time can pick a run someone else dispatched just
    before, and report its result as this update's.
    """
    _, step = _step("Update the Control Plane")
    run = step["run"]
    assert "-F return_run_details=true" in run
    assert "RUN_ID=$(jq -r '.workflow_run_id // empty'" in run
    assert "gh run list" not in run
    # And the run is on the release commit.
    assert step["env"]["TARGET"] == "${{ steps.update.outputs.to }}"
    assert '[ "$RUN_SHA" != "$TARGET" ]' in run


def test_the_validated_release_commit_reaches_the_fast_forward() -> None:
    _, resolve = _step("Resolve the release")
    assert 'echo "sha=$SHA" >> "$GITHUB_OUTPUT"' in resolve["run"]
    assert "git/ref/tags/$TAG" in resolve["run"]
    _, update = _step("Fast-forward main")
    assert update["env"]["SHA"] == "${{ steps.resolve.outputs.sha }}"
    assert '"$TAG" "$SHA"' in update["run"]


def test_the_dispatched_setup_run_checks_its_commit_first() -> None:
    """The guard has to run inside the dispatched run, before any secret is
    read: the caller's head_sha check only notices after the fact."""
    _, update = _step("Update the Control Plane")
    assert '-f "inputs[expected_sha]=$TARGET"' in update["run"]

    setup = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "setup-control-plane.yaml").read_text()
    )
    triggers = setup["on"] if "on" in setup else setup[True]
    assert "expected_sha" in triggers["workflow_dispatch"]["inputs"]
    first = setup["jobs"]["deploy"]["steps"][0]
    assert first["if"] == "inputs.expected_sha != ''"
    assert first["env"] == {"EXPECTED": "${{ inputs.expected_sha }}", "ACTUAL": "${{ github.sha }}"}
    assert 'if [ "$EXPECTED" != "$ACTUAL" ]' in first["run"]
    assert "exit 1" in first["run"]


def test_a_missing_workflow_is_skipped_by_file_not_by_error_text() -> None:
    """Every API failure has to stop the run; only an absent file may skip."""
    _, step = _step("Require a torn-down stack")
    assert '[ -f ".github/workflows/$wf" ] || continue' in step["run"]
    assert "404" not in step["run"]


def test_checkouts_that_receive_the_update_token_are_pinned() -> None:
    for step in _steps():
        if "UPSTREAM_UPDATE_TOKEN" in str(step.get("with", {})):
            assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", step["uses"]), step["uses"]


def test_the_push_token_is_the_dedicated_secret() -> None:
    _, step = _step("Checkout main")
    assert step["with"]["token"] == "${{ secrets.UPSTREAM_UPDATE_TOKEN }}"
    assert step["with"]["fetch-depth"] == 0


def test_it_does_not_run_in_the_upstream_repository() -> None:
    condition = _workflow()["jobs"]["update"]["if"]
    assert "github.repository !=" in condition
    assert "stefanko-ch/Nexus-Stack" in condition

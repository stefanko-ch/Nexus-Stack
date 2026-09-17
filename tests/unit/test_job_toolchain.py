"""Lifecycle jobs install every tool they use beyond the job image (#884).

A Conductor tenant fork runs the lifecycle workflows on a Forgejo runner
whose job image is `node:22-bookworm`. Probed on 2026-09-17: it runs as
root and has curl, wget, git, ssh, ssh-keygen, python3, unzip, tar, node
and npm, but no sudo, jq, aws, gh, or pip. The first real run failed on
`sudo: command not found`; jq, the AWS CLI and PyYAML were next in line.

The rule: a lifecycle job may only use, beyond that baseline, what an
earlier step of the same job installed. Local composite actions and the
scripts a step calls are followed, so a tool used inside
`log-to-d1.sh` counts where that script runs.

`sudo` and `apt-get` are never allowed: the job image has no sudo, and
GitHub's runner is not root.

`gh` is used only by `scripts/repo-secret.sh`, on github.com; on a forge
the script uses curl. The workflow `update-from-upstream.yml` refuses to
run anywhere but GitHub and is therefore not a lifecycle job here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
LIFECYCLE = [
    "initial-setup.yaml",
    "setup-control-plane.yaml",
    "spin-up.yml",
    "teardown.yml",
    "destroy-all.yml",
    "spin-up-snapshot.yml",
    "teardown-snapshot.yml",
]

# Tools outside the job image's baseline, and what makes them available.
# "python-yaml" stands for `import yaml` under the job's python3.
WATCHED = ("jq", "aws", "cloudflared", "tofu", "uv", "uvx", "gh", "yq", "pip", "pip3")
FORBIDDEN = ("sudo", "apt-get", "apt")

# Uses that are fine without an install, with the reason.
EXEMPT = {
    ("scripts/repo-secret.sh", "gh"): "used only on github.com; a forge takes the curl branch",
}

INSTALLERS = {"install-tool.sh", "install-opentofu.sh"}

_SCRIPT_REF = re.compile(r"(?:\.github/scripts|(?<![\w/])scripts)/[\w.-]+\.(?:sh|py)")


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), path
    return data


def _code(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _commands(text: str, names: tuple[str, ...]) -> set[str]:
    code = _code(text)
    return {
        name
        for name in names
        if re.search(rf"(?<![\w./$-]){re.escape(name)}(?![\w./-])(?!=)", code)
    }


def _script_uses(rel: str) -> set[tuple[str, str]]:
    """(source, tool) pairs a referenced script needs."""
    path = REPO_ROOT / rel
    # The installers name the tools they install; that is not a use.
    if not path.is_file() or path.name in INSTALLERS:
        return set()
    text = path.read_text()
    found = {(rel, t) for t in _commands(text, WATCHED + FORBIDDEN)}
    if rel.endswith(".py") and re.search(r"^\s*import yaml", text, re.M):
        found.add((rel, "python-yaml"))
    if rel.endswith(".sh") and re.search(r"^\s*import yaml", text, re.M):
        found.add((rel, "python-yaml"))
    return found


def _provides(step: dict[str, Any]) -> set[str]:
    run = _code(str(step.get("run", "")))
    uses = str(step.get("uses", ""))
    out: set[str] = set()
    if "install-opentofu.sh" in run:
        out.add("tofu")
    for tool in re.findall(r"install-tool\.sh\"?[ \t]+(\w+)", run):
        out.add({"awscli": "aws"}.get(tool, tool))
    if uses.startswith("astral-sh/setup-uv"):
        out |= {"uv", "uvx"}
    if "uv sync" in run and ".venv/bin" in run and "GITHUB_PATH" in run:
        out.add("python-yaml")
    return out


# SSH to the server goes through Cloudflare Access: ~/.ssh/config names
# cloudflared as the ProxyCommand (nexus_deploy.setup.configure_ssh). So a
# step needs cloudflared when it runs `ssh … nexus`, or a nexus_deploy
# command that opens that connection.
_SSH_VIA_ACCESS = re.compile(
    r"(?<![\w./-])ssh(?![\w-])[^\n]*(?<![\w.@/-])nexus(?![\w.-])"
    r"|nexus_deploy\s+(run-pipeline|s3-snapshot)\b"
)


def _uses(step: dict[str, Any]) -> set[tuple[str, str]]:
    run = str(step.get("run", ""))
    found = {("step", t) for t in _commands(run, WATCHED + FORBIDDEN)}
    if _SSH_VIA_ACCESS.search(_code(run)):
        found.add(("ssh over Access", "cloudflared"))
    for rel in set(_SCRIPT_REF.findall(_code(run))):
        found |= _script_uses(rel)
    return found


def _expanded_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        uses = str(step.get("uses", ""))
        if uses.startswith("./"):
            base = REPO_ROOT / uses
            action = base / "action.yml" if (base / "action.yml").exists() else base / "action.yaml"
            out.extend(_expanded_steps((_load(action).get("runs") or {}).get("steps") or []))
        else:
            out.append(step)
    return out


def _jobs() -> list[tuple[str, str, list[dict[str, Any]]]]:
    jobs = []
    for name in LIFECYCLE:
        for job_name, job in (_load(WORKFLOWS / name).get("jobs") or {}).items():
            if "steps" in job:
                jobs.append((name, job_name, _expanded_steps(job["steps"])))
    return jobs


def _violations(steps: list[dict[str, Any]]) -> list[str]:
    available: set[str] = set()
    problems = []
    for index, step in enumerate(steps):
        available |= _provides(step)
        label = step.get("name") or step.get("uses") or f"step {index}"
        for source, tool in sorted(_uses(step)):
            if (source, tool) in EXEMPT:
                continue
            if tool in FORBIDDEN:
                problems.append(f"{label}: {tool} ({source}) is never available")
            elif tool not in available:
                problems.append(f"{label}: {tool} ({source}) used before it is installed")
    return problems


@pytest.mark.parametrize(
    ("workflow", "job", "steps"), _jobs(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_lifecycle_job_installs_what_it_uses(
    workflow: str, job: str, steps: list[dict[str, Any]]
) -> None:
    problems = _violations(steps)
    assert not problems, f"{workflow}:{job}\n  " + "\n  ".join(problems)


def test_the_rule_sees_the_tools_it_is_about() -> None:
    """Guards the guard: if the detection stopped matching, every job
    would pass on nothing."""
    seen: dict[str, set[str]] = {}
    for workflow, _job, steps in _jobs():
        for step in steps:
            seen.setdefault(workflow, set()).update(tool for _, tool in _uses(step))
    assert {"jq", "aws", "python-yaml", "tofu"} <= seen["setup-control-plane.yaml"]
    assert {"jq", "cloudflared", "python-yaml", "uv"} <= seen["spin-up.yml"]
    assert {"jq", "aws", "python-yaml"} <= seen["destroy-all.yml"]


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        ([{"run": "sudo mv x /usr/local/bin/"}], ["sudo"]),
        ([{"run": "echo '{}' | jq ."}], ["jq"]),
        ([{"run": "bash .github/scripts/install-tool.sh jq"}, {"run": "jq . f"}], []),
        ([{"run": "jq . f"}, {"run": "bash .github/scripts/install-tool.sh jq"}], ["jq"]),
        ([{"run": "python3 .github/scripts/generate-services-tfvars.py"}], ["python-yaml"]),
        ([{"run": ".github/scripts/log-to-d1.sh info x"}], ["jq"]),
        ([{"run": "bash .github/scripts/install-tool.sh awscli"}, {"run": "aws s3 ls"}], []),
        ([{"run": "echo 'use jq-style filters'  # jq in a comment"}], []),
        ([{"run": "uv run python -m nexus_deploy s3-snapshot"}], ["cloudflared"]),
        ([{"run": "ssh -o BatchMode=yes nexus true"}], ["cloudflared"]),
        (
            [
                {"uses": "astral-sh/setup-uv@v3"},
                {"run": "uv run python -m nexus_deploy snapshot-prune"},
            ],
            [],
        ),
        ([{"run": "ssh-keygen -t ed25519 -C nexus-stack"}], []),
        ([{"run": "ssh-keygen -f ~/.ssh/id -C github-actions@nexus-stack"}], []),
        ([{"run": 'ssh nexus "docker ps"'}], ["cloudflared"]),
    ],
)
def test_the_rule_itself(steps: list[dict[str, Any]], expected: list[str]) -> None:
    problems = _violations(steps)
    for tool in expected:
        assert any(f": {tool} (" in p for p in problems), (tool, problems)
    if not expected:
        assert not problems, problems


def test_the_ci_job_uses_the_runners_job_image() -> None:
    """job-image-toolchain.yaml proves the installs in the runner's image;
    that only holds while both name the same one."""
    config = yaml.safe_load(
        (REPO_ROOT / "stacks" / "forgejo-runner" / "runner-config.yml").read_text()
    )
    images = {label.split("docker://", 1)[1] for label in config["runner"]["labels"]}
    assert len(images) == 1, images
    ci = _load(WORKFLOWS / "job-image-toolchain.yaml")
    assert ci["jobs"]["toolchain"]["container"]["image"] == images.pop()


def test_the_ci_job_installs_what_the_lifecycle_jobs_install() -> None:
    installed = set()
    for _workflow, _job, steps in _jobs():
        for step in steps:
            installed |= _provides(step)
    ci_steps = _load(WORKFLOWS / "job-image-toolchain.yaml")["jobs"]["toolchain"]["steps"]
    ci_installed = set().union(*(_provides(s) for s in ci_steps))
    assert installed <= ci_installed, installed - ci_installed

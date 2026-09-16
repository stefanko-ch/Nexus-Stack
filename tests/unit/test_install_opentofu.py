"""OpenTofu is installed by a pinned script, not by a marketplace action.

WHY THIS EXISTS. A Conductor tenant fork could not deploy: its first
lifecycle run on a Forgejo runner stopped at `uses: opentofu/setup-opentofu@v2`
with `repository ... not found` (#872). Forgejo resolves a bare `uses:` against
DEFAULT_ACTIONS_URL, which the forgejo stack pins to data.forgejo.org, and
that mirror does not carry the action. Every workflow now runs
`.github/scripts/install-opentofu.sh` instead.

Two kinds of checks:

- Repository rules. No `uses:` of setup-opentofu; no call of the script with
  a version argument, so every workflow gets the one pinned version; and no job
  runs `tofu` -- directly or through a local composite action -- before
  installing it.
- The script's refusals, run under bash with `curl` and `uname` replaced. The
  success path cannot be faked: the checksum is pinned to the real release
  archive. It is exercised for real by tofu-checks.yaml, which runs the script
  on every pull request that touches it, and was run on Ubuntu 26.04 and in the
  Forgejo runner's node:22-bookworm image when the script was written.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "install-opentofu.sh"
_WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
_ACTIONS = sorted((REPO_ROOT / ".github" / "actions").rglob("action.y*ml"))

# A `tofu` subcommand on a line that is not a comment.
_TOFU_CALL = re.compile(
    r"(?m)^[^#\n]*\btofu\s+"
    r"(init|apply|plan|output|validate|fmt|destroy|state|import|workspace|refresh)\b"
)


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), path
    return data


def _all_steps() -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for wf in _WORKFLOWS:
        for job in (_load(wf).get("jobs") or {}).values():
            out.extend((wf, step) for step in job.get("steps") or [])
    for action in _ACTIONS:
        out.extend((action, step) for step in (_load(action).get("runs") or {}).get("steps") or [])
    return out


def _local_action_calls_tofu(uses: str) -> bool:
    if not uses.startswith("./"):
        return False
    base = REPO_ROOT / uses
    path = base / "action.yml" if (base / "action.yml").exists() else base / "action.yaml"
    steps = (_load(path).get("runs") or {}).get("steps") or []
    return any(_TOFU_CALL.search(str(s.get("run", ""))) for s in steps)


def _calls_tofu(step: dict[str, Any]) -> bool:
    return bool(_TOFU_CALL.search(str(step.get("run", "")))) or _local_action_calls_tofu(
        str(step.get("uses", ""))
    )


def _installs_tofu(step: dict[str, Any]) -> bool:
    return "install-opentofu.sh" in str(step.get("run", "")) or "nexus-bootstrap" in str(
        step.get("uses", "")
    )


def test_workflow_files_were_found() -> None:
    assert _WORKFLOWS
    assert _ACTIONS
    assert SCRIPT.is_file()


def test_nothing_uses_setup_opentofu() -> None:
    """Checked on parsed `uses:` values, so the comments that explain the
    change -- and name the action -- do not count."""
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {step['uses']}"
        for path, step in _all_steps()
        if "setup-opentofu" in str(step.get("uses", ""))
    ]
    assert not offenders, (
        f"opentofu/setup-opentofu cannot be resolved on a Forgejo runner (#872): {offenders}. "
        "Run `bash .github/scripts/install-opentofu.sh` instead."
    )


def test_the_script_is_always_called_without_a_version() -> None:
    """One pinned version everywhere. tofu-checks.yaml relies on it: a checker
    on a different version than the applier can pass what the applier
    rejects."""
    calls = [
        (path, line.strip())
        for path, step in _all_steps()
        for line in str(step.get("run", "")).splitlines()
        if "install-opentofu.sh" in line
    ]
    assert calls, "no workflow runs install-opentofu.sh"
    offenders = [
        f"{p.relative_to(REPO_ROOT)}: {line}"
        for p, line in calls
        if not re.fullmatch(
            r'bash "?(\$GITHUB_WORKSPACE/)?\.github/scripts/install-opentofu\.sh"?', line
        )
    ]
    assert not offenders, (
        f"install-opentofu.sh called with arguments or unexpected form: {offenders}"
    )


def test_no_job_runs_tofu_before_installing_it() -> None:
    """A step "runs tofu" if its script calls a tofu subcommand, or if it uses
    a local composite action that does (nexus-config-tfvars does, and leaves
    the install to its caller)."""
    problems = []
    for wf in _WORKFLOWS:
        for name, job in (_load(wf).get("jobs") or {}).items():
            steps = job.get("steps") or []
            first_call = next((i for i, s in enumerate(steps) if _calls_tofu(s)), None)
            if first_call is None:
                continue
            first_install = next((i for i, s in enumerate(steps) if _installs_tofu(s)), None)
            if first_install is None or first_install > first_call:
                problems.append(
                    f"{wf.name}:{name} (tofu at step {first_call}, install at {first_install})"
                )
    assert not problems, f"jobs that run tofu without installing it first: {problems}"


def test_the_rule_above_sees_the_jobs_it_is_meant_for() -> None:
    """Guards the guard: if the tofu pattern stopped matching, the ordering
    test would pass on zero jobs."""
    jobs = {
        wf.name
        for wf in _WORKFLOWS
        for job in (_load(wf).get("jobs") or {}).values()
        if any(_calls_tofu(s) for s in job.get("steps") or [])
    }
    assert {"spin-up.yml", "teardown.yml", "destroy-all.yml", "tofu-checks.yaml"} <= jobs


def _pinned_version() -> str:
    pinned = re.search(r'^PINNED_VERSION="([^"]+)"$', SCRIPT.read_text(), re.M)
    assert pinned, "PINNED_VERSION not found"
    return pinned.group(1)


def test_pinned_checksums_are_well_formed() -> None:
    text = SCRIPT.read_text()
    version = _pinned_version()
    for arch in ("amd64", "arm64"):
        assert re.search(rf'{re.escape(version)}/{arch}\) echo "[0-9a-f]{{64}}"', text), (
            f"no 64-hex checksum pinned for {version}/{arch}"
        )


def test_only_the_pinned_version_has_checksums() -> None:
    """A leftover line for an old version is dead code that reads like a
    supported choice; the header says to replace the lines, not add to them."""
    text = SCRIPT.read_text()
    versions = set(re.findall(r"^\s+([0-9][^/\s]*)/(?:amd64|arm64)\) echo", text, re.M))
    assert versions == {_pinned_version()}


# ---------------------------------------------------------------------------
# The script's refusals
# ---------------------------------------------------------------------------

_FAKE_CURL = """#!/usr/bin/env bash
# Writes a stand-in archive wherever -o points; logs the URL.
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) echo "$1" >> "$FAKE_LOG"; shift ;;
    *) shift ;;
  esac
done
printf 'not the real archive' > "$out"
"""

_FAKE_UNAME = """#!/usr/bin/env bash
case "$1" in
  -s) echo "$FAKE_UNAME_S" ;;
  -m) echo "$FAKE_UNAME_M" ;;
  *) echo "$FAKE_UNAME_S" ;;
esac
"""

# A real sha256, so the mismatch below is computed rather than faked; macOS
# has no `sha256sum`, CI does, and both must reach the same comparison.
_SHA256SUM = f"""#!{sys.executable}
import hashlib, sys
for path in sys.argv[1:]:
    print(hashlib.sha256(open(path, "rb").read()).hexdigest() + "  " + path)
"""


def _run_script(
    tmp_path: Path, *args: str, uname_s: str = "Linux", uname_m: str = "x86_64"
) -> tuple[int, str, str, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("curl", _FAKE_CURL), ("uname", _FAKE_UNAME), ("sha256sum", _SHA256SUM)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    gh_path = tmp_path / "github_path"
    gh_path.write_text("")
    log = tmp_path / "curl.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_UNAME_S": uname_s,
        "FAKE_UNAME_M": uname_m,
        "GITHUB_PATH": str(gh_path),
        "RUNNER_TEMP": str(tmp_path / "runner-temp"),
    }
    done = subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False
    )
    urls = log.read_text().splitlines() if log.exists() else []
    return done.returncode, done.stderr, gh_path.read_text(), urls


def test_script_refuses_a_version_argument(tmp_path: Path) -> None:
    rc, err, gh_path, urls = _run_script(tmp_path, "1.9.0")
    assert rc == 1
    assert "takes no arguments" in err
    assert gh_path == ""
    assert urls == []


@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_script_refuses_an_archive_that_does_not_match_the_pin(tmp_path: Path, arch: str) -> None:
    """The one refusal that protects anything: a replaced download must not
    be installed or put on PATH. Run for both pinned architectures, and the
    URL is checked, so the test is known to have reached the comparison."""
    rc, err, gh_path, urls = _run_script(tmp_path, uname_m=arch)
    expected_arch = {"x86_64": "amd64", "aarch64": "arm64"}[arch]
    assert rc == 1, err
    assert "Checksum mismatch" in err
    version = _pinned_version()
    assert urls == [
        "https://github.com/opentofu/opentofu/releases/download/"
        f"v{version}/tofu_{version}_linux_{expected_arch}.tar.gz"
    ]
    assert hashlib.sha256(b"not the real archive").hexdigest() in err
    assert gh_path == ""
    assert not (tmp_path / "runner-temp").exists()


def test_script_refuses_a_non_linux_runner(tmp_path: Path) -> None:
    rc, err, gh_path, urls = _run_script(tmp_path, uname_s="Darwin")
    assert rc == 1
    assert "Linux runners only" in err
    assert gh_path == ""
    assert urls == []


def test_script_refuses_an_unpinned_architecture(tmp_path: Path) -> None:
    rc, err, gh_path, urls = _run_script(tmp_path, uname_m="riscv64")
    assert rc == 1
    assert "riscv64" in err
    assert gh_path == ""
    assert urls == []

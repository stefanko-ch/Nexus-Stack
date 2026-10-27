"""Tests for .github/scripts/generate-services-tfvars.py.

The script had no tests, which is how #911 stayed open on a question
nobody had answered: what happens when D1 names a service the deployed
ref's ``services.yaml`` does not have. Measured answer, before the guard
these tests cover existed — exit 0, nothing on either stream, the name
simply absent from the output. The deploy then succeeds and the stack is
not there.

Run as a subprocess rather than imported: the filename has a hyphen, and
what matters here is the exit status, which is what the workflow step
reacts to.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "generate-services-tfvars.py"

# Two services are enough to exercise every branch: one core (always
# enabled, never named in D1) and one ordinary (enabled only when D1 says
# so). A fixture rather than the real services.yaml, so the assertions do
# not move when a stack is added.
FIXTURE = textwrap.dedent(
    """\
    services:
      forgejo:
        subdomain: "git"
        port: 3000
        public: false
        core: true
        description: "Git forge"
        image: "codeberg.org/forgejo/forgejo:14"
      grafana:
        subdomain: "grafana"
        port: 3001
        public: false
        description: "Dashboards"
        image: "grafana/grafana:12.3.0"
    """
)


def _run(
    tmp_path: Path, enabled: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the generator in `tmp_path` with ENABLED_SERVICES=`enabled`."""
    (tmp_path / "services.yaml").write_text(FIXTURE, encoding="utf-8")
    (tmp_path / "tofu" / "stack").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tofu" / "stack" / "config.tfvars").write_text("", encoding="utf-8")
    # Inherit the environment rather than replacing it: a hand-built env
    # drops whatever the platform needs (PATH, HOME, locale, the
    # interpreter's own vars) and turns an unrelated breakage into a
    # failure of this test.
    env = {**os.environ, "ENABLED_SERVICES": enabled, "FIREWALL_RULES": "", **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def _tfvars(tmp_path: Path) -> str:
    return (tmp_path / "tofu" / "stack" / "config.tfvars").read_text(encoding="utf-8")


def test_the_script_is_where_this_test_thinks_it_is() -> None:
    """Otherwise every assertion below is about a subprocess that failed
    to start, which looks much the same as a passing guard."""
    assert SCRIPT.is_file(), SCRIPT


def test_known_services_are_enabled(tmp_path: Path) -> None:
    result = _run(tmp_path, "grafana")
    assert result.returncode == 0, result.stderr
    out = _tfvars(tmp_path)
    assert "grafana = {\n    enabled     = true" in out
    # Core is enabled without being named in D1.
    assert "forgejo = {\n    enabled     = true" in out


def test_an_unnamed_non_core_service_is_disabled(tmp_path: Path) -> None:
    result = _run(tmp_path, "forgejo")
    assert result.returncode == 0, result.stderr
    assert "grafana = {\n    enabled     = false" in _tfvars(tmp_path)


def test_empty_enabled_set_enables_only_core(tmp_path: Path) -> None:
    """The no-D1-state path: core on, everything else off."""
    result = _run(tmp_path, "")
    assert result.returncode == 0, result.stderr
    out = _tfvars(tmp_path)
    assert "forgejo = {\n    enabled     = true" in out
    assert "grafana = {\n    enabled     = false" in out


def test_unknown_service_fails_loudly(tmp_path: Path) -> None:
    """#911. The silent drop is the defect; this is the guard."""
    result = _run(tmp_path, "grafana,only-on-a-branch")
    assert result.returncode == 1
    assert "only-on-a-branch" in result.stderr
    # The name of a real service is not what the operator needs to see.
    assert "grafana" not in result.stderr


def test_every_unknown_service_is_named(tmp_path: Path) -> None:
    """Naming one of three would send someone round the loop twice."""
    result = _run(tmp_path, "zeta-stack,grafana,alpha-stack")
    assert result.returncode == 1
    assert "alpha-stack" in result.stderr
    assert "zeta-stack" in result.stderr
    # Sorted, so the message does not reshuffle between runs.
    assert result.stderr.index("alpha-stack") < result.stderr.index("zeta-stack")


def test_the_message_says_what_to_do(tmp_path: Path) -> None:
    """A failure an operator cannot act on is a worse failure than the
    silent drop it replaced: that one at least did not stop a deploy."""
    stderr = _run(tmp_path, "only-on-a-branch").stderr
    # The two causes, and the one-click recovery.
    assert "not merged" in stderr
    assert "never deletes" in stderr
    assert "Control Plane" in stderr
    # The branch-deploy command lives in the docs, not here: the rule in
    # test_job_toolchain.py reads this script as text and cannot tell a
    # tool named in a message from one invoked, so inlining `gh …` made
    # four lifecycle jobs fail for a mention. The section is named instead.
    assert "docs/admin-guides/troubleshooting.md" in stderr


def test_nothing_is_written_when_the_guard_fires(tmp_path: Path) -> None:
    """The step runs before `tofu apply`, which reads this file. A
    half-written tfvars behind a non-zero exit would be a trap for
    anything that retries without clearing it."""
    result = _run(tmp_path, "only-on-a-branch")
    assert result.returncode == 1
    # Not just any exit 1: an unrelated early failure would also leave the
    # file untouched, and this test would pass without the guard firing.
    assert "only-on-a-branch" in result.stderr
    assert _tfvars(tmp_path) == ""


def test_the_guard_is_skippable_for_teardown(tmp_path: Path) -> None:
    """Teardown and destroy generate tfvars too, and the guard harms them.

    destroy-all.yml runs this generator and then removes a preserved
    Forgejo service token under `if: ${{ !cancelled() }}` — deliberately,
    so a *failed* destroy still cleans up. An abort here would therefore
    skip `tofu destroy` while that purge still ran, leaving infrastructure
    alive with its management credential revoked. The guard introduced
    that path; before it, the generator could not fail.
    """
    result = _run(tmp_path, "grafana,only-on-a-branch", {"ALLOW_UNKNOWN_ENABLED_SERVICES": "true"})

    assert result.returncode == 0, result.stderr
    # Still says so — skipping the abort is not skipping the diagnosis.
    assert "only-on-a-branch" in result.stderr
    assert "ALLOW_UNKNOWN_ENABLED_SERVICES" in result.stderr
    # And it wrote the file, which is what teardown needs.
    assert "grafana = {\n    enabled     = true" in _tfvars(tmp_path)


@pytest.mark.parametrize("value", ["false", "", "yes", "1", "TRUE "])
def test_only_an_exact_true_skips_the_guard(tmp_path: Path, value: str) -> None:
    """A typo in a workflow must not silently disable a safety check. Only
    the literal `true` counts (case-insensitively, whitespace-trimmed) —
    `TRUE ` passes because of the trim, `1` and `yes` do not."""
    result = _run(tmp_path, "only-on-a-branch", {"ALLOW_UNKNOWN_ENABLED_SERVICES": value})

    if value.strip().lower() == "true":
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode == 1, f"{value!r} disabled the guard"


def test_every_destroying_workflow_sets_the_flag(tmp_path: Path) -> None:
    """The rule, not the instance. A teardown workflow that runs this
    generator without the flag can abort before `tofu destroy` — and the
    cleanup steps behind it still run. A new teardown variant must not be
    able to reintroduce that quietly."""
    workflows = REPO_ROOT / ".github" / "workflows"
    offenders = []
    for path in sorted(workflows.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if "generate-services-tfvars" not in text or "tofu destroy" not in text:
            continue
        if "ALLOW_UNKNOWN_ENABLED_SERVICES=true" not in text:
            offenders.append(path.name)
    assert offenders == [], (
        f"these workflows destroy and generate tfvars but do not skip the guard: {offenders}"
    )
    # Guard against the check going vacuous if the generator is renamed.
    assert (REPO_ROOT / ".github" / "workflows" / "destroy-all.yml").exists()


def test_the_doc_section_the_message_points_at_exists(tmp_path: Path) -> None:
    """An error message that names a doc section is a claim, and a claim in
    an error message is read while something is already broken. The heading
    is matched verbatim, so renaming it fails here rather than sending
    someone to a page that no longer has it."""
    stderr = _run(tmp_path, "only-on-a-branch").stderr
    doc = REPO_ROOT / "docs" / "admin-guides" / "troubleshooting.md"
    assert doc.is_file(), doc

    # The quoted heading is pulled out of the message rather than repeated
    # here — repeating it would let the two drift and still pass.
    quoted = re.findall(r"'([^']+)'", stderr)
    assert quoted, f"no quoted heading in the message:\n{stderr}"
    # The last quoted run, so an apostrophe earlier in the prose cannot
    # make this test grade the wrong substring — which it did once.
    heading = " ".join(quoted[-1].split())
    headings = {
        " ".join(line[3:].split())
        for line in doc.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    }
    assert heading in headings, f"{heading!r} is not a heading in {doc.name}"


def test_the_doc_quotes_the_message_the_script_prints(tmp_path: Path) -> None:
    """The guide shows a sample of this failure, and a doc quoting an error
    string only helps if the code prints it verbatim — otherwise someone
    searching their log for the documented line finds nothing. Caught once
    already: removing an apostrophe from the message left the guide quoting
    a sentence that no longer exists."""
    doc = (REPO_ROOT / "docs" / "admin-guides" / "troubleshooting.md").read_text(encoding="utf-8")
    stderr = _run(tmp_path, "only-on-a-branch").stderr
    first_line = stderr.splitlines()[0]
    assert "only-on-a-branch" in first_line, first_line
    assert first_line in doc, (
        f"the guide does not quote the line the script prints:\n  script: {first_line}"
    )


@pytest.mark.parametrize("enabled", ["  grafana  ", "grafana,", ",grafana", "grafana,,"])
def test_whitespace_and_empty_entries_are_not_unknown_services(
    tmp_path: Path, enabled: str
) -> None:
    """The D1 list is assembled by string join; a trailing comma or a
    stray space must not read as a service nobody has."""
    result = _run(tmp_path, enabled)
    assert result.returncode == 0, result.stderr
    assert "grafana = {\n    enabled     = true" in _tfvars(tmp_path)

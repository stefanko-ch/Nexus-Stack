"""A silent spin-up mutes that run's mail, and nothing after it.

Before, the ``silent_mode`` input was written to the stack's D1 and never
reset. Nexus-Conductor dispatched every single-user operation silently, so
one deploy muted a student's stack for good, over the notification
toggles on its own Settings page. The input now applies to the one run;
a stack-wide mute stays available on purpose through
``toggle-silent-mode.yml``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SPIN_UP = WORKFLOWS / "spin-up.yml"

# Writing the D1 value `silent_mode = 'true'`, in any spelling of the SQL.
_PERSIST = re.compile(r"VALUES\s*\(\s*'silent_mode'\s*,\s*'true'", re.IGNORECASE)


def _email_step() -> dict[str, Any]:
    data = yaml.safe_load(SPIN_UP.read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Send stack online email via Resend":
                found: dict[str, Any] = step
                return found
    raise AssertionError("spin-up.yml has no 'Send stack online email via Resend' step")


def test_no_lifecycle_workflow_persists_silent_mode() -> None:
    offenders = [
        path.name
        for path in WORKFLOWS.glob("*.y*ml")
        if path.name != "toggle-silent-mode.yml" and _PERSIST.search(path.read_text())
    ]
    assert offenders == [], f"silent_mode written to D1 outside toggle-silent-mode.yml: {offenders}"


def test_email_step_honours_the_run_input() -> None:
    step = _email_step()
    assert step["env"]["RUN_SILENT"] == "${{ inputs.silent_mode }}"
    script = step["run"]
    check = script.index('if [ "$RUN_SILENT" = "true" ]; then')
    # Before anything that could send: the Resend branch, the D1 lookups.
    assert check < script.index('if [ -n "$RESEND_API_KEY" ]; then')
    assert "exit 0" in script[check : script.index("fi", check)]


def test_toggle_workflow_still_mutes_a_stack_on_purpose() -> None:
    assert _PERSIST.search((WORKFLOWS / "toggle-silent-mode.yml").read_text()) is None, (
        "toggle-silent-mode.yml writes the value from a variable, not a literal; "
        "if this starts matching, the persistence test's exemption is doing work"
    )
    assert "silent_mode" in (WORKFLOWS / "toggle-silent-mode.yml").read_text()

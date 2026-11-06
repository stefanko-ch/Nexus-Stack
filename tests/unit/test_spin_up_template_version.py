"""The spin-up refreshes the Control Plane's TEMPLATE_VERSION secret (#954).

Only setup-control-plane.yaml used to set it, so a Conductor upgrade
followed by spin-ups kept showing the version of the last deploy. These
tests run the real block from spin-up.yml against a fake `npx` that
records what wrangler was asked to do.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIN_UP = REPO_ROOT / ".github" / "workflows" / "spin-up.yml"


def _block() -> str:
    text = SPIN_UP.read_text()
    match = re.search(
        r'^( +)TEMPLATE_VERSION=""\n.*?(?=^\1echo "✅ Credentials stored")', text, re.M | re.S
    )
    assert match, "TEMPLATE_VERSION block not found in spin-up.yml"
    indent = match.group(1)
    return "\n".join(ln.removeprefix(indent) for ln in match.group(0).splitlines())


def _run(tmp_path: Path, *, version_file: str | None, delete_says: str = "") -> tuple[str, str]:
    log = tmp_path / "npx.log"
    fake = tmp_path / "bin" / "npx"
    fake.parent.mkdir()
    # Records argv and stdin. `secret delete` fails with the given text
    # unless it is empty, which stands for a successful delete.
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$* | $(cat)" >> {log}\n'
        'if [ "$3 $4" = "secret delete" ] && [ -n "$DELETE_SAYS" ]; then\n'
        '  echo "$DELETE_SAYS"; exit 1\n'
        "fi\n"
    )
    fake.chmod(0o755)
    if version_file is not None:
        (tmp_path / ".template-version").write_text(version_file)
    env = {
        **os.environ,
        "PATH": f"{fake.parent}:{os.environ['PATH']}",
        "PAGES_PROJECT": "proj",
        "DELETE_SAYS": delete_says,
    }
    result = subprocess.run(
        ["bash", "-c", _block()], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
    )
    return result.stdout, log.read_text() if log.exists() else ""


def test_sets_the_version_from_the_file(tmp_path: Path) -> None:
    out, calls = _run(tmp_path, version_file=" v0.88.1\n")
    assert (
        "wrangler@4.129.0 pages secret put TEMPLATE_VERSION --project-name proj | v0.88.1" in calls
    )
    assert "✅ TEMPLATE_VERSION stored (v0.88.1)" in out


def test_removes_a_stale_secret_when_there_is_no_file(tmp_path: Path) -> None:
    out, calls = _run(tmp_path, version_file=None)
    assert "pages secret delete TEMPLATE_VERSION --project-name proj" in calls
    assert "Removed stale TEMPLATE_VERSION secret" in out


@pytest.mark.parametrize(
    ("says", "expected"),
    [
        ("✘ [ERROR] Secret not found", "nothing to refresh"),
        ("✘ [ERROR] Authentication error", "Could not remove"),
    ],
)
def test_a_failed_delete_is_reported_by_what_wrangler_said(
    tmp_path: Path, says: str, expected: str
) -> None:
    out, _ = _run(tmp_path, version_file=None, delete_says=says)
    assert expected in out


def test_runs_before_the_control_plane_is_redeployed() -> None:
    """The secret only reaches the running Functions with the next deploy."""
    text = SPIN_UP.read_text()
    assert text.index('TEMPLATE_VERSION=""') < text.index(
        "- name: Redeploy Control Plane to activate secrets"
    )

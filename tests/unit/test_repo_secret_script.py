"""scripts/repo-secret.sh — repository secrets on GitHub (gh) or Forgejo (API).

Runs the real script with `gh` / `curl` replaced by shims on PATH that
record their argv and stdin, so both forge paths are exercised without a
network. Issue #728.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "repo-secret.sh"

SHIM = """#!/bin/bash
printf '%s\\n' "$@" > "$SHIM_DIR/{name}.args"
cat > "$SHIM_DIR/{name}.stdin"
{extra}
"""


def _shims(tmp_path: Path, *, http_code: str = "201") -> Path:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    (shim_dir / "gh").write_text(SHIM.format(name="gh", extra=""))
    (shim_dir / "curl").write_text(SHIM.format(name="curl", extra=f"printf '%s' {http_code}"))
    for name in ("gh", "curl"):
        (shim_dir / name).chmod(0o755)
    return shim_dir


def _run(
    tmp_path: Path,
    args: list[str],
    *,
    stdin: str = "",
    env: dict[str, str],
    http_code: str = "201",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    shim_dir = _shims(tmp_path, http_code=http_code)
    full_env = {
        "PATH": f"{shim_dir}:{os.environ['PATH']}",
        "SHIM_DIR": str(shim_dir),
        "GH_TOKEN": "tok-1",
        **env,
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )
    return proc, shim_dir


GITHUB = {"GITHUB_SERVER_URL": "https://github.com"}
FORGEJO = {
    "GITHUB_SERVER_URL": "https://forgejo.example",
    "GITHUB_API_URL": "https://forgejo.example/api/v1",
    "GITHUB_REPOSITORY": "nexus-conductor/nexus-alice",
}


def test_github_set_delegates_to_gh_with_the_value_on_stdin(tmp_path: Path) -> None:
    proc, shims = _run(tmp_path, ["set", "R2_ACCESS_KEY_ID"], stdin="key-value", env=GITHUB)
    assert proc.returncode == 0, proc.stderr
    assert (shims / "gh.args").read_text().split() == ["secret", "set", "R2_ACCESS_KEY_ID"]
    assert (shims / "gh.stdin").read_text() == "key-value"
    assert not (shims / "curl.args").exists()


def test_github_delete_delegates_to_gh(tmp_path: Path) -> None:
    proc, shims = _run(tmp_path, ["delete", "R2_DATA_ACCESS_KEY_ID"], env=GITHUB)
    assert proc.returncode == 0, proc.stderr
    assert (shims / "gh.args").read_text().split() == ["secret", "delete", "R2_DATA_ACCESS_KEY_ID"]


def test_forgejo_set_puts_json_data_to_the_actions_secrets_endpoint(tmp_path: Path) -> None:
    ssh_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n"
    proc, shims = _run(tmp_path, ["set", "SSH_PRIVATE_KEY"], stdin=ssh_key, env=FORGEJO)
    assert proc.returncode == 0, proc.stderr
    args = (shims / "curl.args").read_text().splitlines()
    assert args[-1] == (
        "https://forgejo.example/api/v1/repos/nexus-conductor/nexus-alice/actions/secrets/SSH_PRIVATE_KEY"
    )
    assert "PUT" in args
    assert "Authorization: token tok-1" in args
    assert "@-" in args, "the body must arrive on stdin, never in argv"
    assert json.loads((shims / "curl.stdin").read_text()) == {"data": ssh_key}
    assert not (shims / "gh.args").exists()


def test_forgejo_delete_issues_delete_on_the_same_path(tmp_path: Path) -> None:
    proc, shims = _run(
        tmp_path, ["delete", "R2_DATA_SECRET_ACCESS_KEY"], env=FORGEJO, http_code="204"
    )
    assert proc.returncode == 0, proc.stderr
    args = (shims / "curl.args").read_text().splitlines()
    assert "DELETE" in args
    assert args[-1].endswith("/actions/secrets/R2_DATA_SECRET_ACCESS_KEY")


def test_forgejo_non_2xx_fails_and_names_the_status(tmp_path: Path) -> None:
    proc, _ = _run(
        tmp_path, ["set", "R2_ACCESS_KEY_ID"], stdin="s3cret-value", env=FORGEJO, http_code="403"
    )
    assert proc.returncode == 1
    assert "HTTP 403" in proc.stderr
    assert "s3cret-value" not in proc.stderr


@pytest.mark.parametrize(
    ("args", "env", "fragment"),
    [
        (["set"], GITHUB, "usage"),
        (["set", "bad-name"], GITHUB, "invalid secret name"),
        (["rotate", "X"], GITHUB, "unknown action"),
        (["set", "X"], {**FORGEJO, "GITHUB_API_URL": ""}, "GITHUB_API_URL"),
    ],
)
def test_argument_and_environment_validation(
    tmp_path: Path, args: list[str], env: dict[str, str], fragment: str
) -> None:
    proc, _ = _run(tmp_path, args, stdin="v", env=env)
    assert proc.returncode != 0
    assert fragment in proc.stderr


def test_missing_token_is_rejected_before_any_call(tmp_path: Path) -> None:
    shims = _shims(tmp_path)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "set", "X"],
        input="v",
        capture_output=True,
        text=True,
        env={
            "PATH": f"{shims}:{os.environ['PATH']}",
            "SHIM_DIR": str(shims),
            "GH_TOKEN": "",
            **GITHUB,
        },
        check=False,
    )
    assert proc.returncode == 2
    assert "GH_TOKEN" in proc.stderr
    assert not (shims / "gh.args").exists()

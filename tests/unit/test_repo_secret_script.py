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
    assert "@-" in args, "the body must arrive on stdin, never in argv"
    assert "--config" in args, "the token must travel in a curl config file"
    assert not any("tok-1" in a for a in args), (
        "GH_TOKEN must never reach argv — process arguments are readable "
        "through /proc by any user on a shared runner, and this token can "
        "write every repository secret"
    )
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


# A curl shim that actually writes a body to curl's `-o` target, which the
# shared shim does not. Needed to exercise what the script prints from the
# forge's error response.
BODY_SHIM = """#!/bin/bash
# Drain stdin first. The script pipes `node ... | curl ...`, so a shim that
# exits without reading closes the pipe under node and it dies with EPIPE
# instead of the script reaching its error path. That is a race — a small
# payload often lands before the shim exits — which passed locally and
# failed in CI. The shared SHIM above drains for the same reason.
cat > /dev/null
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then printf '%s' "$RESPONSE_BODY" > "$a"; fi
  prev="$a"
done
printf '%s' "422"
"""


def _run_with_body(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    (shim_dir / "curl").write_text(BODY_SHIM)
    (shim_dir / "curl").chmod(0o755)
    return subprocess.run(
        ["bash", str(SCRIPT), "set", "SOME_SECRET"],
        input="s3cr3t-value",
        capture_output=True,
        text=True,
        env={
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "GH_TOKEN": "tok-1",
            "RESPONSE_BODY": body,
            **FORGEJO,
        },
        check=False,
    )


def test_error_response_body_is_never_printed(tmp_path: Path) -> None:
    """The PUT payload of this request IS a secret.

    setup-control-plane.yaml captures this script's stderr with
    `OUTPUT=$(... 2>&1)` and prints it as SAVE_ERROR into the workflow log,
    which for a public repository is world-readable. Whether a forge or a
    proxy in front of it echoes the rejected request back is not knowable
    from here.

    Truncating was tried first and is not sufficient, which is why this
    test asserts absence rather than a bound: every secret this workflow
    stores is short enough to survive any useful cap -- an ed25519 private
    key is 387 bytes, an R2 access key 32, its secret 64.
    """
    secret = "s3cr3t-value"
    proc = _run_with_body(tmp_path, f'{{"message":"rejected","request":{{"data":"{secret}"}}}}')

    assert proc.returncode == 1
    assert secret not in proc.stderr
    assert "rejected" not in proc.stderr


def test_error_path_names_the_status_and_the_endpoint(tmp_path: Path) -> None:
    """Dropping the body must not leave the operator without a diagnosis.

    The status code distinguishes the three cases that matter on Forgejo --
    404 wrong API path, 403 token lacks write:repository, 422 rejected
    payload -- and the endpoint carries the secret's name, never its value.
    """
    proc = _run_with_body(tmp_path, '{"message":"whatever"}')

    assert "HTTP 422" in proc.stderr
    assert "SOME_SECRET" in proc.stderr
    assert "/repos/nexus-conductor/nexus-alice/actions/secrets/SOME_SECRET" in proc.stderr


def test_error_path_is_identical_when_the_forge_sends_no_body(tmp_path: Path) -> None:
    """A forge answering with a status and nothing else produces the same
    two lines -- no dangling header, no branch that only runs sometimes."""
    proc = _run_with_body(tmp_path, "")

    assert "HTTP 422" in proc.stderr
    assert proc.stderr.count("repo-secret.sh:") == 2


@pytest.mark.parametrize(
    "api_url",
    [
        "https://forgejo.example/api/v1",
        "http://localhost:3000/api/v1",
        "http://127.0.0.1:3000/api/v1",
        "http://[::1]:3000/api/v1",
    ],
)
def test_https_and_loopback_urls_are_accepted(tmp_path: Path, api_url: str) -> None:
    """Loopback over http is allowed on purpose: there is no wire to listen
    on. Whether a Forgejo job container reaches its own forge at all is
    #679, and an http URL on the same host is one plausible answer."""
    proc, _ = _run(
        tmp_path, ["delete", "X"], env={**FORGEJO, "GITHUB_API_URL": api_url}, http_code="204"
    )
    assert proc.returncode == 0, proc.stderr


def test_remote_cleartext_url_is_refused_before_the_token_is_sent(tmp_path: Path) -> None:
    """GH_TOKEN can write every repository secret. Sending it unencrypted to
    a remote host is refused rather than attempted, and refused *before* any
    call — so the shim must never have run."""
    proc, shims = _run(
        tmp_path,
        ["set", "X"],
        stdin="v",
        env={**FORGEJO, "GITHUB_API_URL": "http://forgejo.example/api/v1"},
    )
    assert proc.returncode == 2
    assert "refusing to send GH_TOKEN in cleartext" in proc.stderr
    assert not (shims / "curl.args").exists()


def test_transport_failure_still_names_action_and_endpoint(tmp_path: Path) -> None:
    """A curl that dies before producing a status (DNS, connect, TLS) used to
    abort the script through `set -e`, leaving the operator curl's bare
    one-liner with no action, name or endpoint attached — for precisely the
    "forge unreachable" case this script exists to make legible."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    (shim_dir / "curl").write_text("#!/bin/bash\ncat > /dev/null\nexit 6\n")
    (shim_dir / "curl").chmod(0o755)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "delete", "R2_ACCESS_KEY_ID"],
        capture_output=True,
        text=True,
        env={"PATH": f"{shim_dir}:{os.environ['PATH']}", "GH_TOKEN": "tok-1", **FORGEJO},
        check=False,
    )
    assert proc.returncode == 1
    assert "failed before any HTTP status (exit 6)" in proc.stderr
    assert "/actions/secrets/R2_ACCESS_KEY_ID" in proc.stderr
    assert "may be unreachable" in proc.stderr

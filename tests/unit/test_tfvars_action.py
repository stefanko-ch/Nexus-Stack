"""Values reach config.tfvars as data, whatever characters they contain.

The nexus-config-tfvars action used to put GitHub expressions straight into an
unquoted heredoc (#772). An expression is substituted textually before bash
parses the line, so a value was source code: a Docker Hub token containing a
dollar sign was silently truncated, a backtick aborted the heredoc, and a
quote became shell syntax.

Two things are pinned here: no expression inside a `run:` block of that
action, and a value full of awkward characters arriving in OpenTofu byte for
byte. The second is checked twice: with a small reader for HCL string
literals, which runs everywhere, and with OpenTofu itself where it is
installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION = REPO_ROOT / ".github" / "actions" / "nexus-config-tfvars" / "action.yml"
SCRIPT = REPO_ROOT / ".github" / "scripts" / "tfvars-write.sh"

# Everything bash, a heredoc or HCL treats specially, in one value.
AWKWARD = 'dckr_pat_a$bc`whoami`"quoted"\\back$HOME${x}%{if y}$(id);&|<>!\tTAB'

BASE_ENV = {
    "SERVER_TYPE": "cx43",
    "SERVER_LOCATION": "hel1",
    "SERVER_IMAGE": "ubuntu-26.04",
    "DOMAIN": "example.com",
    "ADMIN_EMAIL": "admin@example.com",
    "USER_EMAIL": "user@example.com",
    "GUEST_EMAILS": "a@example.com,b@example.com",
    "SUBDOMAIN_SEPARATOR": ".",
    "GITHUB_OWNER": "alice",
    "GITHUB_REPO": "stack",
    "ENABLE_FORGEJO_SERVICE_TOKEN": "",
    "DOCKERHUB_USERNAME": "",
    "DOCKERHUB_TOKEN": "",
}


def write_stack(tmp_path: Path, **overrides: str) -> Path:
    target = tmp_path / "config.tfvars"
    env = {"PATH": os.environ["PATH"], **BASE_ENV, **overrides}
    subprocess.run(
        ["bash", str(SCRIPT), "stack", str(target)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def read_hcl_string(literal: str) -> str:
    """Undo HCL's quoted-string escapes, as OpenTofu does."""
    assert literal.startswith('"'), literal
    assert literal.endswith('"'), literal
    body = literal[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            out.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}[body[i + 1]])
            i += 2
        elif body.startswith("$${", i) or body.startswith("%%{", i):
            out.append(body[i] + "{")
            i += 3
        else:
            assert not body.startswith("${", i), "an unescaped template sequence"
            assert not body.startswith("%{", i), "an unescaped template sequence"
            assert ch != '"', "an unescaped quote inside the literal"
            out.append(ch)
            i += 1
    return "".join(out)


def read_tfvars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^([a-z_][a-z0-9_]*)\s*=\s*(.*)$", line)
        if match and match.group(2).startswith('"'):
            values[match.group(1)] = read_hcl_string(match.group(2))
        elif match:
            values[match.group(1)] = match.group(2)
    return values


# ---- the action -----------------------------------------------------------------


def test_no_expression_inside_a_run_block_of_the_action() -> None:
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    offending = [
        f"{step.get('name', '?')}: {line.strip()}"
        for step in steps
        for line in str(step.get("run", "")).splitlines()
        if "${{" in line
    ]
    assert not offending, "expressions belong in `env:`, not in `run:`:\n" + "\n".join(offending)


def test_the_action_writes_the_stack_settings_through_the_script() -> None:
    text = ACTION.read_text()
    assert "tfvars-write.sh stack tofu/stack/config.tfvars" in text
    assert "<< EOF" not in text, "an unquoted heredoc expands whatever is written through it"


# ---- the values -----------------------------------------------------------------


@pytest.mark.parametrize(
    "variable",
    ["DOCKERHUB_TOKEN", "DOMAIN", "ADMIN_EMAIL", "GUEST_EMAILS", "SERVER_TYPE", "GITHUB_REPO"],
)
def test_an_awkward_value_round_trips_unchanged(tmp_path: Path, variable: str) -> None:
    overrides = {variable: AWKWARD}
    if variable == "DOCKERHUB_TOKEN":
        overrides["DOCKERHUB_USERNAME"] = "user"
    values = read_tfvars(write_stack(tmp_path, **overrides))
    key = {"ADMIN_EMAIL": "admin_email"}.get(variable, variable.lower())
    assert values[key] == AWKWARD


def test_the_three_values_the_issue_reported_arrive_whole(tmp_path: Path) -> None:
    for token in ("dckr_pat_a$bc", "p@ss`word", "AB$HOME/x"):
        values = read_tfvars(
            write_stack(tmp_path, DOCKERHUB_USERNAME="user", DOCKERHUB_TOKEN=token)
        )
        assert values["dockerhub_token"] == token


def test_a_value_shaped_like_shell_runs_nothing(tmp_path: Path) -> None:
    marker = tmp_path / "PWNED"
    payload = f'" = "" ]; touch {marker}; [ "'
    values = read_tfvars(
        write_stack(tmp_path, DOCKERHUB_USERNAME=payload, DOCKERHUB_TOKEN=f"$(touch {marker})")
    )
    assert not marker.exists()
    assert values["dockerhub_username"] == payload


def test_a_newline_in_a_value_cannot_add_a_line(tmp_path: Path) -> None:
    values = read_tfvars(write_stack(tmp_path, DOMAIN='example.com"\nadmin_email = "evil@x'))
    assert values["domain"] == 'example.com"\nadmin_email = "evil@x'
    assert values["admin_email"] == "admin@example.com"


def test_docker_hub_credentials_are_written_only_as_a_pair(tmp_path: Path) -> None:
    assert "dockerhub_token" not in read_tfvars(write_stack(tmp_path, DOCKERHUB_TOKEN="t"))
    assert "dockerhub_username" not in read_tfvars(write_stack(tmp_path, DOCKERHUB_USERNAME="u"))
    both = read_tfvars(write_stack(tmp_path, DOCKERHUB_USERNAME="u", DOCKERHUB_TOKEN="t"))
    assert (both["dockerhub_username"], both["dockerhub_token"]) == ("u", "t")


def test_the_forgejo_flag_is_a_bare_boolean(tmp_path: Path) -> None:
    on = read_tfvars(write_stack(tmp_path, ENABLE_FORGEJO_SERVICE_TOKEN="true"))
    assert on["enable_forgejo_service_token"] == "true"
    for other in ("", "false", "TRUE", "yes", 'true"'):
        off = read_tfvars(write_stack(tmp_path, ENABLE_FORGEJO_SERVICE_TOKEN=other))
        assert off["enable_forgejo_service_token"] == "false"


def test_the_server_type_line_keeps_the_shape_other_steps_read(tmp_path: Path) -> None:
    # teardown-snapshot.yml reads the type back with grep and sed.
    path = write_stack(tmp_path)
    line = next(ln for ln in path.read_text().splitlines() if ln.startswith("server_type"))
    assert re.fullmatch(r'server_type\s+= "cx43"', line), line


def test_set_appends_one_line_and_refuses_a_bad_key(tmp_path: Path) -> None:
    path = write_stack(tmp_path)
    subprocess.run(
        ["bash", str(SCRIPT), "set", str(path), "hetzner_s3_bucket", AWKWARD],
        check=True,
        capture_output=True,
    )
    assert read_tfvars(path)["hetzner_s3_bucket"] == AWKWARD
    before = path.read_text()
    refused = subprocess.run(
        ["bash", str(SCRIPT), "set", str(path), 'x"\nevil = "1', "v"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert path.read_text() == before


# ---- OpenTofu's own reading of the file --------------------------------------------


@pytest.mark.skipif(shutil.which("tofu") is None, reason="OpenTofu is not installed")
def test_opentofu_reads_the_awkward_value_back_unchanged(tmp_path: Path) -> None:
    module = tmp_path / "module"
    module.mkdir()
    tfvars = write_stack(module, DOCKERHUB_USERNAME="user", DOCKERHUB_TOKEN=AWKWARD, DOMAIN=AWKWARD)
    declared = sorted(k for k in read_tfvars(tfvars) if k != "enable_forgejo_service_token")
    (module / "main.tf").write_text(
        "".join(f'variable "{name}" {{\n  type = string\n}}\n' for name in declared)
        + 'variable "enable_forgejo_service_token" {\n  type = bool\n}\n'
        + 'output "token" {\n  value = var.dockerhub_token\n}\n'
        + 'output "domain" {\n  value = var.domain\n}\n'
    )
    env = {**os.environ, "TF_IN_AUTOMATION": "1"}
    for command in (
        ["tofu", "init", "-input=false", "-backend=false"],
        ["tofu", "apply", "-input=false", "-auto-approve", f"-var-file={tfvars.name}"],
    ):
        subprocess.run(command, cwd=module, env=env, check=True, capture_output=True, text=True)
    outputs = json.loads(
        subprocess.run(
            ["tofu", "output", "-json"],
            cwd=module,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert outputs["token"]["value"] == AWKWARD
    assert outputs["domain"]["value"] == AWKWARD

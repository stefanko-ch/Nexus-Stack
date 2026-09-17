"""install-tool.sh installs pinned jq, cloudflared and the AWS CLI (#884).

The refusals are run under bash with `curl` and `uname` replaced. The
success path cannot be faked, because the checksums are pinned to the real
release files. It runs for real in `.github/workflows/job-image-toolchain.yaml`,
inside the Forgejo runner's job image.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "install-tool.sh"
TOOLS = ("jq", "cloudflared", "awscli")

_FAKE_CURL = """#!/usr/bin/env bash
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) echo "$1" >> "$FAKE_LOG"; shift ;;
    *) shift ;;
  esac
done
printf 'not the real file' > "$out"
"""

_FAKE_UNAME = """#!/usr/bin/env bash
case "$1" in
  -s) echo "$FAKE_UNAME_S" ;;
  -m) echo "$FAKE_UNAME_M" ;;
  *) echo "$FAKE_UNAME_S" ;;
esac
"""

# A real sha256, so the mismatch is computed rather than faked; macOS has no
# `sha256sum`, CI does, and both must reach the same comparison.
_SHA256SUM = f"""#!{sys.executable}
import hashlib, sys
for path in sys.argv[1:]:
    print(hashlib.sha256(open(path, "rb").read()).hexdigest() + "  " + path)
"""


def _run(
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


def _pins() -> dict[tuple[str, str], tuple[str, str]]:
    """(tool, arch) -> (version, sha256), read from the script."""
    text = SCRIPT.read_text()
    out = {}
    for tool in TOOLS:
        block = re.search(rf"^  {tool}/amd64 \| {tool}/arm64\)(.*?)^    ;;", text, re.M | re.S)
        assert block, tool
        body = block.group(1)
        version = re.search(r'VERSION="([^"]+)"', body)
        assert version, tool
        for arch in ("amd64", "arm64"):
            sha = re.search(rf'{arch}\).*?SHA256="([0-9a-f]+)"', body, re.S)
            assert sha, (tool, arch)
            out[(tool, arch)] = (version.group(1), sha.group(1))
    return out


def test_every_tool_has_a_version_and_two_well_formed_checksums() -> None:
    pins = _pins()
    assert len(pins) == len(TOOLS) * 2
    for (tool, arch), (version, sha) in pins.items():
        assert re.fullmatch(r"[0-9]+(\.[0-9]+)+", version), (tool, version)
        assert re.fullmatch(r"[0-9a-f]{64}", sha), (tool, arch)
    # One checksum per file: amd64 and arm64 must differ.
    for tool in TOOLS:
        assert pins[(tool, "amd64")][1] != pins[(tool, "arm64")][1], tool


@pytest.mark.parametrize("args", [(), ("jq", "cloudflared"), ("yq",), ("../evil",)])
def test_the_script_refuses_anything_but_one_known_tool(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    rc, err, gh_path, urls = _run(tmp_path, *args)
    assert rc == 1
    assert "usage" in err or "Unknown tool" in err
    assert urls == []
    assert gh_path == ""


def test_the_script_refuses_a_non_linux_runner(tmp_path: Path) -> None:
    rc, err, gh_path, urls = _run(tmp_path, "jq", uname_s="Darwin")
    assert rc == 1
    assert "Linux runners only" in err
    assert (gh_path, urls) == ("", [])


def test_the_script_refuses_an_unpinned_architecture(tmp_path: Path) -> None:
    rc, err, gh_path, urls = _run(tmp_path, "jq", uname_m="riscv64")
    assert rc == 1
    assert "No jq build pinned" in err
    assert (gh_path, urls) == ("", [])


_EXPECTED_URLS = {
    ("jq", "amd64"): "https://github.com/jqlang/jq/releases/download/jq-{v}/jq-linux-amd64",
    ("jq", "arm64"): "https://github.com/jqlang/jq/releases/download/jq-{v}/jq-linux-arm64",
    (
        "cloudflared",
        "amd64",
    ): "https://github.com/cloudflare/cloudflared/releases/download/{v}/cloudflared-linux-amd64",
    (
        "cloudflared",
        "arm64",
    ): "https://github.com/cloudflare/cloudflared/releases/download/{v}/cloudflared-linux-arm64",
    ("awscli", "amd64"): "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-{v}.zip",
    ("awscli", "arm64"): "https://awscli.amazonaws.com/awscli-exe-linux-aarch64-{v}.zip",
}


@pytest.mark.parametrize(("tool", "arch"), sorted(_EXPECTED_URLS))
def test_a_file_that_does_not_match_its_pin_is_not_installed(
    tmp_path: Path, tool: str, arch: str
) -> None:
    """The refusal that protects anything. The URL is asserted, so the test
    is known to have reached the comparison for this tool and architecture."""
    version, sha = _pins()[(tool, arch)]
    uname_m = {"amd64": "x86_64", "arm64": "aarch64"}[arch]
    rc, err, gh_path, urls = _run(tmp_path, tool, uname_m=uname_m)
    assert rc == 1, err
    assert "Checksum mismatch" in err
    assert urls == [_EXPECTED_URLS[(tool, arch)].format(v=version)]
    assert sha in err
    assert hashlib.sha256(b"not the real file").hexdigest() in err
    assert gh_path == ""
    assert not list((tmp_path / "runner-temp").rglob("*")), "nothing may be installed"


def test_the_script_uses_no_sudo_and_no_early_reader() -> None:
    code = "\n".join(line.split("#", 1)[0] for line in SCRIPT.read_text().splitlines())
    assert not re.search(r"(?<![\w-])sudo(?![\w-])", code)
    assert not re.search(r"\|\s*(head\b|grep\b[^|]*\s-[a-zA-Z]*q)", code)


def test_every_install_call_names_a_known_tool() -> None:
    calls = []
    for path in [*(REPO_ROOT / ".github").rglob("*.yml"), *(REPO_ROOT / ".github").rglob("*.yaml")]:
        calls += re.findall(r"install-tool\.sh\"?[ \t]+(\S+)", path.read_text())
    assert calls, "no workflow calls install-tool.sh"
    assert set(calls) <= set(TOOLS), calls

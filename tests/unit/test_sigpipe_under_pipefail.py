"""No early-exiting reader on a pipe under pipefail (#883).

`set -o pipefail` reports a pipeline as failed when any stage fails. A
reader that stops early (`head`, `grep -q`) closes the pipe; if the
writer writes again after that, it dies of SIGPIPE, and the pipeline
fails with 141. Whether that happens depends on scheduling. So it
passes most of the time and fails at random, as `install-opentofu.sh`
did on the Conductor-Stack:

    INSTALLED=$("$DEST/tofu" version | head -n 1)   ->  exit 141, no message

The checks below run the real code against a writer that emits two
chunks with a pause in between, which makes the old form fail every
time instead of sometimes.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

import pytest

from nexus_deploy.compose_runner import render_remote_script
from nexus_deploy.forgejo import render_ready_preamble
from nexus_deploy.s3_persistence import S3Endpoint, render_restore_script, render_snapshot_script

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((REPO_ROOT / ".github" / "scripts").glob("*.sh"))

# A pipe into a reader that may stop before its input ends: head, or grep
# with -q/--quiet anywhere among its options (`grep -E -q`, `grep -qx`).
_EARLY_READER = re.compile(
    r"\|\s*(head\b|grep\b[^|;&]*?\s(-[a-zA-Z]*q[a-zA-Z]*|--quiet|--silent)\b)"
)


def _strip_comment(line: str) -> str:
    """Drop a shell comment: a `#` outside quotes that starts a word.
    A `#` inside quotes, or inside a word such as `${#x}` or `a#b`, is
    code, and what follows it must still be checked."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;|&("):
            return line[:i]
    return line


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Comment-stripped shell lines with continuations joined, so a pipe
    split across a trailing backslash, or continued on a line that starts
    with `|`, is one pipeline. Returns (first line number, joined text)."""
    out: list[tuple[int, str]] = []
    continued = False
    for n, raw in enumerate(text.splitlines(), 1):
        code = _strip_comment(raw).strip()
        joins = out and (continued or code.startswith("|"))
        continued = code.endswith("\\")
        code = code.removesuffix("\\").strip()
        if joins:
            out[-1] = (out[-1][0], f"{out[-1][1]} {code}")
        else:
            out.append((n, code))
    return out


# Two lines as two separate writes, the second after the reader has had
# time to exit.
_SLOW_TWO_LINES = 'printf "%s\\n" "$1"; sleep 0.3; printf "%s\\n" "$2"'


def _bash(snippet: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_the_mechanism_is_real() -> None:
    """The failure the fixes below avoid, reproduced."""
    result = _bash(
        "set -euo pipefail\n"
        f"w() {{ {_SLOW_TWO_LINES}; }}\n"
        'X=$(w one two | head -n 1)\necho "reached $X"\n'
    )
    assert result.returncode == 141
    assert "reached" not in result.stdout


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_do_not_pipe_into_an_early_reader(script: Path) -> None:
    """Every script here runs under pipefail or may one day; the rule is
    cheap to keep everywhere."""
    offenders = [
        f"{n}: {line}"
        for n, line in _logical_lines(script.read_text())
        if _EARLY_READER.search(line)
    ]
    assert not offenders, offenders


@pytest.mark.parametrize(
    ("snippet", "flagged"),
    [
        ("X=$(tofu version | head -n 1)", True),
        ('if echo "$R" | grep -q ok; then', True),
        ('if echo "$R" | grep -E -q "^ok"; then', True),
        ('if echo "$R" | grep --quiet ok; then', True),
        ('if echo "$R" | grep -qxF -- "$B"; then', True),
        ("long_command --flag \\\n  | grep -q ok", True),
        ("long_command --flag\n  | head -1", True),
        ('if grep -qxF -- "$B" <<< "$LIST"; then', False),
        ('echo "$R" | grep -E "^[-*]" >/dev/null', False),
        ('git log --oneline -20 "$A..$B" >&2', False),
        ("echo x | grep -c .  # head -1 in a comment", False),
        ('curl -H "X-Tag: #1" "$U" | head -n 1', True),
        ("printf '%s' '#x' | grep -q x", True),
        ('echo "${#ARR[@]}" | head -1', True),
        ("# echo x | head -1", False),
        ("x=1  # comment with 'an odd quote", False),
    ],
)
def test_the_early_reader_rule_itself(snippet: str, flagged: bool) -> None:
    lines = _logical_lines(snippet)
    assert any(_EARLY_READER.search(line) for _, line in lines) is flagged, lines


def test_install_opentofu_reads_the_version_without_a_pipe(tmp_path: Path) -> None:
    """The two lines that read the version, run against a `tofu` that
    writes its output in two chunks."""
    text = (REPO_ROOT / ".github" / "scripts" / "install-opentofu.sh").read_text()
    lines = [ln for ln in text.splitlines() if ln.startswith("INSTALLED=")]
    assert len(lines) == 2, lines

    tofu = tmp_path / "tofu"
    tofu.write_text(
        '#!/usr/bin/env bash\nprintf "OpenTofu v1.12.6\\n"; sleep 0.3; printf "on linux_amd64\\n"\n'
    )
    tofu.chmod(tofu.stat().st_mode | stat.S_IXUSR)

    snippet = (
        "set -euo pipefail\n" + f"DEST={tmp_path}\n" + "\n".join(lines) + '\necho "[$INSTALLED]"\n'
    )
    result = _bash(snippet)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[OpenTofu v1.12.6]"


def test_compose_runner_running_check_survives_a_chunked_listing() -> None:
    """A running container must count as started however `docker ps`
    splits its output."""
    script = render_remote_script(parents=[], leaves=["jupyter"])
    start = script.index("if RUNNING=$(docker ps")
    condition = (
        script[start : script.index("then", start)] + "then echo started; else echo failed; fi"
    )

    snippet = (
        "set -euo pipefail\n"
        f"docker() {{ set -- jupyter marimo; {_SLOW_TWO_LINES}; }}\n"
        "name=jupyter\n" + condition + "\n"
    )
    result = _bash(snippet)
    assert result.stdout.strip() == "started", (result.returncode, result.stderr)


def test_forgejo_ready_preamble_matches_without_a_pipe() -> None:
    preamble = render_ready_preamble(container="forgejo")
    gate = preamble[
        preamble.index("CONTAINER=") : preamble.index("\nfi\n", preamble.index("grep")) + 4
    ]
    assert "| grep" not in gate
    snippet = (
        "set -euo pipefail\n"
        f"docker() {{ set -- forgejo other; {_SLOW_TWO_LINES}; }}\n" + gate + "echo found\n"
    )
    result = _bash(snippet)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "found"


def _endpoint() -> S3Endpoint:
    return S3Endpoint(
        endpoint="https://example.r2.cloudflarestorage.com",
        region="auto",
        access_key="k",
        secret_key="s",
        bucket="nexus-test-persistence",
    )


def _restore_script() -> str:
    return render_restore_script(endpoint=_endpoint(), postgres_targets=(), rsync_targets=())


def test_restore_finds_latest_txt_in_a_long_listing() -> None:
    """A long snapshot listing, `latest.txt` first. With the old
    `printf | grep -q` form, printf could die of SIGPIPE and the restore
    would report "no snapshot" and start empty."""
    script = _restore_script()
    line = next(ln for ln in script.splitlines() if "latest.txt" in ln and "grep" in ln)
    assert "|" not in line, line

    snippet = (
        "set -euo pipefail\n"
        'SNAPSHOT_LISTING="latest.txt"$\'\\n\'"$(for i in $(seq 1 5000); do echo "2026-09-$i/"; done)"\n'
        + line
        + "\n  echo fresh-start\n  exit 0\nfi\necho found\n"
    )
    result = _bash(snippet)
    assert result.stdout.strip() == "found", (result.returncode, result.stderr)


def test_snapshot_drift_check_reads_all_of_its_input() -> None:
    """grep -q would stop at the first drift line and kill tee and rclone."""
    script = render_snapshot_script(
        endpoint=_endpoint(),
        stack_slug="nexus-test",
        template_version="v0.82.0",
        timestamp="20260917T120000Z",
        postgres_targets=(),
        rsync_targets=(),
    )
    check = script[script.index('rclone check "$src" "$dst"') :].split("\n", 1)[0]
    assert "grep -q" not in check, check
    assert check.endswith('| grep -E "^[-*]" >/dev/null'), check

    # And the drift is still detected: a clean exit status of the reader.
    # A drift line first, then far more output than one pipe buffer, so
    # the old `grep -q` would have closed the pipe while tee still wrote.
    result = _bash(
        "set -euo pipefail\n"
        "w() { echo '* drift/a'; for i in $(seq 1 20000); do echo \"= same/$i\"; done; }\n"
        'w | tee /dev/null | grep -E "^[-*]" >/dev/null; s=("${PIPESTATUS[@]}"); echo "${s[*]}"\n'
    )
    assert result.stdout.strip() == "0 0 0", result.stderr


@pytest.mark.parametrize(
    ("workflow", "fragment"),
    [
        ("spin-up.yml", "head -c 300 /tmp/smoke-ssh.err 2>/dev/null | tr"),
        ("destroy-all.yml", 'grep -qxF -- "$BUCKET" <<< "$EXISTING_BUCKETS"'),
    ],
)
def test_pipefail_steps_use_the_safe_form(workflow: str, fragment: str) -> None:
    text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text()
    assert fragment in text
    assert "| head -c 300" not in text or workflow != "spin-up.yml"
    assert '"$EXISTING_BUCKETS" | grep -q' not in text

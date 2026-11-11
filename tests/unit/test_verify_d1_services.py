"""The D1 sync's final check says what it found, and only what it found.

`.github/scripts/sync-deployed-state.sh` ended with "✅ Found 0 services in
D1" after a sync that had written every row (#943): it read a path the
document does not have, and `|| echo "0"` turned the jq failure into a count.
The check is now `.github/scripts/verify-d1-services.py`, with three answers:
all there, some missing, could not tell.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "verify-d1-services.py"
SYNC = REPO_ROOT / ".github" / "scripts" / "sync-deployed-state.sh"

SERVICES_YAML = "services:\n  forgejo: {}\n  grafana: {}\n  kestra: {}\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_d1_services", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_d1 = _load()


def wrangler(names: list[str]) -> str:
    """What `wrangler d1 execute --json` prints: one object per statement."""
    return json.dumps([{"results": [{"name": n} for n in names], "success": True, "meta": {}}])


def test_all_services_present_is_a_tick_with_both_counts() -> None:
    status, message = verify_d1.verify(wrangler(["forgejo", "grafana", "kestra"]), SERVICES_YAML)
    assert status == verify_d1.OK
    assert "All 3 services" in message
    assert "D1 holds 3 rows" in message


def test_extra_rows_in_d1_are_not_an_error() -> None:
    # The sync never deletes, so a service removed from services.yaml keeps its row.
    status, message = verify_d1.verify(
        wrangler(["forgejo", "grafana", "kestra", "retired-stack"]), SERVICES_YAML
    )
    assert status == verify_d1.OK
    assert "D1 holds 4 rows" in message


def test_a_missing_service_is_named_and_is_not_a_tick() -> None:
    status, message = verify_d1.verify(wrangler(["forgejo", "grafana"]), SERVICES_YAML)
    assert status == verify_d1.MISSING
    assert "missing 1 of 3" in message
    assert "kestra" in message
    assert "✅" not in message


def test_an_empty_table_is_a_shortfall_not_zero_found() -> None:
    status, message = verify_d1.verify(wrangler([]), SERVICES_YAML)
    assert status == verify_d1.MISSING
    assert "missing 3 of 3" in message


@pytest.mark.parametrize(
    "answer",
    [
        "",  # nothing printed
        "✘ [ERROR] A request to the Cloudflare API failed.",  # an error, not JSON
        '{"result": [{"name": "forgejo"}]}',  # the shape the old check assumed
        "[]",
        '[{"success": true}]',
        '[{"results": [{"id": 1}]}]',
        # A failed statement that still carries rows: they say nothing.
        '[{"results": [{"name": "forgejo"}, {"name": "grafana"}, {"name": "kestra"}], "success": false}]',
        '[{"results": [{"name": "forgejo"}, {"name": "grafana"}, {"name": "kestra"}]}]',
    ],
)
def test_an_answer_that_cannot_be_read_is_unknown_never_a_count(answer: str) -> None:
    status, message = verify_d1.verify(answer, SERVICES_YAML)
    assert status == verify_d1.UNREADABLE
    assert "NOT verified" in message
    assert "✅" not in message


def test_the_script_exits_with_the_status_and_says_why(tmp_path: Path) -> None:
    services = tmp_path / "services.yaml"
    services.write_text(SERVICES_YAML)

    def run(answer: str) -> subprocess.CompletedProcess[str]:
        document = tmp_path / "answer.json"
        document.write_text(answer)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(document), str(services)],
            capture_output=True,
            text=True,
            check=False,
        )

    ok = run(wrangler(["forgejo", "grafana", "kestra"]))
    assert ok.returncode == 0
    assert "All 3 services" in ok.stdout
    short = run(wrangler(["forgejo"]))
    assert short.returncode == 1
    assert "missing 2 of 3" in short.stderr
    unknown = run("not json")
    assert unknown.returncode == 2
    assert "NOT verified" in unknown.stderr


def test_a_missing_input_file_is_unknown_not_missing_services(tmp_path: Path) -> None:
    services = tmp_path / "services.yaml"
    services.write_text(SERVICES_YAML)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "no-such-answer.json"), str(services)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == verify_d1.UNREADABLE
    assert "NOT verified" in result.stderr


def test_the_sync_script_no_longer_turns_a_failed_read_into_a_count() -> None:
    text = SYNC.read_text(encoding="utf-8")
    assert "verify-d1-services.py" in text
    assert '|| echo "0"' not in text
    assert "Found $SERVICE_COUNT services" not in text
    # The success line is printed only in the branch for status 0.
    final = text[text.index("# Step 5: Final verification") :]
    assert final.count('echo "✅ D1 sync complete"') == 1
    assert final.index('echo "✅ D1 sync complete"') < final.index("  1)")


# ---- the script end to end, with a stand-in for wrangler ----------------------

FAKE_NPX = """#!/bin/sh
# npx wrangler@... d1 execute ...: succeed quietly, except for the final
# SELECT, which answers with the document the test prepared.
case "$*" in
  *"SELECT name FROM services"*)
    [ -n "${FAKE_VERIFY_STDERR:-}" ] && echo "$FAKE_VERIFY_STDERR" >&2
    cat "$FAKE_VERIFY_ANSWER"
    exit "${FAKE_VERIFY_EXIT:-0}"
    ;;
  *) exit 0 ;;
esac
"""


def run_sync(
    tmp_path: Path, answer: str, *, exit_status: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(FAKE_NPX)
    npx.chmod(0o755)
    work = tmp_path / "repo"
    (work / ".github" / "scripts").mkdir(parents=True)
    for name in ("sync-deployed-state.sh", "verify-d1-services.py"):
        (work / ".github" / "scripts" / name).write_text(
            (REPO_ROOT / ".github" / "scripts" / name).read_text()
        )
    (work / "services.yaml").write_text((REPO_ROOT / "services.yaml").read_text())
    document = tmp_path / "answer.json"
    document.write_text(answer)
    env = {
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
        "CLOUDFLARE_API_TOKEN": "not-a-real-token",
        "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
        "DOMAIN": "example.com",
        "FAKE_VERIFY_ANSWER": str(document),
        "FAKE_VERIFY_EXIT": str(exit_status),
        "FAKE_VERIFY_STDERR": stderr,
    }
    return subprocess.run(
        ["bash", ".github/scripts/sync-deployed-state.sh"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# The sync script uses GNU sed, as the runners have; macOS ships BSD sed.
needs_gnu_userland = pytest.mark.skipif(
    sys.platform != "linux", reason="sync-deployed-state.sh needs GNU sed"
)


def _all_service_names() -> list[str]:
    import yaml

    return sorted(yaml.safe_load((REPO_ROOT / "services.yaml").read_text())["services"])


@needs_gnu_userland
def test_sync_ends_with_the_tick_when_every_service_is_in_d1(tmp_path: Path) -> None:
    result = run_sync(tmp_path, wrangler(_all_service_names()))
    assert result.returncode == 0, result.stderr[-600:]
    assert "✅ D1 sync complete" in result.stdout
    assert "Found 0 services" not in result.stdout


@needs_gnu_userland
def test_sync_fails_without_the_tick_when_rows_are_missing(tmp_path: Path) -> None:
    result = run_sync(tmp_path, wrangler(_all_service_names()[:-3]))
    assert result.returncode == 1
    assert "missing 3 of" in result.stderr
    assert "✅ D1 sync complete" not in result.stdout


@needs_gnu_userland
def test_sync_does_not_claim_success_when_the_answer_cannot_be_read(tmp_path: Path) -> None:
    result = run_sync(tmp_path, '{"result": []}')
    assert result.returncode == 0, "the rows were written; only the check is unknown"
    assert "✅ D1 sync complete" not in result.stdout
    assert "result not verified" in result.stdout
    assert "NOT verified" in result.stderr


@needs_gnu_userland
def test_sync_does_not_claim_success_when_the_query_fails(tmp_path: Path) -> None:
    result = run_sync(tmp_path, "", exit_status=1, stderr="✘ [ERROR] Authentication error")
    assert result.returncode == 0
    assert "✅ D1 sync complete" not in result.stdout
    assert "result not verified" in result.stdout
    assert "wrangler exit 1" in result.stderr

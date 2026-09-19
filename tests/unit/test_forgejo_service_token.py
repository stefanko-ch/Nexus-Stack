"""forgejo-service-token.sh keeps the Access service token across a teardown (#892).

The script is run for real under bash, with `tofu` and `curl` replaced by
fakes whose behaviour the test sets through the environment. What is asserted
is what the script *did* — which subcommands ran, with which arguments — not
which strings it contains.

`jq` is the one real dependency: the filter that picks tokens by name is
exactly the part worth exercising. Locally its absence skips; in CI it fails
(see :func:`test_ci_actually_has_jq`), because a silent skip in CI would leave
the contract unchecked.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "forgejo-service-token.sh"

RESOURCE = "cloudflare_zero_trust_access_service_token.forgejo[0]"
ACCOUNT = "acc123"
DOMAIN = "nexus.example.com"
# What main.tf names it: "nexus-${replace(var.domain, ".", "-")}-forgejo-token".
TOKEN_NAME = "nexus-nexus-example-com-forgejo-token"

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")

_FAKE_TOFU = """#!/usr/bin/env bash
echo "tofu $*" >> "$FAKE_LOG"
if [ "$1" = "state" ] && [ "$2" = "list" ]; then
  if [ "${FAKE_STATE_LIST_RC:-0}" -ne 0 ]; then
    echo "Error: state locked" >&2
    exit "${FAKE_STATE_LIST_RC}"
  fi
  if [ -n "${FAKE_STATE:-}" ]; then
    printf '%s\\n' "$FAKE_STATE"
  fi
  exit 0
fi
if [ "$1" = "state" ] && [ "$2" = "rm" ]; then
  exit "${FAKE_STATE_RM_RC:-0}"
fi
if [ "$1" = "import" ]; then
  exit "${FAKE_IMPORT_RC:-0}"
fi
if [ "$1" = "plan" ]; then
  echo "  # ${RESOURCE:-resource} must be replaced"
  exit "${FAKE_PLAN_RC:-0}"
fi
exit 0
"""

_FAKE_CURL = """#!/usr/bin/env bash
out=""
method=GET
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -X) method="$2"; shift 2 ;;
    -H) shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
echo "curl $method $url" >> "$FAKE_LOG"
if [ "$method" = "DELETE" ]; then
  printf '%s' "${FAKE_DELETE_CODE:-200}"
  exit "${FAKE_CURL_RC:-0}"
fi
if [ -n "$out" ]; then
  printf '%s' "${FAKE_LIST_JSON:-}" > "$out"
fi
printf '%s' "${FAKE_LIST_CODE:-200}"
exit "${FAKE_CURL_RC:-0}"
"""


def _token_list(*names: str) -> str:
    """A Cloudflare service-token listing, one entry per name given."""
    return json.dumps(
        {
            "success": True,
            "result": [
                {"id": f"id-{index}", "name": name, "client_id": f"client-{index}"}
                for index, name in enumerate(names, start=1)
            ],
        }
    )


class Result:
    def __init__(self, done: subprocess.CompletedProcess[str], log: list[str]) -> None:
        self.rc = done.returncode
        self.out = done.stdout
        self.err = done.stderr
        self.log = log

    def ran(self, pattern: str) -> bool:
        return any(re.search(pattern, line) for line in self.log)


def _run(tmp_path: Path, action: str, **overrides: str) -> Result:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("tofu", _FAKE_TOFU), ("curl", _FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "DOMAIN": DOMAIN,
        "CLOUDFLARE_API_TOKEN": "cf-secret-token",
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
        **overrides,
    }
    done = subprocess.run(
        ["bash", str(SCRIPT), action],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    return Result(done, log.read_text().splitlines() if log.exists() else [])


# ---------------------------------------------------------------------------
# preserve — the half that runs before `tofu destroy`
# ---------------------------------------------------------------------------


def test_preserve_takes_the_token_out_of_the_state(tmp_path: Path) -> None:
    result = _run(tmp_path, "preserve", FAKE_STATE=f"hcloud_server.main\n{RESOURCE}")
    assert result.rc == 0, result.err
    assert result.ran(r"tofu state rm cloudflare_zero_trust_access_service_token\.forgejo")


def test_preserve_does_nothing_when_the_token_is_not_managed(tmp_path: Path) -> None:
    """The feature is opt-in, and a second teardown finds it already gone."""
    result = _run(tmp_path, "preserve", FAKE_STATE="hcloud_server.main")
    assert result.rc == 0, result.err
    assert not result.ran(r"state rm")


def test_preserve_fails_loudly_when_the_removal_fails(tmp_path: Path) -> None:
    """Continuing would hand the destroy a token an external system holds."""
    result = _run(tmp_path, "preserve", FAKE_STATE=RESOURCE, FAKE_STATE_RM_RC="1")
    assert result.rc == 1
    assert "could not remove" in result.err


def test_preserve_fails_when_the_state_cannot_be_read(tmp_path: Path) -> None:
    """An unreadable state must not read as "nothing to preserve"."""
    result = _run(tmp_path, "preserve", FAKE_STATE_LIST_RC="1")
    assert result.rc == 1
    assert "Could not read the OpenTofu state" in result.err
    assert not result.ran(r"state rm")


# ---------------------------------------------------------------------------
# adopt — the half that runs before `tofu apply`
# ---------------------------------------------------------------------------


def test_adopt_is_a_no_op_when_the_feature_is_off(tmp_path: Path) -> None:
    result = _run(tmp_path, "adopt", ENABLE_FORGEJO_SERVICE_TOKEN="")
    assert result.rc == 0, result.err
    assert result.log == [], "an off feature must not even query Cloudflare"


def test_adopt_leaves_an_already_managed_token_alone(tmp_path: Path) -> None:
    result = _run(tmp_path, "adopt", ENABLE_FORGEJO_SERVICE_TOKEN="true", FAKE_STATE=RESOURCE)
    assert result.rc == 0, result.err
    assert not result.ran(r"curl")
    assert not result.ran(r"tofu import")


@needs_jq
def test_adopt_imports_the_one_token_named_after_this_stack(tmp_path: Path) -> None:
    """The name is derived exactly as main.tf derives it, and a token
    belonging to another stack in the same account must not be touched."""
    listing = _token_list("nexus-other-example-com-forgejo-token", TOKEN_NAME)
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=listing,
    )
    assert result.rc == 0, result.err + result.out
    assert result.ran(rf"tofu import .*{re.escape(RESOURCE)} {ACCOUNT}/id-2$")
    assert "id-1" not in "\n".join(result.log[1:])


@needs_jq
def test_adopt_creates_a_new_token_when_none_was_preserved(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=_token_list("nexus-other-example-com-forgejo-token"),
    )
    assert result.rc == 0, result.err
    assert not result.ran(r"tofu import")
    assert "new one will be minted" in result.out


@needs_jq
def test_adopt_refuses_to_guess_between_two_tokens_of_the_same_name(tmp_path: Path) -> None:
    """Importing the wrong one hands the Access policy a credential the
    external system does not hold — the same silent failure, one level down."""
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=_token_list(TOKEN_NAME, TOKEN_NAME),
    )
    assert result.rc == 1
    assert "Refusing to guess" in result.err
    assert TOKEN_NAME in result.err
    assert not result.ran(r"tofu import")


@needs_jq
def test_adopt_fails_when_the_listing_is_refused(tmp_path: Path) -> None:
    """A 403 must not read as "no token exists" — that would mint a second."""
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_CODE="403",
        FAKE_LIST_JSON="{}",
    )
    assert result.rc == 1
    assert "HTTP 403" in result.err
    assert "Service Tokens" in result.err
    assert not result.ran(r"tofu import")


@needs_jq
def test_adopt_fails_when_cloudflare_reports_no_success(tmp_path: Path) -> None:
    """A 200 whose body says success: false would otherwise select nothing."""
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=json.dumps({"success": False, "errors": [{"code": 10000}]}),
    )
    assert result.rc == 1
    assert "did not report success" in result.err
    assert not result.ran(r"tofu import")


@needs_jq
def test_adopt_fails_when_the_import_fails(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=_token_list(TOKEN_NAME),
        FAKE_IMPORT_RC="1",
    )
    assert result.rc == 1
    assert "could not import" in result.err
    assert "silently invalidate" in result.err


@needs_jq
def test_adopt_refuses_when_applying_would_still_change_the_token(tmp_path: Path) -> None:
    """An import that succeeds but does not settle is the case worth
    catching: the credential would rotate anyway, and nothing would say so.
    `tofu plan -detailed-exitcode` answers 2 when changes remain."""
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=_token_list(TOKEN_NAME),
        FAKE_PLAN_RC="2",
    )
    assert result.rc == 1
    assert "would rotate the credential" in result.err
    assert result.ran(r"tofu plan .*-detailed-exitcode")


@needs_jq
def test_adopt_says_the_secret_cannot_be_read_again(tmp_path: Path) -> None:
    """Infisical shows the client id and no secret after this. Unexplained,
    that reads as a defect rather than as how Cloudflare works."""
    result = _run(
        tmp_path,
        "adopt",
        ENABLE_FORGEJO_SERVICE_TOKEN="true",
        FAKE_LIST_JSON=_token_list(TOKEN_NAME),
    )
    assert result.rc == 0, result.err
    assert "cannot be read again" in result.out
    assert "still valid" in result.out


# ---------------------------------------------------------------------------
# purge — destroy-all leaves nothing behind
# ---------------------------------------------------------------------------


@needs_jq
def test_purge_deletes_every_token_of_that_name(tmp_path: Path) -> None:
    result = _run(tmp_path, "purge", FAKE_LIST_JSON=_token_list(TOKEN_NAME, TOKEN_NAME))
    assert result.rc == 0, result.err
    deleted = [line for line in result.log if line.startswith("curl DELETE")]
    assert len(deleted) == 2, result.log
    assert all(f"/accounts/{ACCOUNT}/access/service_tokens/id-" in line for line in deleted)


@needs_jq
def test_purge_leaves_other_stacks_tokens_alone(tmp_path: Path) -> None:
    result = _run(tmp_path, "purge", FAKE_LIST_JSON=_token_list("nexus-other-com-forgejo-token"))
    assert result.rc == 0, result.err
    assert not result.ran(r"curl DELETE")


@needs_jq
def test_purge_fails_when_a_delete_is_refused(tmp_path: Path) -> None:
    """destroy-all promises nothing is left behind; a 500 breaks that."""
    result = _run(
        tmp_path,
        "purge",
        FAKE_LIST_JSON=_token_list(TOKEN_NAME),
        FAKE_DELETE_CODE="500",
    )
    assert result.rc == 1
    assert "HTTP 500" in result.err
    assert "still there" in result.err


@needs_jq
def test_purge_treats_an_already_deleted_token_as_done(tmp_path: Path) -> None:
    result = _run(tmp_path, "purge", FAKE_LIST_JSON=_token_list(TOKEN_NAME), FAKE_DELETE_CODE="404")
    assert result.rc == 0, result.err
    assert "already gone" in result.out


# ---------------------------------------------------------------------------
# The script itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["", "delete", "adopt extra"])
def test_the_script_refuses_an_unknown_action(tmp_path: Path, action: str) -> None:
    result = _run(tmp_path, action)
    assert result.rc == 1
    assert "usage" in result.err
    assert result.log == []


def test_the_script_never_prints_the_api_token_or_a_response_body() -> None:
    """The listing carries the client_id of every service token in the
    account, and the bearer token authenticates against all of them."""
    code = "\n".join(line.split("#", 1)[0] for line in SCRIPT.read_text().splitlines())
    for sink in ("echo", "printf", "cat"):
        assert not re.search(rf"{sink}[^\n]*\$\{{?CLOUDFLARE_API_TOKEN", code)
    assert not re.search(r"(cat|echo|printf)[^\n]*\$body", code)


def test_the_script_keeps_early_readers_off_pipes() -> None:
    """#883: a reader that exits first kills the writer under pipefail."""
    code = "\n".join(line.split("#", 1)[0] for line in SCRIPT.read_text().splitlines())
    assert not re.search(r"\|\s*(head\b|grep\b[^|]*\s-[a-zA-Z]*q)", code)


# ---------------------------------------------------------------------------
# The wiring. Order is the whole point: preserve must run before the destroy
# and adopt before the apply, or the step is decoration.
# ---------------------------------------------------------------------------

WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _positions(workflow: str, *patterns: str) -> list[int]:
    """Where each pattern first appears in a workflow, as a character offset.

    Regexes, not literals: the step calls the script through
    `"$GITHUB_WORKSPACE/.github/scripts/..."`, so a literal needle silently
    matched nothing — and a `find()` that returns -1 reads as "at the very
    start", which is an ordering assertion that can never fail. Hence the
    explicit assert.
    """
    text = (WORKFLOWS / workflow).read_text()
    found = []
    for pattern in patterns:
        match = re.search(pattern, text)
        assert match, f"{pattern!r} does not match anything in {workflow}"
        found.append(match.start())
    return found


def test_the_rebuild_teardown_preserves_the_token_before_it_destroys() -> None:
    preserve, destroy = _positions(
        "teardown.yml",
        r'forgejo-service-token\.sh"? preserve',
        r"tofu destroy -var-file=config\.tfvars -auto-approve",
    )
    assert preserve < destroy, "the destroy would take the token with it"


def test_the_spin_up_adopts_the_token_before_it_applies() -> None:
    adopt, apply_ = _positions(
        "spin-up.yml",
        r'forgejo-service-token\.sh"? adopt',
        r"tofu apply -var-file=config\.tfvars -auto-approve",
    )
    assert adopt < apply_, "the apply would mint a replacement token"


def test_the_spin_up_passes_what_the_adopt_step_reads() -> None:
    """A missing variable there is not a crash but a silent no-op: the step
    would decide the feature is off and let the apply mint a new token."""
    text = (WORKFLOWS / "spin-up.yml").read_text()
    step = text[text.index("Adopt a preserved Forgejo service token") :][:900]
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "DOMAIN",
        "ENABLE_FORGEJO_SERVICE_TOKEN",
    ):
        assert name in step, name


def test_destroy_all_removes_the_preserved_token() -> None:
    """Otherwise a stack that was torn down first keeps a live credential
    after a workflow whose subject is leaving nothing behind."""
    destroy, purge = _positions(
        "destroy-all.yml",
        r"Destroying Nexus Stack \(Server, Tunnel, Services\)",
        r'forgejo-service-token\.sh"? purge',
    )
    assert destroy < purge, "purge must run after the destroy that may remove it"


def test_the_snapshot_teardown_needs_no_preservation() -> None:
    """It destroys one target, so the token was never at risk there. If that
    ever widens to an untargeted destroy, this fails and the preserve step
    has to be added — silently losing the token is what #892 was."""
    text = (WORKFLOWS / "teardown-snapshot.yml").read_text()
    destroys = re.findall(r"^\s*(?:if ! )?tofu destroy[^\n]*", text, re.M)
    assert destroys, "teardown-snapshot no longer destroys anything"
    for line in destroys:
        assert "-target=" in line, line


def test_ci_actually_has_jq() -> None:
    """In CI a skip is indistinguishable from a pass, and the name matching
    above is the contract this file exists to pin."""
    if os.environ.get("CI") != "true":
        pytest.skip("only enforced in CI; locally jq is optional")
    assert shutil.which("jq") is not None, (
        "jq is missing in CI, so the token-selection tests would skip and the "
        "name matching would go unchecked. Restore the jq install step in "
        ".github/workflows/python-tests.yml."
    )

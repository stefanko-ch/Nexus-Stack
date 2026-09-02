"""Which folder wins when the same secret key appears twice.

`secret_sync` keeps the first occurrence of a key and discards the rest.
Nothing states which folder should be "first" — it falls out of the
`LC_ALL=C sort` at the top of the rendered script, and out of the root
folder being appended after that sorted list. Issue #756.

These tests exist because that is a side effect rather than a decision.
A change that dropped the sort, switched to a locale-aware one, or
reordered the root append would silently hand every deployment a
different value for a colliding key, with no runtime signal: a notebook
reads `API_KEY` and gets the wrong one. Pinning it makes the behaviour a
contract, so such a change fails here rather than in production.

The rendered script runs for real, with `curl` and `docker` replaced by
shims — the same approach as tests/unit/test_repo_secret_script.py. One
harness liberty: `compose_dir` is the hardcoded `/opt/docker-server/...`,
so the script's copy is rewritten to point at a tmpdir. That path is
orthogonal to precedence; everything the tests assert on runs unmodified.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from nexus_deploy.secret_sync import StackTarget, render_remote_script

# A curl that answers from fixture files instead of Infisical. The folder
# listing and the per-folder secret fetch differ by `secretPath` appearing
# in argv, which is how the two are told apart.
CURL_SHIM = """#!/bin/bash
path=""
for a in "$@"; do
  case "$a" in secretPath=*) path="${a#secretPath=}" ;; esac
done
if [ -n "$path" ]; then
  label="$path"
  if [ "$label" = "/" ]; then label="root"; else label="${label#/}"; fi
  cat "$FIXTURES/secrets_${label}.json" 2>/dev/null || echo '{"secrets":[]}'
else
  cat "$FIXTURES/folders.json"
fi
"""

DOCKER_SHIM = "#!/bin/bash\nexit 0\n"


def _run_sync(tmp_path: Path, folders: dict[str, dict[str, str]]) -> tuple[str, str]:
    """Run the real rendered script over a fake Infisical.

    `folders` maps folder label -> {key: value}; use "root" for the
    unnamed root folder. Returns (stdout+stderr, env-file contents).
    """
    target = StackTarget(name="jupyter")
    script = render_remote_script(
        target=target,
        project_id="proj-1",
        infisical_token="tok-1",
        infisical_env="prod",
    )

    stack_dir = tmp_path / "stack"
    stack_dir.mkdir()
    script = script.replace(target.compose_dir, str(stack_dir))

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    named = [f for f in folders if f != "root"]
    (fixtures / "folders.json").write_text(json.dumps({"folders": [{"name": n} for n in named]}))
    for label, pairs in folders.items():
        (fixtures / f"secrets_{label}.json").write_text(
            json.dumps({"secrets": [{"secretKey": k, "secretValue": v} for k, v in pairs.items()]})
        )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(CURL_SHIM)
    (bin_dir / "docker").write_text(DOCKER_SHIM)
    for name in ("curl", "docker"):
        (bin_dir / name).chmod(0o755)

    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FIXTURES": str(fixtures),
            "HOME": str(tmp_path),
        },
        check=False,
    )
    env_file = stack_dir / Path(target.env_file).name
    return proc.stdout + proc.stderr, env_file.read_text() if env_file.exists() else ""


def test_the_alphabetically_first_folder_wins(tmp_path: Path) -> None:
    """Precedence follows `LC_ALL=C sort` over folder names.

    `clickhouse` sorts before `postgres`, so its value survives. Nothing
    declares this; it is what the sort produces, which is exactly why it
    is asserted here.
    """
    out, env = _run_sync(
        tmp_path,
        {
            "postgres": {"SHARED_KEY": "from-postgres"},
            "clickhouse": {"SHARED_KEY": "from-clickhouse"},
        },
    )

    assert "from-clickhouse" in env
    assert "from-postgres" not in env
    assert "collisions=1" in out


def test_the_losing_folder_is_named_in_the_log(tmp_path: Path) -> None:
    """The discard is announced, and names both sides.

    This is the only signal an operator gets: after the deploy the stack
    simply holds one of the two values, with nothing at runtime marking
    which. The message has to carry the shadowed folder and the winner.
    """
    out, _ = _run_sync(
        tmp_path,
        {
            "postgres": {"SHARED_KEY": "from-postgres"},
            "clickhouse": {"SHARED_KEY": "from-clickhouse"},
        },
    )

    assert "Key collision" in out
    assert "SHARED_KEY" in out
    assert "postgres" in out
    assert "clickhouse" in out
    assert "first-wins" in out


def test_sorting_is_byte_order_not_locale(tmp_path: Path) -> None:
    """`LC_ALL=C` is not alphabetical: uppercase sorts before lowercase.

    A folder named `Analytics` beats `analytics` and beats every
    lowercase name, which is not what "alphabetically first" suggests to
    a reader. Pinned separately so a switch to a locale-aware sort fails
    loudly rather than quietly reversing this pair.
    """
    out, env = _run_sync(
        tmp_path,
        {
            "analytics": {"SHARED_KEY": "from-lowercase"},
            "Analytics": {"SHARED_KEY": "from-uppercase"},
        },
    )

    assert "from-uppercase" in env
    assert "from-lowercase" not in env
    assert "collisions=1" in out


def test_the_root_folder_loses_to_every_named_folder(tmp_path: Path) -> None:
    """Root is appended after the sorted list, so it is processed last.

    That makes it lose every collision regardless of name — a second
    ordering rule layered on the sort, and the one most likely to be
    overlooked when the loop is touched.
    """
    out, env = _run_sync(
        tmp_path,
        {
            "root": {"SHARED_KEY": "from-root"},
            "zzz": {"SHARED_KEY": "from-zzz"},
        },
    )

    assert "from-zzz" in env
    assert "from-root" not in env
    assert "collisions=1" in out


def test_distinct_keys_across_folders_are_all_kept(tmp_path: Path) -> None:
    """The guard rails: only equal keys collide.

    Without this a change that deduplicated too eagerly — by value, or
    per-folder-prefix — would still satisfy the tests above.
    """
    out, env = _run_sync(
        tmp_path,
        {
            "alpha": {"KEY_A": "value-a"},
            "beta": {"KEY_B": "value-b"},
        },
    )

    assert "value-a" in env
    assert "value-b" in env
    assert "collisions=0" in out


@pytest.mark.parametrize("label", ["clickhouse", "postgres"])
def test_a_key_present_in_only_one_folder_is_never_a_collision(tmp_path: Path, label: str) -> None:
    """A single occurrence is not shadowed, whichever folder holds it."""
    out, env = _run_sync(tmp_path, {label: {"ONLY_KEY": "only-value"}})

    assert "only-value" in env
    assert "collisions=0" in out

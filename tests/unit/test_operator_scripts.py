"""The break-glass scripts under `scripts/` read a config path that exists.

These run by hand, rarely, and usually while something is already broken —
which is the worst moment to discover that a path went stale. Three of them
still read `tofu/config.tfvars`, from before that root was split into
`tofu/stack/` and `tofu/control-plane/`. Nothing generates the old path, so
each silently fell back to a bare `nexus` prefix and then looked for
resources whose names nobody has.

Silently is the operative word: a fallback that produces a wrong name finds
no orphan, and finding no orphan is also what success looks like.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((REPO_ROOT / "scripts").glob("*.sh"))

# Where `domain = "..."` is actually written — see
# .github/actions/nexus-config-tfvars/action.yml.
_TFVARS = "tofu/stack/config.tfvars"


def test_scripts_were_found() -> None:
    """Otherwise the parametrised tests below pass by iterating nothing."""
    assert len(SCRIPTS) >= 5, [p.name for p in SCRIPTS]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_script_reads_the_pre_split_tfvars_path(script: Path) -> None:
    code = "\n".join(line.split("#", 1)[0] for line in script.read_text().splitlines())

    stale = re.findall(r"tofu/config\.tfvars", code)

    assert not stale, (
        f"{script.name} reads tofu/config.tfvars, which nothing generates since the "
        f"root was split. The domain lives in {_TFVARS}."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_script_points_a_tofu_dir_at_the_pre_split_root(script: Path) -> None:
    """The same defect in its other spelling.

    Two scripts built the path through a variable rather than writing it out,
    so a check for the literal string missed them — and one of those was found
    by this test rather than by reading, which is the argument for having it.

    The fallback is what makes it worth pinning: a script that cannot find the
    file does not fail, it carries on with a bare `nexus` prefix and looks for
    names that belong to nobody.
    """
    code = "\n".join(line.split("#", 1)[0] for line in script.read_text().splitlines())

    for match in re.finditer(r'TOFU_DIR="([^"]+)"', code):
        assert match.group(1).endswith("/tofu/stack"), (
            f"{script.name} sets TOFU_DIR to {match.group(1)!r}; `domain` lives in "
            f"{_TFVARS} since the tofu root was split"
        )

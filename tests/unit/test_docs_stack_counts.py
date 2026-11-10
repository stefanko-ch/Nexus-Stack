"""No guide states the size of the catalogue as "N+ stacks".

The catalogue grows with almost every release, and a number written into
running text is never updated with it: the user guide said "60+ Docker
services", the setup guide "40+ Docker stacks" and the concepts page "100+
stacks" on the same day the catalogue held more than 160.

The real number lives in two places that tests keep honest: the README's
`## Stacks (N)` heading (tests/unit/test_readme.py) and the generated block in
docs/stacks/overview.md (tests/unit/test_stack_catalogue.py). Everywhere else,
say it without a number or link to the catalogue.

Only the "N+" form is checked. A bare number is too often something else: a
fleet of 15 stacks under a snapshot cap, a typical setup of 5 to 15 services.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

ROUNDED_COUNT = re.compile(
    r"\b\d+\+\s+(?:Docker\s+|data\s+|open-source\s+|self-hosted\s+)?(?:stacks|services)\b",
    re.IGNORECASE,
)

# Not guides about this project's catalogue:
# - CHANGELOG.md records what past releases said.
# - docs/proposals/ are dated design documents.
# - docs/stacks/<name>.md describe the product itself, whose own feature
#   counts ("notifications via 90+ services") are the vendor's, not ours.
SKIPPED_FILES = {"CHANGELOG.md"}
SKIPPED_PREFIXES = ("docs/proposals/", "docs/stacks/")


def rounded_counts(text: str) -> list[str]:
    return [match.group(0) for match in ROUNDED_COUNT.finditer(text)]


def _checked_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return [
        name
        for name in listed
        if name and name not in SKIPPED_FILES and not name.startswith(SKIPPED_PREFIXES)
    ]


def test_no_rounded_catalogue_size_in_the_guides() -> None:
    hits = [
        f"{name}: {hit}"
        for name in _checked_files()
        for hit in rounded_counts((REPO_ROOT / name).read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "A guide states the catalogue's size as a rounded number, which goes stale "
        "with the next release. Say it without a number or link docs/stacks/overview.md:\n"
        + "\n".join(hits)
    )


def test_the_guides_are_actually_checked() -> None:
    """The premise: an empty or mis-filtered file list would pass anything."""
    checked = _checked_files()
    assert "docs/user-guides/stacks.md" in checked
    assert "docs/admin-guides/setup-guide.md" in checked
    assert "README.md" in checked
    assert "docs/stacks/uptime-kuma.md" not in checked


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ships with 60+ Docker services grouped", 1),
        ("sized for the 40+ Docker stacks scenario", 1),
        ("A project with 100+ stacks cannot", 1),
        ("roughly 15 stacks", 0),
        ("between 5 and 15 services", 0),
        ("a large catalogue of Docker services", 0),
        ("80+ tools for developers", 0),
    ],
)
def test_rounded_counts(text: str, expected: int) -> None:
    assert len(rounded_counts(text)) == expected

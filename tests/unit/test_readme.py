"""Checks on the stack section of the top-level README.

The README lists every stack as a badge under a ``## Stacks (N)`` heading and
nothing else: descriptions live in ``docs/stacks/README.md``. These tests read
the real ``README.md`` and the real ``stacks/`` directory, because the failure
they guard against is the two drifting apart. A release that added 47 stacks
left "80+ Docker services" standing 53 lines above a heading that said 163.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
STACKS_DIR = REPO_ROOT / "stacks"

HEADING = re.compile(r"^## Stacks \((\d+)\)$", re.MULTILINE)
# One stack badge: a shields.io static badge, linked to the stack's website.
BADGE = re.compile(r"^\[!\[([^\]]+)\]\(https://img\.shields\.io/badge/[^)]+\)\]\([^)]+\)$")
# "163 stacks", "80+ Docker services", "60 services" — a catalogue size written
# as a number in running text.
HARD_CODED_COUNT = re.compile(r"\b\d+\+?\s+(?:Docker\s+)?(?:stacks|services)\b", re.IGNORECASE)


def _stack_section() -> tuple[int, list[str], str]:
    """Return the heading's count, the section's lines, and the README without that section."""
    text = README.read_text(encoding="utf-8")
    match = HEADING.search(text)
    assert match, "README.md has no '## Stacks (N)' heading"
    rest = text[match.end() :]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    outside = text[: match.start()] + (rest[next_heading.start() :] if next_heading else "")
    return int(match.group(1)), section.splitlines(), outside


def _badge_names() -> list[str]:
    _, lines, _ = _stack_section()
    return [m.group(1) for line in lines if (m := BADGE.match(line))]


def _stack_dirs() -> list[str]:
    return sorted(p.name for p in STACKS_DIR.iterdir() if p.is_dir())


def test_heading_count_is_the_number_of_stack_directories() -> None:
    stated, _, _ = _stack_section()
    actual = len(_stack_dirs())
    assert stated == actual, (
        f"README.md says '## Stacks ({stated})' but stacks/ holds {actual} directories. "
        f"Update the number in the heading."
    )


def test_one_badge_per_stack_directory() -> None:
    badges = _badge_names()
    actual = len(_stack_dirs())
    assert len(badges) == actual, (
        f"README.md has {len(badges)} stack badges but stacks/ holds {actual} directories. "
        f"Add or remove a badge under '## Stacks (N)'."
    )


def test_every_shields_line_in_the_section_is_a_well_formed_badge() -> None:
    # A badge the pattern does not recognise would be left out of the count
    # above without failing it, so a malformed line has to fail on its own.
    _, lines, _ = _stack_section()
    malformed = [line for line in lines if "img.shields.io" in line and not BADGE.match(line)]
    assert not malformed, (
        "These lines under '## Stacks (N)' mention img.shields.io but are not a "
        f"'[![Name](badge-url)](website)' badge on a line of its own: {malformed}"
    )


def test_badges_are_unique_and_sorted_by_name() -> None:
    badges = _badge_names()
    duplicates = sorted({name for name in badges if badges.count(name) > 1})
    assert not duplicates, f"Duplicate stack badges in README.md: {duplicates}"
    expected = sorted(badges, key=str.casefold)
    out_of_place = [
        f"{got!r} (expected {want!r})"
        for got, want in zip(badges, expected, strict=True)
        if got != want
    ]
    assert not out_of_place, (
        "Stack badges in README.md are sorted by name, ignoring case. "
        f"First badge out of place: {out_of_place[0]}"
    )


def test_no_hard_coded_stack_count_outside_the_heading() -> None:
    _, _, outside = _stack_section()
    hits = HARD_CODED_COUNT.findall(outside)
    assert not hits, (
        f"README.md states a catalogue size in running text: {hits}. The heading "
        f"'## Stacks (N)' is the only place the number lives, because it is the only "
        f"place a test compares it with stacks/."
    )

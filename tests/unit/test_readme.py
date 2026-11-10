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
# "163 stacks", "80+ Docker services", "60 data tools" — a catalogue size
# written as a number in running text.
HARD_CODED_COUNT = re.compile(
    r"\b\d+\+?\s+(?:Docker\s+|data\s+)?(?:stacks|services|tools)\b", re.IGNORECASE
)


def _stack_section() -> tuple[int, list[str], str]:
    """Return the heading's count, the section's lines, and the README without the heading line."""
    text = README.read_text(encoding="utf-8")
    match = HEADING.search(text)
    assert match, "README.md has no '## Stacks (N)' heading"
    rest = text[match.end() :]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    # Everything except the heading line itself: prose after the badges is
    # still part of the README and must not restate the count either.
    without_heading = text[: match.start()] + rest
    return int(match.group(1)), section.splitlines(), without_heading


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


def test_every_badge_like_line_in_the_section_is_a_well_formed_badge() -> None:
    # A badge the pattern does not recognise would be left out of the count
    # above without failing it, so a malformed line has to fail on its own.
    _, lines, _ = _stack_section()
    malformed = [line for line in lines if line.startswith(("[![", "![")) and not BADGE.match(line)]
    assert not malformed, (
        "These lines under '## Stacks (N)' start like a badge or an image but are not a "
        f"'[![Name](badge-url)](website)' badge on a line of its own: {malformed}"
    )


def test_badge_block_holds_nothing_but_badges() -> None:
    # Prose after the last badge (tiers, the licence note) is fine. A line
    # between two badges is a description creeping back into the list.
    _, lines, _ = _stack_section()
    positions = [i for i, line in enumerate(lines) if BADGE.match(line)]
    assert positions, "README.md has no stack badges under '## Stacks (N)'"
    block = lines[positions[0] : positions[-1] + 1]
    strays = [line for line in block if not BADGE.match(line)]
    assert not strays, (
        "The badge list under '## Stacks (N)' is badges only, one per line with no "
        f"blank lines or text between them. Found: {strays}"
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

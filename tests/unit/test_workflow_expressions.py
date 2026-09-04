"""GitHub expression syntax inside workflow and action script bodies.

WHY THIS EXISTS. A comment written to explain that GitHub expressions must
not be interpolated into a shell body contained one — spelled with empty
braces — inside a `run:` block. GitHub substitutes expressions across the
whole `run:` body before bash ever sees it, so a `#` does not hide it, and
an empty expression is a template error: the action failed to load and
every spin-up died at that step with

    (Line: 137, Col: 12): An expression was expected

`actionlint` does not catch it — verified by reinserting the empty
expression and running the hook, which passed. Nor does YAML parsing: the
file is valid YAML, and only GitHub's own template layer rejects it. That
leaves a test.

A comment OUTSIDE a `run:` body is fine — GitHub never parses YAML comments
— which is why the rule is scoped to script bodies rather than to the files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_WORKFLOWS = sorted(Path(".github/workflows").glob("*.y*ml"))
_ACTIONS = sorted(Path(".github/actions").rglob("action.y*ml"))
_FILES = _WORKFLOWS + _ACTIONS

_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")


def _run_line_ranges(path: Path) -> list[tuple[int, int]]:
    """Line ranges (1-based, inclusive) of every `run:` value in the file.

    Uses the YAML node graph rather than a regex over the text. A regex has
    to enumerate the forms `run:` can take — `run: |`, `|-`, `>`, `>+`, an
    inline `run: echo …`, and `- run: |` when it is a step's first key —
    and the first version of this check missed three of the five. The
    parser knows all of them, and cannot fall behind YAML.
    """
    ranges: list[tuple[int, int]] = []

    def walk(node: object) -> None:
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode) and key.value == "run":
                    ranges.append((value.start_mark.line + 1, value.end_mark.line + 1))
                walk(value)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item)

    for document in yaml.compose_all(path.read_text()):
        if document is not None:
            walk(document)
    return ranges


def _offenders(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    ranges = _run_line_ranges(path)
    found = []
    for i, line in enumerate(lines, 1):
        if not any(start <= i <= end for start, end in ranges):
            continue  # outside every script body — a YAML comment, say
        for match in _EXPRESSION.finditer(line):
            if match.group(1).strip():
                continue  # a real expression; not our business
            found.append(f"{path}:{i}: {line.strip()}")
    return found


def test_workflow_files_were_found() -> None:
    """A glob that matches nothing would make every test below vacuous."""
    assert len(_WORKFLOWS) >= 10, f"only {len(_WORKFLOWS)} workflows found"
    assert len(_ACTIONS) >= 1, f"only {len(_ACTIONS)} composite actions found"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_no_empty_github_expression_in_a_script_body(path: Path) -> None:
    """An empty `${{ }}` in a `run:` body stops the file from loading.

    Not a style rule: GitHub refuses the whole workflow or action, so the
    failure is total and lands at runtime rather than in review.
    """
    offenders = _offenders(path)
    assert not offenders, (
        "empty GitHub expression inside a run: body — GitHub reads it as an "
        "expression and refuses the file:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    ("label", "content", "expected"),
    [
        ("inline run", "runs:\n  steps:\n    - run: echo ${{ }}\n", 1),
        ("block scalar", "runs:\n  steps:\n    - run: |\n        echo ${{ }}\n", 1),
        ("chomped block", "runs:\n  steps:\n    - run: |-\n        echo ${{ }}\n", 1),
        ("folded block", "runs:\n  steps:\n    - run: >+\n        echo ${{ }}\n", 1),
        (
            "run below other keys",
            "runs:\n  steps:\n    - name: x\n      run: |\n        echo ${{ }}\n",
            1,
        ),
        ("yaml comment", "runs:\n  # mentions ${{ }} harmlessly\n  steps: []\n", 0),
        (
            "comment above run",
            "runs:\n  steps:\n    # ${{ }} here is fine\n    - run: |\n        echo ok\n",
            0,
        ),
        ("real expression", "runs:\n  steps:\n    - run: |\n        echo ${{ inputs.x }}\n", 0),
    ],
)
def test_the_check_sees_every_run_form_and_no_comments(
    tmp_path: Path, label: str, content: str, expected: int
) -> None:
    """The rule above passes trivially if the detection does not work.

    Every form `run:` can take is here because the first version of this
    check used a regex and missed three of them — inline values, chomping
    indicators, and `- run: |` where `run` is a step's first key. The real
    bug was caught only because it happened to use the one form that regex
    recognised. The comment cases are here for the opposite reason: the
    same text is harmless in a YAML comment and fatal one line deeper, and
    a check that cannot tell them apart is either useless or unusable.
    """
    planted = tmp_path / "action.yml"
    planted.write_text(content)
    offenders = _offenders(planted)
    assert len(offenders) == expected, f"{label}: {offenders}"


# Every `npx wrangler@...` in CI must name an exact version. `wrangler@4`
# and `wrangler@latest` both make npm resolve a range at run time, which
# costs a registry round-trip on a cold runner and -- worse -- lets two
# jobs in the same run legitimately execute different builds with nothing
# recording which. #784 has the measurement: one unpinned fetch sat for
# 423 seconds inside a step that normally takes 16.
#
# This test, not an env var, is the single source of truth. Threading a
# WRANGLER_VERSION through 7 workflows, 3 shell scripts and a composite
# action would add a way for the value to go missing silently; a literal
# that a test keeps identical everywhere cannot.
# The `@spec` is optional on purpose. A bare `npx wrangler` is the worst
# case, not an absent one -- it resolves to whatever npm calls latest --
# and a pattern that required the `@` would have made it invisible to the
# very test meant to catch it.
_NPX_WRANGLER = re.compile(r"npx wrangler(?:@(?P<spec>[^\s\"';|)]+))?")
_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

# Every candidate file, not only the ones already invoking Wrangler with a
# version. Filtering the list on `npx wrangler@` would have excluded a file
# whose only invocation had just lost its pin.
#
# Both script directories. `scripts/` was missed the first time and held a
# live `npx wrangler@latest` that the initial sweep never saw, so the
# "all 64 sites" claim was short by one. A guardrail whose search path is
# narrower than the thing it guards reports success by not looking.
#
# Not covered: `docs/**`. A copy-paste command in prose drifting from the
# pin is a documentation inconsistency, not an unreproducible run, and a
# guardrail over prose invites false positives on text that deliberately
# shows an older form. The two occurrences in
# docs/admin-guides/snapshot-lifecycle.md were brought in line by hand.
_WRANGLER_FILES = sorted(
    (
        *_FILES,
        *Path(".github/scripts").glob("*.sh"),
        *Path("scripts").glob("*.sh"),
    )
)


def test_every_npx_wrangler_pins_an_exact_version() -> None:
    """No `wrangler@4`, no `wrangler@latest` -- an exact x.y.z everywhere."""
    offenders: list[str] = []
    for path in _WRANGLER_FILES:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for match in _NPX_WRANGLER.finditer(line):
                spec = match.group("spec")
                if spec is None:
                    offenders.append(f"{path}:{number}: bare `npx wrangler`, no version at all")
                elif not _EXACT_VERSION.fullmatch(spec):
                    offenders.append(f"{path}:{number}: wrangler@{spec}")

    assert not offenders, (
        "npx wrangler invocations that do not pin an exact version:\n  "
        + "\n  ".join(offenders)
        + "\nUse wrangler@<major>.<minor>.<patch>. See #784."
    )


def test_all_npx_wrangler_invocations_agree_on_one_version() -> None:
    """One version across CI, so no two jobs can run different builds."""
    versions: dict[str, list[str]] = {}
    for path in _WRANGLER_FILES:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for match in _NPX_WRANGLER.finditer(line):
                spec = match.group("spec")
                if spec is None:
                    continue  # the pinning test above owns this case
                versions.setdefault(spec, []).append(f"{path}:{number}")

    assert versions, (
        "no `npx wrangler@` invocations found at all -- if Wrangler is now "
        "invoked some other way, these two tests need rewriting rather than "
        "deleting, or the pin stops being enforced."
    )
    assert len(versions) == 1, (
        "CI runs more than one Wrangler version:\n  "
        + "\n  ".join(
            f"{v}: {len(where)} site(s), first at {where[0]}"
            for v, where in sorted(versions.items())
        )
        + "\nBumping the pin means bumping every site."
    )

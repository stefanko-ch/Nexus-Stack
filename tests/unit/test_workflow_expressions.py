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

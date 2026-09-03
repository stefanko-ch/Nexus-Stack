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

_WORKFLOWS = sorted(Path(".github/workflows").glob("*.y*ml"))
_ACTIONS = sorted(Path(".github/actions").rglob("action.y*ml"))
_FILES = _WORKFLOWS + _ACTIONS

_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")
_RUN_BLOCK = re.compile(r"\s*run:\s*[|>]")


def _inside_run_block(lines: list[str], index: int) -> bool:
    """Is line `index` (0-based) part of a `run:` block scalar?

    Walks back to the first line indented less than this one: for a block
    scalar's content that is the `run:` key itself.
    """
    indent = len(lines[index]) - len(lines[index].lstrip())
    for j in range(index - 1, -1, -1):
        line = lines[j]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) >= indent:
            continue
        return bool(_RUN_BLOCK.match(line))
    return False


def _offenders(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    found = []
    for i, line in enumerate(lines):
        for match in _EXPRESSION.finditer(line):
            if match.group(1).strip():
                continue  # a real expression; not our business
            if _inside_run_block(lines, i):
                found.append(f"{path}:{i + 1}: {line.strip()}")
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


def test_the_check_detects_a_planted_empty_expression(tmp_path: Path) -> None:
    """The rule above passes trivially if the detection does not work.

    Both shapes are here on purpose: the same text is harmless in a YAML
    comment and fatal one line deeper, and a check that cannot tell them
    apart would either miss the bug or ban a legitimate comment.
    """
    planted = tmp_path / "action.yml"
    planted.write_text(
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    # Harmless: a YAML comment mentioning ${{ }} is never parsed.\n"
        "    - name: Example\n"
        "      shell: bash\n"
        "      run: |\n"
        "        # Fatal: substitution runs over the whole body first.\n"
        "        echo ${{ }}\n"
    )
    offenders = _offenders(planted)
    assert len(offenders) == 1, offenders
    assert offenders[0].endswith("echo ${{ }}")
    assert ":9:" in offenders[0], "flagged the wrong line"

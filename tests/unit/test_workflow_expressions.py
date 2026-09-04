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
from typing import Any

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
# Matches inside comments and echoed strings as well as real commands.
# That is not a bug and it caught prose twice while this branch was being
# written: a comment reading "every `npx wrangler` invocation" is text a
# future maintainer may copy into a shell. Write "Wrangler" in prose.
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


# The npm-store cache key embeds the Wrangler pin. It has to: without it, a
# pin bump restores the previous store under the loose restore-key, and
# because the primary key is unchanged GitHub does not save the new one --
# so the new version is re-downloaded on every run from then on, silently
# and permanently. That failure is invisible in a green workflow, which is
# why it gets a test rather than a comment.
#
# Walks the parsed steps rather than grepping lines. A line-based version
# checked only that the versions it *found* agreed, so deleting the pin
# from one workflow's key left the others agreeing and the test silent --
# the fifth time in this branch's history that a guardrail missed its own
# evasion rather than the obvious violation.
_NPM_CACHE_STEP = "Cache the npm store"
_CACHE_KEY_PIN = re.compile(r"-wrangler(?P<spec>[0-9][^-\s]*)-")


def _npm_cache_steps() -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in _WORKFLOWS:
        document = yaml.safe_load(path.read_text())
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                if isinstance(step, dict) and str(step.get("name", "")).startswith(_NPM_CACHE_STEP):
                    found.append((path, step))
    return found


def test_npm_cache_keys_carry_the_pinned_wrangler_version() -> None:
    """Every npm-store cache key names the version `npx wrangler@…` uses."""
    pinned = {
        match.group("spec")
        for path in _WRANGLER_FILES
        for match in _NPX_WRANGLER.finditer(path.read_text())
        if match.group("spec") is not None
    }
    assert len(pinned) == 1, f"expected exactly one pinned version, found {sorted(pinned)}"
    version = pinned.pop()

    steps = _npm_cache_steps()
    assert steps, (
        f"no step named {_NPM_CACHE_STEP!r} in any workflow. If the caching was "
        "removed deliberately, delete this test with it; otherwise the npm "
        "store is no longer cached at all. See #784."
    )

    offenders: list[str] = []
    for path, step in steps:
        key = str((step.get("with") or {}).get("key", ""))
        match = _CACHE_KEY_PIN.search(key)
        if match is None:
            offenders.append(f"{path}: key names no Wrangler version: {key}")
        elif match.group("spec") != version:
            offenders.append(f"{path}: key says {match.group('spec')}, npx says {version}")

    assert not offenders, (
        "npm-store cache keys out of step with the Wrangler pin:\n  "
        + "\n  ".join(offenders)
        + "\nA key that omits or misnames the pin makes a bumped Wrangler "
        "uncacheable, permanently and silently."
    )


def test_every_workflow_touching_npm_caches_the_store() -> None:
    """A workflow that runs npm must cache ~/.npm -- all of them, not some.

    Asserting only that *a* cache step exists somewhere let the step be
    deleted from one workflow while the others kept the test green. The
    set that needs the cache is derivable, so derive it.
    """
    uses_npm = {
        path
        for path in _WORKFLOWS
        if re.search(r"npx wrangler|npm ci\b|npm run ", path.read_text())
    }
    has_cache = {path for path, _ in _npm_cache_steps()}

    missing = sorted(str(p) for p in uses_npm - has_cache)
    assert not missing, (
        "workflows that run npm without caching ~/.npm:\n  "
        + "\n  ".join(missing)
        + f"\nAdd a step named {_NPM_CACHE_STEP!r}. A cold npm fetch cost "
        "145-425s per occurrence in run 33852993550. See #784."
    )

    stray = sorted(str(p) for p in has_cache - uses_npm)
    assert not stray, (
        "workflows with an npm-store cache but no npm usage:\n  "
        + "\n  ".join(stray)
        + "\nEither the usage was removed and the cache step should go too, "
        "or the detection above needs widening."
    )

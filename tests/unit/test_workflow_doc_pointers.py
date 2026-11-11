"""A workflow message that names a section of a guide names one that exists.

The strict_snapshot abort in teardown-snapshot.yml tells the operator to read
"'A strict snapshot aborted the teardown'" in the snapshot-lifecycle guide. A
heading renamed in the guide would leave that message pointing at nothing, at
the moment someone is reading it because a teardown just failed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "teardown-snapshot.yml"
GUIDE = REPO_ROOT / "docs" / "admin-guides" / "snapshot-lifecycle.md"

# echo "   docs/admin-guides/snapshot-lifecycle.md under"
# echo "   'A strict snapshot aborted the teardown'."
_POINTER = re.compile(
    r"docs/admin-guides/snapshot-lifecycle\.md under\"\s*\n\s*echo \"\s*'(?P<heading>[^']+)'"
)


def _headings(markdown: str) -> set[str]:
    return {m.group(1).strip() for m in re.finditer(r"^#{1,6} (.+)$", markdown, re.MULTILINE)}


def test_the_abort_message_names_a_heading_that_exists() -> None:
    pointers = _POINTER.findall(WORKFLOW.read_text(encoding="utf-8"))
    assert pointers, "teardown-snapshot.yml no longer points at the snapshot-lifecycle guide"
    headings = _headings(GUIDE.read_text(encoding="utf-8"))
    for heading in pointers:
        assert heading in headings, (
            f"teardown-snapshot.yml sends the operator to {heading!r}, "
            f"which is not a heading in {GUIDE.relative_to(REPO_ROOT)}"
        )

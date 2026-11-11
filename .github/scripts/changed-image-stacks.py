#!/usr/bin/env python3
"""Which stack images a pull request has to build.

Reads the changed paths of a pull request, one per line, on standard input
and prints a JSON list of stack names for the build matrix of
`.github/workflows/stack-image-builds.yaml`.

A stack is listed when it builds its own image (`stacks/<name>/Dockerfile`)
and the pull request touched anything in its folder: the Dockerfile, a lock
file, a script it copies, or its image test.

When the pull request changes the check itself (the workflow or this
script), every stack that ships an image test is listed, so a change to the
check is exercised against the images it is meant to guard.

Exit status: 0 with the list on standard output. 2 when the stacks
directory is missing, which means the caller ran it from the wrong place
and an empty list would read as "nothing to build".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# A change to one of these re-runs the check against every tested image.
CHECK_FILES = (
    ".github/workflows/stack-image-builds.yaml",
    ".github/scripts/changed-image-stacks.py",
)
IMAGE_TEST = "image-test.sh"


def stacks_to_build(changed: list[str], stacks_dir: Path) -> list[str]:
    """The stacks whose image the changed paths can affect, sorted."""
    with_dockerfile = {p.parent.name for p in stacks_dir.glob("*/Dockerfile")}
    selected: set[str] = set()
    for path in changed:
        parts = Path(path).parts
        if len(parts) >= 3 and parts[0] == stacks_dir.name and parts[1] in with_dockerfile:
            selected.add(parts[1])
    if any(path in CHECK_FILES for path in changed):
        selected |= {name for name in with_dockerfile if (stacks_dir / name / IMAGE_TEST).is_file()}
    return sorted(selected)


def main() -> int:
    """Print the build matrix for the changed paths on standard input."""
    stacks_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("stacks")
    if not stacks_dir.is_dir():
        print(f"changed-image-stacks: no such directory: {stacks_dir}", file=sys.stderr)
        return 2
    changed = [line.strip() for line in sys.stdin if line.strip()]
    print(json.dumps(stacks_to_build(changed, stacks_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

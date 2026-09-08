"""Conventions the seeded workspace files have to satisfy.

These read the real ``examples/workspace-seeds/`` tree rather than a fixture:
the files ship to every user's workspace verbatim, so what matters is the
bytes on disk, not a reconstruction of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SEEDS_DIR = Path(__file__).resolve().parents[2] / "examples" / "workspace-seeds"
# rglob, not glob: the seeder itself walks recursively (seeder.py:170,
# `root.rglob("*")`), and other seed trees already nest — kestra/flows,
# kestra/workflows, prefect/flows. A notebook at marimo/<sub>/x.py would
# therefore ship without this check ever seeing it.
MARIMO_SEEDS = sorted((SEEDS_DIR / "marimo").rglob("*.py"))

# Marimo's own limit, copied from the version this project runs:
#
#   marimo/_server/files/directory_scanner.py
#     READ_LIMIT = 512
#     "Python (.py) files are marimo apps if the header (first 512 bytes)
#      contains both `marimo.App` and `import marimo`."
#
# Not a heuristic of ours, and not negotiable from this side.
MARIMO_HEADER_READ_LIMIT = 512


def _is_notebook(source: bytes) -> bool:
    """Whether the file is a marimo notebook at all, reading the WHOLE file.

    Distinguishes a notebook from a plain helper module such as
    ``_nexus_spark.py``, which must not be held to the header rule.
    """
    return b"marimo.App" in source and b"import marimo" in source


def test_marimo_seed_directory_is_not_empty() -> None:
    """Guard against the checks below passing vacuously.

    A renamed directory would otherwise turn every parametrised test into
    zero tests, and the suite would go green on no coverage at all.
    """
    assert MARIMO_SEEDS, f"no marimo seeds found under {SEEDS_DIR / 'marimo'}"


@pytest.mark.parametrize(
    "path", MARIMO_SEEDS, ids=lambda p: str(p.relative_to(SEEDS_DIR / "marimo"))
)
def test_marimo_seed_is_recognisable_as_a_notebook(path: Path) -> None:
    """A seeded notebook must declare itself inside marimo's 512-byte header.

    Miss it and nothing fails: the file opens perfectly by direct URL and
    runs normally. It simply appears in marimo's file browser with a plain
    code icon rather than a notebook icon, which is how a user learns the
    seeds are "not there" — reported exactly that way twice before the cause
    was found.

    The trap is a long module docstring. Prose above ``import marimo`` pushes
    both markers past the window, and the failure scales with how well the
    file is documented. Five of six seeds were over the limit when this test
    was written; the sixth passed at byte 419, which was luck rather than
    design.

    The fix is not to delete the docstring — it is what a reader sees on
    GitHub. Keep a short summary above the header and move the rest into the
    notebook's first ``mo.md`` cell, where a reader of the notebook sees it
    instead.
    """
    source = path.read_bytes()
    if not _is_notebook(source):
        pytest.skip(f"{path.name} is a helper module, not a notebook")

    header = source[:MARIMO_HEADER_READ_LIMIT]

    # Asserted separately, and in the order they appear, so a failure names
    # the marker that actually fell out of the window rather than reporting
    # "one of two things is wrong".
    def _too_late(marker: bytes) -> str:
        return (
            f"{path.name}: `{marker.decode()}` sits at byte "
            f"{source.find(marker)}, past marimo's "
            f"{MARIMO_HEADER_READ_LIMIT}-byte header window, so marimo will "
            f"not recognise this file as a notebook. Shorten the module "
            f"docstring and move the prose into the first mo.md cell."
        )

    assert b"import marimo" in header, _too_late(b"import marimo")
    assert b"marimo.App" in header, _too_late(b"marimo.App")

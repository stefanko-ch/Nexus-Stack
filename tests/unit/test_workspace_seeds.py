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

# Same reasoning for Kestra: rglob, both flows/ and workflows/, and any
# future subdirectory under kestra/.
KESTRA_SEEDS = sorted(p for p in (SEEDS_DIR / "kestra").rglob("*") if p.suffix in {".yaml", ".yml"})

# Both spellings Kestra accepts. The legacy one still parses, so a seed
# using it would fire exactly as hard as one using the current name.
SCHEDULE_TRIGGER_TYPES = (
    "io.kestra.plugin.core.trigger.Schedule",
    "io.kestra.core.models.triggers.types.Schedule",
)

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


# ---------------------------------------------------------------------------
# Seeded Kestra flows must not carry a schedule trigger
# ---------------------------------------------------------------------------


def test_kestra_seed_directory_is_not_empty() -> None:
    """Otherwise the parametrised check below silently covers nothing."""
    assert KESTRA_SEEDS, f"no Kestra seeds found under {SEEDS_DIR / 'kestra'}"


@pytest.mark.parametrize("path", KESTRA_SEEDS, ids=lambda p: p.name)
def test_kestra_seed_declares_no_schedule_trigger(path: Path) -> None:
    """A seeded flow lands on *every* user stack, so a cron trigger fires N
    times in parallel for an N-user cohort — multiplying CloudFront
    downloads, R2 egress, Databricks Free-Edition quota burn and Kestra
    container CPU. CLAUDE.md states the rule; a scheduled flow belongs to
    the orchestrator's `_phase_kestra_register`, outside workspace-seeds/.

    This test exists because the rule had no enforcement. `.github/
    copilot-instructions.md:107-111` tells Copilot to "flag it" — and
    Copilot does not review this repository, which is what PR #915 is
    about. A rule whose only enforcement is a reviewer that never runs is
    not enforced, and a violation would reach users' workspaces unseen.
    """
    text = path.read_text(encoding="utf-8")
    offenders = [t for t in SCHEDULE_TRIGGER_TYPES if t in text]
    assert not offenders, (
        f"{path.relative_to(SEEDS_DIR)} declares a schedule trigger "
        f"({', '.join(offenders)}). Seeded flows are run manually; register a "
        f"scheduled flow through _phase_kestra_register instead."
    )

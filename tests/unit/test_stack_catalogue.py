"""The generated stack catalogue in ``docs/stacks/overview.md``.

Two kinds of test. The first group renders from small inputs and pins the
format. The second reads the real repository, because the failure this guards
against is the committed page and ``services.yaml`` drifting apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexus_deploy import stack_catalogue as sc

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERVIEW = REPO_ROOT / "docs" / "stacks" / "overview.md"

CATEGORIES_TS = """
export const CATEGORIES: Record<string, { name: string; description: string }> = {
  'core': { name: 'Core Infrastructure', description: 'Essential.' },
  'databases': { name: 'Databases', description: 'Engines.' },
  'storage': { name: 'Object Storage', description: 'S3.' },
};

export const CATEGORY_ORDER = [
  'core', 'databases',
  'storage',
];
"""

SERVICES: dict[str, dict[str, Any]] = {
    "zeta": {"category": "databases", "description": "Last  by\n name.", "image": "zeta:1"},
    "alpha": {
        "category": "databases",
        "description": "A | B",
        "image": "alpha:2",
        "tier": "proven",
    },
    "git": {"category": "core", "description": "Forge.", "image": "git:3", "core": True},
    "alpha-ui": {
        "category": "databases",
        "description": "Second service.",
        "image": "alpha:2",
        "stack": "alpha",
    },
}
TITLES: dict[str, str | None] = {"zeta": "Zeta", "alpha": "alpha", "git": "Git", "alpha-ui": None}


def _render() -> str:
    return sc.render_catalogue(
        sc.collect_stacks(SERVICES, TITLES), sc.read_categories(CATEGORIES_TS)
    )


# ---- format ---------------------------------------------------------------


def test_categories_come_back_in_the_declared_order() -> None:
    assert sc.read_categories(CATEGORIES_TS) == [
        ("core", "Core Infrastructure"),
        ("databases", "Databases"),
        ("storage", "Object Storage"),
    ]


def test_categories_that_disagree_with_their_order_are_rejected() -> None:
    broken = CATEGORIES_TS.replace("'storage',\n];", "];")
    with pytest.raises(sc.CatalogueError, match="named but not in order: \\['storage'\\]"):
        sc.read_categories(broken)


def test_unreadable_categories_file_is_rejected() -> None:
    with pytest.raises(sc.CatalogueError, match="could not read"):
        sc.read_categories("export const NOTHING = {};")


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ('---\ntitle: "Kestra"\n---\n\nbody', "Kestra"),
        ("---\ntitle: Stacks Overview\ndescription: x\n---\n", "Stacks Overview"),
        ("# No frontmatter\n\ntitle: nope\n", None),
        ("---\ndescription: only\n---\n", None),
        ('---\ntitle: ""\n---\n', None),
        ("---\ntitle: never closed\n", None),
        ('---\ntitle: "A \\"quoted\\" name"\n---\n', 'A "quoted" name'),
        ('---\ntitle: Ends with a quote"\n---\n', 'Ends with a quote"'),
        ("---\ntitle: [not, a, string]\n---\n", None),
        ("---\n- a list\n---\n", None),
        ("---\ntitle: 'unbalanced\n---\n", None),
    ],
)
def test_read_title(page: str, expected: str | None) -> None:
    assert sc.read_title(page) == expected


def test_render_groups_sorts_and_counts() -> None:
    assert _render() == "\n".join(
        [
            sc.BEGIN_MARKER,
            "",
            "**3 stacks in 2 categories.** Each name links to the stack's own page.",
            "",
            "## Core Infrastructure",
            "",
            "| Stack | What it is | Tier | Image |",
            "|-------|------------|------|-------|",
            "| [Git](./git.md) | Forge. | core | `git:3` |",
            "",
            "## Databases",
            "",
            "| Stack | What it is | Tier | Image |",
            "|-------|------------|------|-------|",
            "| [alpha](./alpha.md) | A \\| B | proven | `alpha:2` |",
            "| [Zeta](./zeta.md) | Last by name. | best-effort | `zeta:1` |",
            "",
            sc.END_MARKER,
        ]
    )


def test_a_second_service_inside_a_stack_gets_no_row() -> None:
    assert "alpha-ui" not in _render()
    assert "Second service." not in _render()


def test_a_stack_without_a_page_title_is_an_error_not_a_blank_name() -> None:
    with pytest.raises(sc.CatalogueError, match="no frontmatter title for: \\['zeta'\\]"):
        sc.collect_stacks(SERVICES, {**TITLES, "zeta": None})


def test_an_entry_missing_a_field_is_named_in_the_error() -> None:
    services = {**SERVICES, "bare": {"category": "core", "image": ""}}
    with pytest.raises(sc.CatalogueError, match="bare \\(no description, image\\)"):
        sc.collect_stacks(services, {**TITLES, "bare": "Bare"})


@pytest.mark.parametrize("content", ["", "- a\n- list\n", "other: {}\n", "services: []\n"])
def test_build_rejects_a_services_file_without_a_services_mapping(
    tmp_path: Path, content: str
) -> None:
    (tmp_path / "services.yaml").write_text(content)
    with pytest.raises(sc.CatalogueError, match="no top-level 'services' mapping"):
        sc.build(tmp_path)


def test_a_category_the_control_plane_does_not_define_is_an_error() -> None:
    services = {**SERVICES, "odd": {"category": "nowhere", "description": "x", "image": "o:1"}}
    stacks = sc.collect_stacks(services, {**TITLES, "odd": "Odd"})
    with pytest.raises(sc.CatalogueError, match="\\['nowhere'\\]"):
        sc.render_catalogue(stacks, sc.read_categories(CATEGORIES_TS))


def test_page_slug_exception_is_used_for_the_link() -> None:
    services = {"woodpecker": {"category": "core", "description": "CI.", "image": "w:1"}}
    stacks = sc.collect_stacks(services, {"woodpecker": "Woodpecker CI"})
    assert "[Woodpecker CI](./woodpecker-ci.md)" in sc.render_catalogue(
        stacks, sc.read_categories(CATEGORIES_TS)
    )


def test_replace_block_keeps_everything_outside_the_markers() -> None:
    page = f"intro\n\n{sc.BEGIN_MARKER}\nold\n{sc.END_MARKER}\n\noutro\n"
    assert sc.replace_block(page, "NEW") == "intro\n\nNEW\n\noutro\n"


@pytest.mark.parametrize(
    "page",
    [
        "no markers at all",
        f"{sc.BEGIN_MARKER}\nnever closed",
        f"{sc.END_MARKER}\n{sc.BEGIN_MARKER}",
    ],
)
def test_replace_block_refuses_a_page_without_usable_markers(page: str) -> None:
    with pytest.raises(sc.CatalogueError, match="markers"):
        sc.replace_block(page, "NEW")


def test_write_regenerates_the_block_in_place(tmp_path: Path) -> None:
    (tmp_path / "docs" / "stacks").mkdir(parents=True)
    (tmp_path / "control-plane" / "src" / "lib").mkdir(parents=True)
    (tmp_path / "control-plane" / "src" / "lib" / "categories.ts").write_text(CATEGORIES_TS)
    (tmp_path / "services.yaml").write_text(
        "services:\n  git:\n    category: core\n    description: Forge.\n    image: git:3\n    core: true\n"
        "  ghost:\n    category: core\n    description: No page.\n    image: g:1\n    stack: git\n"
    )
    (tmp_path / "docs" / "stacks" / "git.md").write_text('---\ntitle: "Git"\n---\n')
    overview = tmp_path / "docs" / "stacks" / "overview.md"
    overview.write_text(f"before\n{sc.BEGIN_MARKER}\nstale\n{sc.END_MARKER}\nafter\n")

    assert sc.write(tmp_path) == overview
    text = overview.read_text()
    assert text.startswith("before\n")
    assert text.endswith("\nafter\n")
    assert "| [Git](./git.md) | Forge. | core | `git:3` |" in text
    assert "stale" not in text


# ---- the real repository --------------------------------------------------


def test_committed_catalogue_matches_services_yaml() -> None:
    page = OVERVIEW.read_text(encoding="utf-8")
    assert sc.replace_block(page, sc.build(REPO_ROOT)) == page, (
        "docs/stacks/overview.md is stale. Regenerate it with "
        "`uv run python -m nexus_deploy.stack_catalogue` and commit the result."
    )


def test_catalogue_has_one_row_per_stack_directory() -> None:
    block = sc.build(REPO_ROOT)
    rows = [line for line in block.splitlines() if line.startswith("| [")]
    directories = [p for p in (REPO_ROOT / "stacks").iterdir() if p.is_dir()]
    assert len(rows) == len(directories), (
        f"the catalogue has {len(rows)} rows but stacks/ holds {len(directories)} directories"
    )


def test_every_catalogue_link_points_at_an_existing_page() -> None:
    block = sc.build(REPO_ROOT)
    targets = [
        line.split("](./", 1)[1].split(")", 1)[0] for line in block.splitlines() if "](./" in line
    ]
    missing = [t for t in targets if not (REPO_ROOT / "docs" / "stacks" / t).exists()]
    assert targets
    assert not missing, f"catalogue links to pages that do not exist: {missing}"

"""The generated diagrams in ``docs/concepts/assets/``.

The diagrams these replaced went stale because nothing compared them with
anything: two said "61 stacks" for months. So the checks here are about the
text in the pictures, and about the committed files matching the generator.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from nexus_deploy import doc_diagrams

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "docs" / "concepts" / "assets"
SVG = "{http://www.w3.org/2000/svg}"

RENDERED = {name: render() for name, render in doc_diagrams.DIAGRAMS.items()}


def _texts(svg: str) -> list[str]:
    """Every line of text drawn in the picture, title excluded."""
    root = ET.fromstring(svg)  # noqa: S314 — our own generated SVG, not untrusted input
    return [span.text or "" for span in root.iter(f"{SVG}tspan")]


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_committed_diagram_matches_the_generator(name: str) -> None:
    path = ASSETS / name
    assert path.exists(), f"{path} is missing. Run `uv run python -m nexus_deploy.doc_diagrams`."
    assert path.read_text(encoding="utf-8") == RENDERED[name], (
        f"docs/concepts/assets/{name} is stale. Regenerate it with "
        f"`uv run python -m nexus_deploy.doc_diagrams` and commit the result."
    )


def test_no_svg_in_the_folder_is_left_over_from_an_earlier_generator() -> None:
    on_disk = {p.name for p in ASSETS.glob("*.svg")}
    assert on_disk == set(RENDERED), (
        f"docs/concepts/assets/ holds SVGs the generator does not produce: {sorted(on_disk - set(RENDERED))}"
    )


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_diagram_is_well_formed_and_labelled(name: str) -> None:
    root = ET.fromstring(RENDERED[name])  # noqa: S314 — our own generated SVG
    assert root.tag == f"{SVG}svg"
    assert root.get("role") == "img"
    label = root.get("aria-label")
    assert label, "a diagram needs an aria-label for screen readers"
    title = root.find(f"{SVG}title")
    assert title is not None
    assert title.text == label


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_diagram_carries_its_own_background(name: str) -> None:
    # Without a full-canvas rect the page background shows through, and grey
    # label text becomes unreadable in one of GitHub's two themes.
    root = ET.fromstring(RENDERED[name])  # noqa: S314 — our own generated SVG
    _, _, width, height = (root.get("viewBox") or "").split()
    backgrounds = [
        rect
        for rect in root.iter(f"{SVG}rect")
        if rect.get("width") == width
        and rect.get("height") == height
        and rect.get("fill") == doc_diagrams.BG
    ]
    assert len(backgrounds) == 1


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_diagram_states_no_number_that_can_go_stale(name: str) -> None:
    # "0 open ports" is a property of the design. A stack count, a price or a
    # version is a fact about today.
    for line in _texts(RENDERED[name]):
        # Whole numbers only: the 2 in "R2" is part of a product name.
        numbers = re.findall(r"\b\d+\b", line)
        assert numbers in ([], ["0"]), f"{name} draws a number in {line!r}"


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_diagram_text_is_large_enough_to_read(name: str) -> None:
    root = ET.fromstring(RENDERED[name])  # noqa: S314 — our own generated SVG
    sizes = [float(text.get("font-size", "0")) for text in root.iter(f"{SVG}text")]
    assert sizes
    assert min(sizes) >= 12.5, f"{name} has text at {min(sizes)}px in an 820px-wide picture"


@pytest.mark.parametrize("name", sorted(RENDERED))
def test_diagram_references_nothing_outside_itself(name: str) -> None:
    # An SVG shown through <img> cannot load external fonts, images or scripts.
    svg = RENDERED[name]
    assert "<script" not in svg
    assert "<image" not in svg
    assert "href=" not in svg
    assert not re.search(r"url\((?!#arrow-[a-z]\))", svg), (
        "only the arrow markers may be referenced"
    )


def test_every_arrow_marker_that_is_used_is_defined() -> None:
    for name, svg in RENDERED.items():
        used = set(re.findall(r"url\(#(arrow-[a-z])\)", svg))
        defined = set(re.findall(r'<marker id="(arrow-[a-z])"', svg))
        assert used <= defined, f"{name} uses undefined markers {sorted(used - defined)}"


def test_text_and_labels_are_escaped() -> None:
    # A label with an ampersand or a quote must not produce invalid SVG.
    svg = doc_diagrams._svg(
        100, 50, "A & B", "x < y", 'say "hi" & go', doc_diagrams._text(1, 2, "R&D <3")
    )
    root = ET.fromstring(svg)  # noqa: S314 — our own generated SVG
    assert root.get("aria-label") == 'say "hi" & go'
    assert [span.text for span in root.iter(f"{SVG}tspan")] == ["A & B", "x < y", "R&D <3"]


def test_write_creates_every_diagram(tmp_path: Path) -> None:
    written = doc_diagrams.write(tmp_path)
    assert [p.name for p in written] == list(doc_diagrams.DIAGRAMS)
    for path in written:
        assert path.parent == tmp_path / "docs" / "concepts" / "assets"
        assert path.read_text(encoding="utf-8") == RENDERED[path.name]


@pytest.mark.parametrize(
    ("page", "diagram"),
    [
        ("README.md", "docs/concepts/assets/nexus-stack-in-one-picture.svg"),
        ("docs/concepts/index.md", "./assets/nexus-stack-in-one-picture.svg"),
        ("docs/concepts/architecture.md", "./assets/three-planes.svg"),
        ("docs/concepts/lifecycle.md", "./assets/lifecycle.svg"),
        ("docs/concepts/security-model.md", "./assets/request-path.svg"),
    ],
)
def test_each_diagram_is_embedded_where_it_belongs(page: str, diagram: str) -> None:
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    embeds = re.findall(r"!\[([^\]]+)\]\(" + re.escape(diagram) + r"\)", text)
    assert len(embeds) == 1, f"{page} should embed {diagram} exactly once, as a markdown image"
    assert len(embeds[0]) > 30, "alt text should describe the picture, not name the file"

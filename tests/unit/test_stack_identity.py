"""The Control Plane header's stack identity — `STACK_LABEL` / `STACK_ACCENT`.

Two Nexus-Stack panels are otherwise pixel-identical, one of whose buttons
is Teardown. Issue #841: the badge alone did not register, because the rest
of the header still said *Nexus Stack, in green* — so the whole header now
routes its brand colour through one variable and the `h1` names the stack.

These tests read the real source rather than a build, because the failure
they guard is a source-level regression: one hardcoded green re-introduced
into `Header.astro` silently drops out of the accent and a labelled panel
goes back to looking like every other one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CONTROL_PLANE = Path(__file__).resolve().parents[2] / "control-plane"
HEADER = CONTROL_PLANE / "src" / "components" / "Header.astro"
IDENTITY = CONTROL_PLANE / "src" / "lib" / "stack-identity.ts"

# The brand green, in the two notations the codebase uses for it.
BRAND_HEX = re.compile(r"#00ff88", re.IGNORECASE)
BRAND_RGBA = re.compile(r"rgba\(\s*0\s*,\s*255\s*,\s*136", re.IGNORECASE)


def _header() -> str:
    return HEADER.read_text(encoding="utf-8")


def _header_code() -> str:
    """`Header.astro` with `/* … */` comments removed.

    The rule below is about declarations, not prose: the comment explaining
    *why* `color-mix` replaced `rgba(0, 255, 136, …)` legitimately contains
    the literal it forbids, and a substring scan cannot tell the two apart.
    Caught by this test on its first run, against its own documentation.
    """
    return re.sub(r"/\*.*?\*/", "", _header(), flags=re.S)


def test_header_hardcodes_no_brand_green() -> None:
    """Every brand colour in the header goes through `--header-accent`.

    A literal `#00ff88` or `rgba(0, 255, 136, …)` here is invisible in the
    default panel — it renders exactly like the variable — and only shows
    up as a stray green element on a stack that sets STACK_ACCENT. That is
    the worst shape for a defect: correct in the configuration everyone
    develops against, wrong in the one it exists for.
    """
    src = _header_code()
    assert not BRAND_HEX.search(src), "Header.astro hardcodes #00ff88; use var(--header-accent)"
    assert not BRAND_RGBA.search(src), (
        "Header.astro hardcodes rgba(0, 255, 136, …); use "
        "color-mix(in srgb, var(--header-accent) N%, transparent)"
    )


def test_header_accent_falls_back_to_the_panel_accent() -> None:
    """With STACK_ACCENT unset the header must look exactly as before.

    The fallback is a single declaration; without it, an unlabelled panel
    resolves `--header-accent` to nothing and loses its heading colour
    entirely. Asserted on the source because it is one line that a refactor
    can drop while every other rule still reads correctly.
    """
    assert re.search(r"--header-accent:\s*var\(--accent\)", _header()), (
        "header must declare `--header-accent: var(--accent)` as the fallback"
    )


def test_the_heading_carries_the_stack_label() -> None:
    """The largest text on the page names the machine.

    This is the whole point of #841: a badge below a 2.5rem green heading
    loses to the heading. If the `h1` goes back to a bare literal, the
    accent work still renders but the panel stops *saying* which stack it
    is, which is the part an operator actually reads.
    """
    src = _header()
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", src, re.S)
    assert h1, "Header.astro has no <h1>"
    assert "stackLabel" in h1.group(1), (
        "the <h1> must render stackLabel when set — found: " + h1.group(1).strip()
    )


def test_the_tagline_keeps_the_product_name_when_a_label_takes_the_heading() -> None:
    """`Nexus Stack` moves down rather than disappearing.

    Without this the product name is nowhere on a labelled panel, which
    trades one identification problem for another.
    """
    src = _header()
    tagline = re.search(r'<p class="tagline"[^>]*>(.*?)</p>', src, re.S)
    assert tagline, "Header.astro has no .tagline"
    assert "Nexus Stack" in tagline.group(1), (
        "the tagline must carry 'Nexus Stack' when the heading is a label"
    )


@pytest.mark.parametrize(
    "value",
    [
        "#a855f7",
        "#fff",
        "#ff8800aa",
        "orange",
        "rebeccapurple",
    ],
)
def test_accent_pattern_admits_real_colours(value: str) -> None:
    """The colours an operator would plausibly type must survive validation."""
    assert _accent_pattern().fullmatch(value), f"{value} should be accepted"


@pytest.mark.parametrize(
    "value",
    [
        "#fffff",  # 5 digits is not a CSS colour
        "#fffffff",  # nor 7
        "red; background: url(x)",  # the injection this guards
        "var(--accent)",
        "",
        "rgb(1,2,3)",
    ],
)
def test_accent_pattern_rejects_everything_else(value: str) -> None:
    """The accent is interpolated into a style attribute, so it is constrained.

    `--header-accent` now cascades to the whole header rather than to one
    badge, which raises the cost of a bad value from a mis-coloured pill to
    a mis-coloured block — and the cost of an *unvalidated* one to a
    stylesheet an operator can write into every page. The pattern is
    unchanged by #841; this pins it so the widened blast radius cannot
    quietly outlive it.
    """
    assert not _accent_pattern().fullmatch(value), f"{value} should be rejected"


def _accent_pattern() -> re.Pattern[str]:
    """Read ACCENT_PATTERN out of the TypeScript rather than restating it.

    A copy here would pass while the real pattern drifted — the exact
    failure these tests exist to prevent.
    """
    src = IDENTITY.read_text(encoding="utf-8")
    m = re.search(r"const ACCENT_PATTERN = /\^(.+)\$/;", src)
    assert m, "ACCENT_PATTERN not found in stack-identity.ts"
    return re.compile(m.group(1))

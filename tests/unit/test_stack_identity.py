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
    """With STACK_ACCENT unset, every colour resolves to its previous value.

    The fallback is a single declaration; without it, an unlabelled panel
    resolves `--header-accent` to nothing and loses its heading colour
    entirely. Asserted on the source because it is one line that a refactor
    can drop while every other rule still reads correctly.

    Stated as *colours* deliberately, not as "looks exactly as before": the
    glows and the active-nav tint now go through `color-mix`, which a browser
    without support drops rather than approximates, leaving the header
    correctly coloured but flat. That baseline is Chrome 111, Safari 16.2 and
    Firefox 113 — all 2023 — for a panel behind Cloudflare Access, so the
    trade was accepted rather than papered over with `rgba()` fallbacks that
    would themselves be hardcoded greens on a recoloured panel.
    """
    assert re.search(r"--header-accent:\s*var\(--accent\)", _header()), (
        "header must declare `--header-accent: var(--accent)` as the fallback"
    )


def test_the_accent_requires_a_label() -> None:
    """`STACK_ACCENT` alone must change nothing.

    #841 states it plainly: with `STACK_LABEL` unset, nothing changes
    anywhere. Before that issue the property held for free — the only
    element carrying the accent sat inside the label's own conditional — so
    nothing tested it. Moving the accent up to `<header>` silently removed
    that guarantee and let an operator recolour a panel that still has no
    name on it, which is a stack that looks different for no stated reason:
    worse than one that looks the same.
    """
    # Comment-stripped: the comment above the tag names `<header>` in prose,
    # and a first-match scan would read the prose instead of the element.
    # Caught here on the first run, exactly as the brand-green guard was.
    header_tag = re.search(r"<header([^>]*)>", _header_code())
    assert header_tag, "Header.astro has no <header> tag"
    attrs = header_tag.group(1)
    assert "stackAccent" in attrs, "the <header> must carry the accent"
    assert "stackLabel" in attrs, (
        "the accent must be gated on stackLabel too — found: " + attrs.strip()
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


def test_the_validator_combines_both_halves_case_insensitively() -> None:
    """The hex test and the allowlist must both be consulted, and folded.

    Asserted on the shape of the export because the Python helper above
    cannot see it: that helper reads the two halves and joins them itself,
    so a TypeScript change to the *join* is invisible to every value-based
    test. Both such changes were tried and both passed, which is why this
    exists.

    `.toLowerCase()` is load-bearing rather than tidy: CSS keywords are
    case-insensitive, so `ORANGE` is a colour an operator may reasonably
    type, and without the fold it would be silently dropped.
    """
    src = IDENTITY.read_text(encoding="utf-8")
    export = re.search(r"export const stackAccent[^;]+;", src, re.S)
    assert export, "stackAccent export not found in stack-identity.ts"
    body = export.group(0)
    assert "HEX_PATTERN.test(rawAccent)" in body, "the hex half must be consulted"
    assert "NAMED_COLOURS.has(rawAccent.toLowerCase())" in body, (
        "the allowlist must be consulted, case-folded — found: " + " ".join(body.split())
    )


@pytest.mark.parametrize(
    "value",
    [
        "#a855f7",
        "#fff",
        "#ff8800aa",
        "orange",
        "rebeccapurple",  # CSS Color 4 added this one after the CSS3 147
        "ORANGE",  # CSS keywords are case-insensitive
        "DarkSlateGray",
    ],
)
def test_accent_pattern_admits_real_colours(value: str) -> None:
    """The colours an operator would plausibly type must survive validation."""
    assert _accepts_accent(value), f"{value} should be accepted"


@pytest.mark.parametrize(
    "value",
    [
        "#fffff",  # 5 digits is not a CSS colour
        "#fffffff",  # nor 7
        "red; background: url(x)",  # the injection this guards
        "var(--accent)",
        "",
        "rgb(1,2,3)",
        # Shape-valid words that are not colours. A bare /[a-z]{3,20}/ let
        # these through, and the cost is not a wrong colour: CSS drops every
        # declaration that reads an unrecognised custom property, so the
        # header ends up with no colour at all.
        "foobar",
        "notacolor",
        # Valid CSS, still not a colour an accent may be. `transparent` is
        # the expensive one — it erases heading, glow, tagline, nav link and
        # the masked logo at once, on the one stack that asked to stand out.
        "transparent",
        "currentcolor",
        "inherit",
        "unset",
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
    assert not _accepts_accent(value), f"{value} should be rejected"


def _accepts_accent(value: str) -> bool:
    """Apply the validator's *data* — the hex regex and the colour set —
    both read out of the TypeScript rather than restated here.

    What this helper cannot check is how the two are combined, because it
    combines them itself in Python. Mutation testing caught exactly that:
    reverting the allowlist to a bare shape test, and dropping the
    `.toLowerCase()`, both left every test below passing. The combination is
    therefore pinned separately and structurally, by
    `test_the_validator_combines_both_halves_case_insensitively`.
    """
    src = IDENTITY.read_text(encoding="utf-8")

    m = re.search(r"const HEX_PATTERN = /\^(.+)\$/;", src)
    assert m, "HEX_PATTERN not found in stack-identity.ts"
    if re.compile(m.group(1)).fullmatch(value):
        return True

    block = re.search(r"const NAMED_COLOURS = new Set\(\[(.*?)\]\);", src, re.S)
    assert block, "NAMED_COLOURS not found in stack-identity.ts"
    names = set(re.findall(r"'([a-z]+)'", block.group(1)))
    assert len(names) == 148, f"expected 148 CSS named colours, parsed {len(names)}"
    return value.lower() in names

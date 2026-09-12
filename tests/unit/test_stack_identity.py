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
LAYOUT = CONTROL_PLANE / "src" / "layouts" / "Layout.astro"
GLOBAL_CSS = CONTROL_PLANE / "src" / "styles" / "global.css"
SRC = CONTROL_PLANE / "src"

# The brand green, in the two notations the codebase uses for it.
BRAND_HEX = re.compile(r"#00ff88", re.IGNORECASE)
BRAND_RGBA = re.compile(r"rgba\(\s*0\s*,\s*255\s*,\s*136", re.IGNORECASE)


def _header() -> str:
    return HEADER.read_text(encoding="utf-8")


def _code(path: Path) -> str:
    """Any source file with `/* … */` and `{/* … */}` comments removed.

    Every rule here is about declarations, not prose — and three separate
    guards in this file tripped on their own documentation before it existed.
    """
    return re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)


def _header_code() -> str:
    """`Header.astro` with `/* … */` comments removed.

    The rule below is about declarations, not prose: the comment explaining
    *why* `color-mix` replaced `rgba(0, 255, 136, …)` legitimately contains
    the literal it forbids, and a substring scan cannot tell the two apart.
    Caught by this test on its first run, against its own documentation.
    """
    return re.sub(r"/\*.*?\*/", "", _header(), flags=re.S)


def test_header_hardcodes_no_brand_green() -> None:
    """Every brand colour in the header goes through `--accent`.

    A literal `#00ff88` or `rgba(0, 255, 136, …)` here is invisible in the
    default panel — it renders exactly like the variable — and only shows
    up as a stray green element on a stack that sets STACK_ACCENT. That is
    the worst shape for a defect: correct in the configuration everyone
    develops against, wrong in the one it exists for.
    """
    src = _header_code()
    assert not BRAND_HEX.search(src), "Header.astro hardcodes #00ff88; use var(--accent)"
    assert not BRAND_RGBA.search(src), (
        "Header.astro hardcodes rgba(0, 255, 136, …); use "
        "color-mix(in srgb, var(--accent) N%, transparent)"
    )


def test_the_accent_override_lands_on_the_document_root() -> None:
    """Part A moved the override from the header onto `<html>`.

    That single placement is what makes every `var(--accent)` on every page
    follow the stack accent. On `<header>` it reached one component; on
    `:root` it reaches the panel, which is the whole point of part A. The
    local `--header-accent` indirection is gone with it — a variable pointing
    at a variable, once the root one is the thing being overridden.
    """
    html_tag = re.search(r"<html([^>]*)>", _code(LAYOUT))
    assert html_tag, "Layout.astro has no <html> tag"
    attrs = html_tag.group(1)
    assert "--accent:" in attrs, "the accent override must land on <html> — found: " + attrs.strip()


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
    # Comment-stripped: comments near the tag name it in prose, and a
    # first-match scan would read the prose instead of the element. Caught
    # on the first run, twice, in two different files.
    html_tag = re.search(r"<html([^>]*)>", _code(LAYOUT))
    assert html_tag, "Layout.astro has no <html> tag"
    attrs = html_tag.group(1)
    assert "stackAccent" in attrs, "the <html> element must carry the accent"
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


# Rules whose green means "this is fine", not "this is Nexus Stack". Each
# one was read individually before being listed: every entry has an --error
# or --warning sibling in the same block, which is what makes it a status
# colour rather than the brand.
STATUS_RULES = {
    ".run-progress.is-success",
    ".is-success .rp-glyph",
    ".is-success .rp-fill",
    ":global(.rp-done .rp-mark)",
    ".category-stats :global(.count-running)",
    ".status-dot.deployed",
    ".status-text.deployed",
    ".databricks-last-sync.status-success",
    ".enabled",
    ":global(.history-item .status.success)",
    ":global(.category-card-stats .running)",
    ".stack-status-dot.status-running",
    ".toast.success",
}


def test_status_colours_never_follow_the_stack_accent() -> None:
    """A healthy stack is green whatever the accent is.

    This is what part A of #841 is actually for. Recolouring the brand is the
    visible half; separating it from status is the half that keeps the panel
    honest. A violet "deployed" dot in a set whose siblings are `--error` red
    and `--warning` amber does not read as a themed success — it reads as a
    state nobody can name, and the one moment an operator most needs the
    palette to be literal is while looking at a Teardown button.

    Every rule below was read before being listed; each has an `--error` or
    `--warning` sibling in its own block.
    """
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".astro", ".css"} or not path.is_file():
            continue
        selector = ""
        for lineno, line in enumerate(_code(path).splitlines(), 1):
            match = re.match(r"^\s*([.#:@a-zA-Z][^{}/\n]*?)\s*\{", line)
            if match:
                selector = match.group(1).strip()
            if selector in STATUS_RULES and "var(--accent)" in line:
                rel = path.relative_to(CONTROL_PLANE)
                offenders.append(f"{rel}:{lineno} {selector}")
    assert not offenders, (
        "status colours must use var(--status-ok), not the brand accent: " + "; ".join(offenders)
    )


def test_the_status_token_is_defined_independently_of_the_accent() -> None:
    """`--status-ok` must not be an alias for `--accent`.

    Defining it as `var(--accent)` would satisfy every other test here while
    quietly re-coupling the two: a stack accent would recolour success again,
    and the separation would exist only in the names. The two are the same
    green today, which is exactly why this needs asserting — nothing visible
    changes when the link is restored.
    """
    css = _code(GLOBAL_CSS)
    decl = re.search(r"--status-ok:\s*([^;]+);", css)
    assert decl, "global.css must define --status-ok"
    value = decl.group(1).strip()
    assert "var(" not in value, (
        f"--status-ok must be a literal colour, not derived from another token — found: {value}"
    )


def test_the_panel_hardcodes_no_brand_green_anywhere() -> None:
    """Part B cleaned the header; part A extends the rule to the whole panel.

    A literal green left behind renders identically in the default panel and
    only shows up as a stray element on a stack that sets an accent — correct
    in the configuration everyone develops against, wrong in the one it
    exists for. The two token definitions in `global.css` are the exception,
    because they are what every other site now points at.
    """
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".astro", ".css"} or not path.is_file():
            continue
        for lineno, line in enumerate(_code(path).splitlines(), 1):
            if "--accent:" in line or "--status-ok:" in line:
                continue  # the definitions themselves
            if BRAND_HEX.search(line) or BRAND_RGBA.search(line):
                offenders.append(f"{path.relative_to(CONTROL_PLANE)}:{lineno}")
    assert not offenders, "hardcoded brand green outside the token definitions: " + ", ".join(
        offenders
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


def _logo_rule() -> str:
    """Just the body of the `.logo` CSS rule.

    Every assertion about the logo has to be scoped to it. Scanning the whole
    file passes as soon as *any* rule carries the declaration — so an
    `aspect-ratio` added to an unrelated selector would satisfy the guard
    while the masked logo collapses to zero height, which is the precise
    failure that guard exists for. Raised in review on #843.
    """
    rule = re.search(r"\.logo\s*\{([^}]*)\}", _header_code(), re.S)
    assert rule, "Header.astro has no .logo rule"
    return rule.group(1)


def test_the_logo_is_masked_rather_than_drawn() -> None:
    """The logo takes the accent, and its asset exists.

    A masked box is filled with `--accent` instead of showing a
    coloured raster, which is what lets the logo recolour with the rest of
    the header. Both halves are asserted because they fail differently: a
    missing declaration leaves a solid rectangle, a missing file leaves an
    invisible one, and neither breaks the build.
    """
    rule = _logo_rule()
    assert re.search(r"-webkit-mask:\s*url\(/nexus-logo-mask\.png\)", rule), (
        "the logo must be painted through a mask, not drawn as an image"
    )
    assert re.search(r"background-color:\s*var\(--accent\)", rule), (
        "the masked box must be filled with the accent"
    )
    assert (CONTROL_PLANE / "public" / "nexus-logo-mask.png").is_file(), (
        "control-plane/public/nexus-logo-mask.png is missing"
    )


def test_the_masked_logo_declares_its_own_aspect_ratio() -> None:
    """Without `aspect-ratio` the logo collapses to nothing.

    An `<img>` carries the intrinsic size of its file; a masked `<div>` has
    none, so a box with a width and no ratio computes to zero height and the
    logo silently disappears. The page still builds, every test that reads
    the markup still passes, and the header just has a gap where the logo
    was — which is exactly the kind of failure worth one assertion.
    """
    assert re.search(r"aspect-ratio:\s*\d+\s*/\s*\d+", _logo_rule()), (
        ".logo must declare an aspect-ratio; a masked div has no intrinsic size"
    )


def test_the_mask_builder_clamps_the_background_to_transparent() -> None:
    """A brightness floor, or the mask carries a veil instead of a silhouette.

    Without one, a "black" ground that is really (1, 1, 1) to (3, 3, 3) maps
    to alpha 1-3 rather than 0. Measured on the Nexus logo before the floor
    existed: 41.8% of the mask sat at alpha 1-5 and only 4.8% was genuinely
    transparent. At 2% opacity that is nearly invisible by itself — but
    `filter: drop-shadow()` reads the alpha channel, so it glows the *box*
    rather than the artwork. Raised in review on #843.

    This asserts the script's shape, not the asset's pixels: checking the
    PNG would mean adding Pillow to CI for one file that changes about never,
    and the realistic regression is someone simplifying the script, not
    someone hand-editing the mask.
    """
    src = (Path(__file__).resolve().parents[2] / "scripts" / "build-logo-mask.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"^GROUND_AT\s*=\s*\d+", src, re.M), (
        "build-logo-mask.py must define a GROUND_AT brightness floor"
    )
    assert "v <= GROUND_AT" in src, "the floor must actually be applied to the alpha ramp"
    assert re.search(r"\(v - GROUND_AT\)", src), (
        "the ramp between floor and solid must be rescaled, not just clipped, "
        "or anti-aliased edges stair-step"
    )


def test_no_reference_survives_to_the_removed_raster() -> None:
    """`nexus-logo-green.png` is gone from the tree; nothing may still ask for it.

    It lives on in git history — that is how the mask can be regenerated —
    but a stale reference in the shipped panel is a 404 on every page load,
    and a 404 for a background image is invisible in the console noise of a
    working page.
    """
    stale = []
    for path in CONTROL_PLANE.rglob("*"):
        if not path.is_file() or "node_modules" in path.parts or "dist" in path.parts:
            continue
        if path.suffix not in {".astro", ".ts", ".js", ".css", ".html", ".json"}:
            continue
        if "nexus-logo-green" in path.read_text(encoding="utf-8", errors="ignore"):
            stale.append(str(path.relative_to(CONTROL_PLANE)))
    assert not stale, f"still reference the removed raster: {stale}"


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

    `--accent` now cascades to the whole panel rather than to one badge,
    which raises the cost of a bad value from a mis-coloured pill to a
    mis-coloured application — and the cost of an *unvalidated* one to a
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

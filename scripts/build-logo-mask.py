#!/usr/bin/env python3
"""Turn a bright-on-dark logo raster into a CSS alpha mask.

The Control Plane header paints its logo by filling a box with
`--header-accent` and masking it, rather than drawing a coloured image.
That is what lets a labelled stack recolour the logo along with everything
else (#841) — the alternative, `filter: hue-rotate()`, ties the result to
the source hue and falls apart on accents far from the original green.

The input must be **bright artwork on a dark ground**: alpha is derived
from per-pixel `max(r, g, b)`, normalised so the artwork's own brightness
reaches full opacity. `nexus-logo-green.png` qualified — its green sat at
(6, 247, 130) against a ~(1, 1, 1) ground, with a fully opaque alpha
channel that made a straight alpha mask impossible.

That source is no longer in the working tree; it was replaced by the mask
this script produced. It remains in git history, so this script stays
runnable against it:

    git show <commit>:control-plane/public/nexus-logo-green.png > /tmp/logo.png
    uv run --with pillow scripts/build-logo-mask.py /tmp/logo.png out.png

Its real use, though, is a *future* logo. Point it at the new artwork.

Usage:
    uv run --with pillow scripts/build-logo-mask.py <input.png> <output.png> [width]
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the dependency is not a project one
    sys.exit("Pillow is required: uv run --with pillow scripts/build-logo-mask.py …")

# Twice the header's 360px display width, so the mask stays crisp on a
# 2x display without carrying resolution nothing renders.
DEFAULT_WIDTH = 720

# Pixels at or above this share of full brightness are treated as solid
# artwork. Below it, alpha scales linearly, which keeps anti-aliased edges
# smooth instead of stair-stepping them.
SOLID_AT = 247


def build_mask(src_path: Path, dst_path: Path, width: int = DEFAULT_WIDTH) -> tuple[int, int]:
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    pixels = src.load()

    alpha = Image.new("L", (w, h))
    ap = alpha.load()
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            v = max(r, g, b)
            ap[x, y] = 255 if v >= SOLID_AT else v * 255 // SOLID_AT

    # White everywhere: the colour is irrelevant to a mask, and white keeps
    # the file legible if someone opens it expecting a picture.
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    out.putalpha(alpha)
    out.thumbnail((width, width * h // w), Image.LANCZOS)
    out.save(dst_path, optimize=True)

    return src_path.stat().st_size, dst_path.stat().st_size


def main() -> int:
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_WIDTH

    before, after = build_mask(src, dst, width)
    print(f"  {src}  {before / 1024 / 1024:.2f} MB")
    print(f"  {dst}  {after / 1024:.1f} KB  ({before / after:.0f}x smaller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

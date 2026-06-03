#!/usr/bin/env python3
"""Render every SVG in this directory to a high-resolution PNG.

Uses cairosvg with a fixed output width that preserves each SVG's
intrinsic aspect ratio (viewBox-derived). Font references that aren't
installed locally (Space Grotesk, Inter, JetBrains Mono) fall back to
the platform's system-ui face -- the layout stays faithful, the
typography becomes whatever the OS provides.
"""
from pathlib import Path
import cairosvg

# Target raster width in pixels. 2400 px gives a crisp ~150 ppi figure
# at the on-poster physical size (each SVG occupies roughly 16 cm wide).
TARGET_WIDTH_PX = 2400

HERE = Path(__file__).parent

svgs = sorted(HERE.glob("*.svg"))
if not svgs:
    raise SystemExit("No SVGs found in " + str(HERE))

for svg_path in svgs:
    out = svg_path.with_suffix(".png")
    print(f"  {svg_path.name:32s} -> {out.name}")
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(out),
        output_width=TARGET_WIDTH_PX,
    )

print(f"\nRendered {len(svgs)} PNG(s) at width={TARGET_WIDTH_PX}px into {HERE}")

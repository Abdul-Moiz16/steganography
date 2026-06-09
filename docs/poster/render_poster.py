#!/usr/bin/env python3
"""Render docs/poster/poster.html to a print-faithful A0 portrait PDF.

Uses Playwright + headless Chromium so Google Fonts and modern CSS
features (custom-properties, grid, aspect-ratio, etc) all render
identically to a desktop browser. Output is a single-page A0 portrait
PDF at docs/poster/poster.pdf -- and a matching ~2400 px PNG preview
for quick eyeballing without opening the PDF.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
HTML_PATH = HERE / "poster.html"
PDF_PATH = HERE / "poster.pdf"
PNG_PREVIEW_PATH = HERE / "poster_preview.png"


def render() -> None:
    if not HTML_PATH.exists():
        raise SystemExit(f"missing {HTML_PATH}")

    url = HTML_PATH.absolute().as_uri()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 2400, "height": 3394},  # roughly A0 portrait at ~72 dpi
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle")
        # Give web fonts and any layout settle a moment
        page.wait_for_timeout(800)

        # Print-to-PDF at A0 portrait (841 x 1189 mm).
        page.pdf(
            path=str(PDF_PATH),
            width="841mm",
            height="1189mm",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        print(f"  pdf  -> {PDF_PATH.relative_to(HERE.parent.parent)}")

        # Quick raster preview for at-a-glance review.
        page.screenshot(
            path=str(PNG_PREVIEW_PATH),
            full_page=True,
            type="png",
        )
        print(f"  png  -> {PNG_PREVIEW_PATH.relative_to(HERE.parent.parent)}")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    render()

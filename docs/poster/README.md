# Poster

A0 portrait poster for the project's poster workshop. Authored in HTML/CSS
so it can be regenerated reproducibly, recolour-themed in one place, and
exported to a print-ready PDF.

## Files

| File | Purpose |
|---|---|
| `poster.html` | The poster itself. Open in any modern browser (Chrome, Arc, Safari, Firefox). |
| `qr_repo.png` | QR code linking to the project's GitLab repository. Regenerate with `build_qr.sh`. |
| `build_qr.sh` | One-liner: regenerates `qr_repo.png` from the canonical repo URL. |
| `HPC Group 1 Poster.png` | The reference poster from a prior project, kept here for scale reference (A0 portrait, scientific-conference style). |

## Viewing

Just open `poster.html` in a browser. It is laid out at native A0 dimensions
(841 mm wide x 1189 mm tall) using CSS `mm` units, so on-screen it will
appear physically huge unless you zoom out (Cmd/Ctrl + minus a few times).

## Exporting to print-ready PDF

The poster is intentionally print-first. Two recommended paths:

### Option 1: Browser print-to-PDF (simplest)

1. Open `poster.html` in **Google Chrome**, **Arc**, or any Chromium-based
   browser (Safari's print engine also works but is slightly less faithful
   on web fonts).
2. `Cmd+P` (macOS) / `Ctrl+P` (Win/Linux).
3. **Destination:** Save as PDF.
4. **Paper size:** A0 (or "Custom" 841x1189 mm if A0 is unavailable).
5. **Margins:** None.
6. **Scale:** Default / 100%.
7. **Background graphics:** ON. (Critical -- otherwise the dark-blue brand
   band, the hero block, and the "So what?" card will all render white.)
8. Click "Save".

### Option 2: Headless Chromium (reproducible from CLI)

If you have Chrome / Chromium installed, the following one-liner produces
the same PDF without a UI step:

```bash
# Adjust the Chrome path for your OS:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu \
  --no-pdf-header-footer \
  --print-to-pdf-no-header \
  --print-to-pdf=poster.pdf \
  "file://$(pwd)/poster.html"
```

(On a Mac without Chrome, install via `brew install --cask google-chrome`,
or use Arc's underlying Chromium binary which is buried under
`~/Library/Application Support/Arc/User Data/...`.)

## Regenerating the QR code

If the repo URL changes (e.g. the repo is mirrored to GitHub for the
public release), regenerate the QR code:

```bash
bash docs/poster/build_qr.sh
```

Or directly:

```bash
venv312/bin/python -c "
import qrcode
url = 'https://gitlab.maastrichtuniversity.nl/m2-2_group02/m2-2_steganography'
qrcode.make(url, box_size=20, border=2).save('docs/poster/qr_repo.png')
"
```

## Editing the design

All colour, typography, and layout are driven by CSS at the top of
`poster.html`. The brand palette matches the paper:

| Token | Hex | Use |
|---|---|---|
| `--um-dark`   | `#001C3D` | Brand bands, dark cards, body text |
| `--um-light`  | `#4A90C4` | Secondary accents, link-blue |
| `--um-orange` | `#E84E10` | Accent highlights, hero numbers, "real"-easier cells |
| `--um-gray`   | `#6B7280` | Captions, muted body text |
| `--paper-bg`  | `#FBF9F5` | Off-white page background |
| `--card-bg`   | `#FFFFFF` | Card background |
| `--rule`      | `#D8D2C5` | Hairline rules / card borders |

Figures are loaded by relative URL from `docs/report/figures/v4_paper/`
so the poster automatically reflects any figure regeneration done via
`scripts/figures/make_v4_paper_figures.py`.

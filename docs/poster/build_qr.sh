#!/usr/bin/env bash
# Regenerate the QR codes used by the poster.
# Two codes:
#   qr_repo.png  -> project GitLab repository (code + paper + data)
#   qr_demo.png  -> live web demo where viewers can encode a message into
#                   an image and watch the detectors respond.
# Edit the URLs below if either target moves.
set -euo pipefail

REPO_URL="https://gitlab.maastrichtuniversity.nl/m2-2_group02/m2-2_steganography"

# TODO: replace with the hosted /toolbox URL once the demo is deployed.
# Until then we point the demo QR at the toolbox source in the repo so the
# code is still scannable -- the call-to-action text on the poster should
# be adjusted accordingly if hosting is not in place by print time.
DEMO_URL="https://gitlab.maastrichtuniversity.nl/m2-2_group02/m2-2_steganography/-/tree/main/public"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY="${SCRIPT_DIR}/../../venv312/bin/python"
if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3)"
fi

"$PY" - <<PYEOF
import qrcode

targets = [
    ("$REPO_URL", "$SCRIPT_DIR/qr_repo.png"),
    ("$DEMO_URL", "$SCRIPT_DIR/qr_demo.png"),
]
for url, out in targets:
    img = qrcode.make(url, box_size=20, border=2)
    img.save(out)
    print(f"wrote {img.size[0]}x{img.size[1]} px QR to {out}")
    print(f"  -> {url}")
PYEOF

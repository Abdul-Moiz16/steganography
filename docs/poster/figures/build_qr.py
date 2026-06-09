#!/usr/bin/env python3
"""Generate the dossier-styled QR code for the poster.

Outputs a single SVG at docs/poster/figures/qr_repo.svg that the poster
can embed via <img>. The QR encodes the project's GitLab URL. The
appearance is dossier-themed: umdark navy modules on a transparent
background so the orange stamp frame around it shows through.
"""
from pathlib import Path

import qrcode
import qrcode.image.svg

URL = "https://gitlab.maastrichtuniversity.nl/m2-2_group02/m2-2_steganography"
OUT = Path(__file__).parent / "qr_repo.svg"


def main() -> None:
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=None,                            # auto-size to fit URL
        error_correction=qrcode.ERROR_CORRECT_M, # ~15% recovery, fine for indoor scan
        box_size=10,
        border=2,                                # quiet zone in modules
    )
    qr.add_data(URL)
    qr.make(fit=True)
    img = qr.make_image(image_factory=factory)
    img.save(str(OUT))

    # The qrcode library's SvgPathImage forces fill="#000000"; replace it
    # with our dossier navy so the QR matches the rest of the poster's
    # ink palette. Also strip the fixed width/height so the SVG scales
    # via the parent <img>'s CSS sizing.
    raw = OUT.read_text()
    raw = raw.replace('fill="#000000"', 'fill="#001C3D"')
    raw = raw.replace('width="41mm" height="41mm"',
                      'width="100%" height="100%"')
    OUT.write_text(raw)

    print(f"  qr  -> {OUT.relative_to(OUT.parent.parent.parent)}")
    print(f"  url: {URL}")


if __name__ == "__main__":
    main()

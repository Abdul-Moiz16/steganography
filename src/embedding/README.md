# `src/embedding` Guide

`embedding/` contains deferred implementation stubs for the final proposal.

## Mainline Functions

- `encrypt_payload_aes_256_cbc(payload, key, iv) -> bytes`
- `decrypt_payload_aes_256_cbc(ciphertext, key, iv) -> bytes`
- `embed_lsb(cover_image, payload_bytes, fill_rate, bit_depth=1) -> Image`
- `embed_dct_lsb_jpeg(cover_jpeg_bytes, payload_bytes, fill_rate, jpeg_quality=95) -> bytes`

## Locked Methodology

- spatial branch:
  - grayscale sequential row-major LSB replacement
  - main analysis uses `bit_depth=1`
- frequency branch:
  - JSteg-style DCT-LSB on non-zero quantized AC coefficients
  - JPEG quality locked to `95`
  - no re-quantization after coefficient edits

Each stub docstring names the exact paper to follow during implementation.

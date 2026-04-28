# `src/embedding` Guide

`embedding/` implements encryption and steganographic embedding for both branches.

## Functions

- `encrypt_payload_aes_256_cbc(payload, key, iv) -> bytes`
- `decrypt_payload_aes_256_cbc(ciphertext, key, iv) -> bytes`
- `embed_lsb(cover_image, payload_bytes, fill_rate, bit_depth=1) -> Image`
- `embed_dct_lsb_jpeg(cover_jpeg_bytes, payload_bytes, fill_rate, jpeg_quality=95) -> bytes`

## Methodology

- **Spatial branch**: grayscale sequential row-major LSB replacement (`bit_depth=1`)
- **Frequency branch**: JSteg-style DCT-LSB on non-zero quantized AC coefficients using `jpeglib`, JPEG quality locked to 95, no re-quantization after coefficient edits
- **Encryption**: AES-256-CBC with PKCS7 padding applied before embedding

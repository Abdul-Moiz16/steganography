from __future__ import annotations


def embed_dct_lsb_jpeg(
    cover_jpeg_bytes: bytes,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    jpeg_quality: int = 95,
) -> bytes:
    """Embed a payload into quantized JPEG coefficients with DCT-LSB replacement.

    Proposal alignment:
    - Reference specification: ``docs/proposals/proposal_updated_3.tex``,
      Section ``Chosen Approaches -> Embedding Methods``.
    - Exact literature anchors:
      - Westfeld and Pfitzmann, "Attacks on steganographic systems," 1999
        [westfeld1999chi] for the JSteg-style non-zero AC replacement rule.
      - Fridrich, Goljan, and Hogea, "New methodology for breaking
        steganographic techniques for JPEGs," 2003 [fridrich2003calib] for the
        JPEG coefficient/calibration framing used throughout the proposal.

    Intended implementation:
    - Parse ``cover_jpeg_bytes`` as a JPEG encoded at Q=95.
    - Access the quantized integer DCT coefficients directly, for example via
      ``jpegio`` as stated in the proposal.
    - Traverse 8x8 blocks in row-major order.
    - Within each block, skip the DC coefficient and any zero-valued AC
      coefficients.
    - Use the first ``fill_rate`` fraction of the remaining non-zero AC
      coefficients as embedding positions.
    - Replace the least significant bit of each selected coefficient with the
      payload bit, keeping the coefficient non-zero.
    - Re-entropy-code the modified quantized coefficients with the same JPEG
      quantization tables and without a second quantization pass.
    - Return JPEG bytes ready to be written directly to ``.jpg`` output.

    Inputs:
    - ``cover_jpeg_bytes``: source JPEG carrier bytes from the frequency branch.
    - ``payload_bytes``: payload bitstream to embed.
    - ``fill_rate``: fraction of eligible non-zero AC coefficients to modify
      (0.25, 0.50, 0.75 in the main study).
    - ``jpeg_quality``: expected source quality. Locked to 95 in the proposal.

    Output:
    - Encoded JPEG bytes for the stego image.
    """
    raise NotImplementedError("JPEG DCT-LSB embedding is not implemented yet.")

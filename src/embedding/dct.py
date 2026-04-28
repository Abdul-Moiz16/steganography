# Main worker: Daria
# Contributor: David (Template)

from __future__ import annotations
import os
import tempfile
import numpy as np


def _load_jpegio():
    try:
        import jpegio as jio
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "DCT embedding requires the optional 'jpegio' dependency. "
            "Install it before running DCT embedding or decoding."
        ) from exc
    return jio

def embed_dct_lsb_jpeg(
    cover_jpeg_bytes: bytes,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    jpeg_quality: int = 95,
) -> bytes:
    """Embed a payload into quantized JPEG coefficients with DCT-LSB replacement.

    Proposal alignment:
    - Reference specification: `docs/proposals/proposal_updated_3.tex`,
      Section `Chosen Approaches -> Embedding Methods`.
    - Exact literature anchors:
      - Westfeld and Pfitzmann, "Attacks on steganographic systems," 1999
        [westfeld1999chi] for the JSteg-style non-zero AC replacement rule.
      - Fridrich, Goljan, and Hogea, "New methodology for breaking
        steganographic techniques for JPEGs," 2003 [fridrich2003calib] for the
        JPEG coefficient/calibration framing used throughout the proposal.

    Intended implementation:
    - Parse `cover_jpeg_bytes` as a JPEG encoded at Q=95.
    - Access the quantized integer DCT coefficients directly, for example via
      `jpegio` as stated in the proposal.
    - Traverse 8x8 blocks in row-major order.
    - Within each block, skip the DC coefficient and any zero-valued AC
      coefficients.
    - Use the first `fill_rate` fraction of the remaining non-zero AC
      coefficients as embedding positions.
    - Replace the least significant bit of each selected coefficient with the
      payload bit, keeping the coefficient non-zero.
    - Re-entropy-code the modified quantized coefficients with the same JPEG
      quantization tables and without a second quantization pass.
    - Return JPEG bytes ready to be written directly to `.jpg` output.

    Inputs:
    - `cover_jpeg_bytes`: source JPEG carrier bytes from the frequency branch.
    - `payload_bytes`: payload bitstream to embed.
    - `fill_rate`: fraction of eligible non-zero AC coefficients to modify
      (0.25, 0.50, 0.75 in the main study).
    - `jpeg_quality`: expected source quality. Locked to 95 in the proposal.

    Output:
    - Encoded JPEG bytes for the stego image.
    """
    jio = _load_jpegio()
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_in:
        tmp_in.write(cover_jpeg_bytes)
        tmp_in_path = tmp_in.name
    try:
        jpeg_struct = jio.read(tmp_in_path)
    finally:
        os.unlink(tmp_in_path)
    payload_bits = np.unpackbits(np.frombuffer(payload_bytes, dtype=np.uint8))
    payload_bit_index = 0
    total_payload_bits = len(payload_bits)

    for channel_idx, coef_array in enumerate(jpeg_struct.coef_arrays):
        if channel_idx != 0:
            continue

        eligible_positions = eligible_positions_helper(coef_array)

        n_embed = int(len(eligible_positions) * fill_rate)
        embedding_positions = eligible_positions[:n_embed]

        if len(embedding_positions) < total_payload_bits:
            raise ValueError(
                f"Payload too large for the requested fill_rate. "
                f"Payload too large: {total_payload_bits} bits, "
                f"Available: {len(embedding_positions)} bits (at {fill_rate:.0%} fill rate). "
            )

        for pos in embedding_positions:
            if payload_bit_index >= total_payload_bits:
                break

            (block_row, block_col, i, j) = pos
            row = block_row * 8 + i
            col = block_col * 8 + j
            coef = coef_array[row, col]

            if coef > 0:
                new_coef = (coef & ~1) | payload_bits[payload_bit_index]
            else:
                new_coef = -((abs(coef) & ~1) | payload_bits[payload_bit_index])
            coef_array[row, col] = new_coef
            payload_bit_index += 1

    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_out:
        tmp_out_path = tmp_out.name
    try:
        jio.write(jpeg_struct, tmp_out_path)
        with open(tmp_out_path, 'rb') as f:
            return f.read()
    finally:
        os.unlink(tmp_out_path)

def decode_dct_lsb_jpeg(
    stego_jpeg_bytes: bytes,
    payload_length_bytes: int,
    fill_rate: float,
) -> bytes:
    jio = _load_jpegio()
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_in:
        tmp_in.write(stego_jpeg_bytes)
        tmp_in_path = tmp_in.name
    try:
        jpeg_struct = jio.read(tmp_in_path)
    finally:
        os.unlink(tmp_in_path)
    coef_array = jpeg_struct.coef_arrays[0]

    eligible_positions = eligible_positions_helper(coef_array)

    n_embed = int(len(eligible_positions) * fill_rate)
    embedding_positions = eligible_positions[:n_embed]

    total_payload_bits = payload_length_bytes * 8
    if len(embedding_positions) < total_payload_bits:
            raise ValueError(
                f"Payload too large for the requested fill_rate. "
                f"Payload too large: {total_payload_bits} bits, "
                f"Available: {len(embedding_positions)} bits (at {fill_rate:.0%} fill rate). "
            )

    extracted_bits = []
    for pos in embedding_positions:
        if len(extracted_bits) == total_payload_bits:
            break

        (block_row, block_col, i, j) = pos
        row = block_row * 8 + i
        col = block_col * 8 + j
        coef = coef_array[row, col]
        extracted_bits.append(abs(coef) & 1)

    extracted_bits_array = np.array(extracted_bits, dtype=np.uint8)
    payload_bytes = np.packbits(extracted_bits_array).tobytes()

    return payload_bytes

# Helper function
def eligible_positions_helper(coef_array: np.ndarray) -> list[tuple[int, int, int, int]]:
    h, w = coef_array.shape
    blocks_vert = h // 8
    blocks_horiz = w // 8

    eligible_positions = []
    for block_row in range(blocks_vert):
        for block_col in range(blocks_horiz):
            block = coef_array[block_row*8:(block_row+1)*8, block_col*8:(block_col+1)*8]
            for i in range(8):
                for j in range(8):
                    if i == 0 and j == 0:
                        continue
                    if block[i, j] != 0 and abs(block[i, j]) != 1:
                        eligible_positions.append((block_row, block_col, i, j))
    return eligible_positions

from __future__ import annotations

from PIL import Image


def embed_lsb(
    cover_image: Image.Image,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    bit_depth: int = 1,
) -> Image.Image:
    """Embed a payload with sequential grayscale LSB replacement.

    Proposal alignment:
    - Reference specification: ``docs/proposals/proposal_updated_3.tex``,
      Section ``Chosen Approaches -> Embedding Methods``.
    - Detector-facing assumptions to preserve: row-major traversal and direct
      LSB replacement, as discussed by Fridrich et al. for classical
      LSB steganalysis [fridrich2001lsb].

    Intended implementation:
    - Input ``cover_image`` must be a single-channel 8-bit grayscale image
      already standardized to 512x512 by ``src.data.images.standardize_image``.
    - Traverse pixels in row-major order.
    - Use exactly the first ``fill_rate`` fraction of available embedding
      positions.
    - Replace the least-significant ``bit_depth`` bit planes with payload bits.
      Main experiment rows use ``bit_depth=1`` only. ``bit_depth=2`` is
      reserved for the auxiliary ``BD-Sens`` condition described in the
      proposal and should not be mixed into the main RQ3 analysis.
    - Stop after the required number of payload bits has been written.
    - Return a new ``PIL.Image.Image`` without mutating ``cover_image``.

    Inputs:
    - ``cover_image``: in-memory grayscale cover image.
    - ``payload_bytes``: pseudo-random or AES-encrypted payload bitstream
      produced upstream.
    - ``fill_rate``: fraction of usable pixel positions to fill
      (0.25, 0.50, 0.75 in the main study).
    - ``bit_depth``: number of least significant bit planes to replace.

    Output:
    - A new grayscale stego image, still PNG-safe and the same size as the
      input image.

    Reference to follow for implementation:
    - J. Fridrich, M. Goljan, and R. Du, "Reliable detection of LSB
      steganography in color and grayscale images," IEEE Multimedia, 2001.
    """
    raise NotImplementedError("Sequential grayscale LSB embedding is not implemented yet.")

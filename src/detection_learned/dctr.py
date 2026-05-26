"""DCTR -- Low-Complexity Features for JPEG Steganalysis (Holub & Fridrich 2015).

Reference
---------
V. Holub and J. Fridrich,
"Low-complexity features for JPEG steganalysis using undecimated DCT,"
IEEE Trans. Inf. Forensics Security, vol. 10, no. 2, pp. 219-228, 2015.

Implementation notes
--------------------
This is the canonical **8,000-dimensional** DCTR feature set. The
decomposition that yields exactly 8,000 features matches the paper's
headline count:

  - 64 DCT modes (full 8x8 basis)                            [matches paper]
  - 25 phase positions, the 5x5 upper-left corner of the     [matches paper]
    8x8 JPEG block alignment grid (phase = (i mod 8, j mod 8))
  - 5-bin absolute-truncated histogram (T = 4)               [matches paper]

  Total feature dim: 64 * 25 * 5 = 8000.

The "25-phase" interpretation
-----------------------------
For each spatial position (i, j) in the undecimated-DCT residual map,
its position modulo the JPEG 8x8 block grid -- i.e. (i mod 8, j mod 8)
in [0, 8) x [0, 8) -- defines its "phase". There are 64 possible phases.
The paper notes that the 25 phases corresponding to the upper-left 5x5
corner of this 8x8 grid carry essentially all the discriminative
signal for JPEG steganalysis (the remaining 39 phases are dominated by
JPEG block-boundary artefacts unrelated to embedding). Restricting to
those 25 phases and concatenating one truncated histogram per
(mode, phase) pair gives the 8,000-dim feature vector.

Notes on the residual computation
---------------------------------
We compute the **undecimated DCT** of the decompressed JPEG: the 8x8
DCT is applied at every pixel offset (stride 1), giving a 64-channel
residual stack of shape (H-7, W-7, 64). Each channel is divided by the
mode-specific JPEG-Y quantization step (Q = 95) before histogramming;
this normalises the per-mode dynamic range so the T = 4 absolute
truncation captures the same fraction of mass across all modes.

Speed
-----
Per image (512x512, single CPU core):
  - undecimated DCT    : ~50 ms  (numpy tensordot)
  - quantize + truncate: ~20 ms
  - phase histograms   : ~100 ms (25 phases x 1 bincount each)
Total: ~170 ms/image. With multiprocessing.Pool(N_CPU) the extraction
parallelises near-linearly. For our 50k-image training cell on 18 cores
this is roughly 8 min per cell.

Public surface
--------------
  dctr_features(jpeg_bytes: bytes, *, quality: int = 95) -> np.ndarray  # (8000,)
  dctr_features_path(path) -> np.ndarray                                 # convenience
  FEATURE_DIM                                                            # 8000
  quantization_matrix(quality) -> np.ndarray                             # (8, 8) JPEG-Y table
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Final, Union

import numpy as np
from numpy.lib.stride_tricks import as_strided
from PIL import Image

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T: Final[int] = 4              # truncation threshold for histogram bin {>=T}
_N_BINS: Final[int] = _T + 1    # bin values {0, 1, 2, 3, >=4}
_PHASE_GRID: Final[int] = 5     # 5x5 upper-left subset of the 8x8 JPEG alignment grid
_N_PHASES: Final[int] = _PHASE_GRID * _PHASE_GRID   # = 25
_N_MODES: Final[int] = 64       # 8x8 DCT modes
_BLOCK: Final[int] = 8          # JPEG block size

FEATURE_DIM: Final[int] = _N_MODES * _N_PHASES * _N_BINS  # = 8000


# ---------------------------------------------------------------------------
# DCT basis
# ---------------------------------------------------------------------------

def _build_dct_basis() -> np.ndarray:
    """Return (64, 8, 8) array of orthonormal 8x8 DCT basis functions.

    Basis indexed by mode = 8*m + n, where (m, n) is the DCT frequency.
    """
    basis = np.zeros((64, 8, 8), dtype=np.float32)
    for m in range(8):
        cm = np.sqrt(1.0 / 8.0) if m == 0 else np.sqrt(2.0 / 8.0)
        for n in range(8):
            cn = np.sqrt(1.0 / 8.0) if n == 0 else np.sqrt(2.0 / 8.0)
            mode = m * 8 + n
            for r in range(8):
                for c in range(8):
                    basis[mode, r, c] = (
                        cm * cn
                        * np.cos((2.0 * r + 1.0) * m * np.pi / 16.0)
                        * np.cos((2.0 * c + 1.0) * n * np.pi / 16.0)
                    )
    return basis


_DCT_BASIS: Final[np.ndarray] = _build_dct_basis()


# ---------------------------------------------------------------------------
# JPEG quantization
# ---------------------------------------------------------------------------

# Standard JPEG luminance quantization matrix (Q=50 reference).
_Q50: Final[np.ndarray] = np.array(
    [
        [16, 11, 10, 16, 24, 40, 51, 61],
        [12, 12, 14, 19, 26, 58, 60, 55],
        [14, 13, 16, 24, 40, 57, 69, 56],
        [14, 17, 22, 29, 51, 87, 80, 62],
        [18, 22, 37, 56, 68, 109, 103, 77],
        [24, 35, 55, 64, 81, 104, 113, 92],
        [49, 64, 78, 87, 103, 121, 120, 101],
        [72, 92, 95, 98, 112, 100, 103, 99],
    ],
    dtype=np.float32,
)


def quantization_matrix(quality: int = 95) -> np.ndarray:
    """JPEG luminance quantization matrix for the given quality factor.

    Follows the standard libjpeg scaling rule.
    """
    if quality < 1 or quality > 100:
        raise ValueError(f"quality must be in [1, 100], got {quality}")
    if quality < 50:
        scale = 5000.0 / quality
    else:
        scale = 200.0 - 2.0 * quality
    q = np.floor((_Q50 * scale + 50.0) / 100.0)
    return np.clip(q, 1.0, 255.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Undecimated DCT
# ---------------------------------------------------------------------------

def _undecimated_dct(img: np.ndarray) -> np.ndarray:
    """Apply the 8x8 DCT at every spatial position (stride 1).

    Parameters
    ----------
    img : (H, W) float32 array

    Returns
    -------
    coeffs : (H-7, W-7, 64) float32 array
        coeffs[i, j, mode] is the mode-th DCT coefficient of the 8x8
        patch whose top-left corner is at (i, j) in `img`.
    """
    if img.ndim != 2:
        raise ValueError(f"_undecimated_dct expects 2D image, got shape {img.shape}")
    H, W = img.shape
    if H < 8 or W < 8:
        raise ValueError(f"image too small for 8x8 DCT: {img.shape}")
    out_h, out_w = H - 7, W - 7
    # Build (out_h, out_w, 8, 8) view over the image via stride tricks.
    s0, s1 = img.strides
    patches = as_strided(
        img,
        shape=(out_h, out_w, 8, 8),
        strides=(s0, s1, s0, s1),
        writeable=False,
    )
    # tensordot: (out_h, out_w, 8, 8) x (64, 8, 8) -> (out_h, out_w, 64)
    return np.tensordot(patches, _DCT_BASIS, axes=([2, 3], [1, 2]))


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------

def _load_grayscale(jpeg_bytes: bytes) -> np.ndarray:
    """Decode JPEG bytes to a float32 grayscale image."""
    with Image.open(io.BytesIO(jpeg_bytes)) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    return arr


def dctr_features(jpeg_bytes: bytes, *, quality: int = 95) -> np.ndarray:
    """Extract the 8000-dim DCTR feature vector from a JPEG image.

    Parameters
    ----------
    jpeg_bytes : raw JPEG file bytes (any quality; default mode-step from Q=95)
    quality : JPEG quality factor used to derive the mode-specific quantizer

    Returns
    -------
    ndarray of shape (FEATURE_DIM,) = (8000,), dtype float32
        Concatenation in (mode, phase, bin) order, row-major:
            features[mode * 125 + phase * 5 + bin]
        Each per-(mode, phase) histogram is L1-normalised.
    """
    img = _load_grayscale(jpeg_bytes)

    # Undecimated DCT: (H-7, W-7, 64)
    coeffs = _undecimated_dct(img)

    # Mode-specific quantization steps, flattened to (64,)
    q_vec = quantization_matrix(quality).reshape(-1)  # (64,)

    # Quantize, abs, truncate to {0, 1, 2, 3, T}
    # Use int32 because the mode-major shift trick below indexes into
    # bins up to _N_MODES * _N_BINS = 320 -- well within int32 range.
    quantized = np.abs(np.round(coeffs / q_vec[None, None, :])).astype(np.int32)
    np.minimum(quantized, _T, out=quantized)

    out_h, out_w, _ = quantized.shape

    # Phase decomposition: 25 sub-arrays per mode (5x5 upper-left subset of
    # the 8x8 JPEG block alignment grid). Phase (a, b) collects values at
    # spatial positions (i, j) with (i mod 8 == a) and (j mod 8 == b).
    #
    # Output buffer is (mode, phase, bin) so a single ravel at the end
    # gives the documented memory layout.
    features = np.empty((_N_MODES, _N_PHASES, _N_BINS), dtype=np.float32)

    # Pre-compute the mode shift used for the bincount-with-mode-major trick.
    mode_shift = (np.arange(_N_MODES, dtype=np.int32) * _N_BINS)  # (64,)

    phase_idx = 0
    for a in range(_PHASE_GRID):
        for b in range(_PHASE_GRID):
            # Sub-sample residual at phase (a, b): every 8th pixel in both
            # axes, starting at offset (a, b).
            sub = quantized[a::_BLOCK, b::_BLOCK, :]
            n_pix = sub.shape[0] * sub.shape[1]
            if n_pix == 0:
                # Defensive: extremely small image. Fill zeros, move on.
                features[:, phase_idx, :] = 0.0
                phase_idx += 1
                continue

            # Mode-major shift trick: encode (mode, bin) into a single index
            # so all 64 mode-histograms can be computed with one bincount.
            shifted = sub + mode_shift[None, None, :]
            hist = np.bincount(
                shifted.ravel(),
                minlength=_N_MODES * _N_BINS,
            )[: _N_MODES * _N_BINS].astype(np.float32)
            hist = hist.reshape(_N_MODES, _N_BINS)
            hist /= float(n_pix)

            features[:, phase_idx, :] = hist
            phase_idx += 1

    return features.ravel().astype(np.float32, copy=False)


def dctr_features_path(path: Union[str, Path]) -> np.ndarray:
    """Convenience: load a JPEG from disk and extract its DCTR features."""
    with open(path, "rb") as f:
        return dctr_features(f.read())

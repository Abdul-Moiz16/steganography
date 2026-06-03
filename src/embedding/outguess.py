"""OutGuess (Provos 2001) DCT-domain steganographic embedding.

Reference
---------
N. Provos, "Defending against statistical steganalysis," in *Proc. 10th
USENIX Security Symposium*, 2001, pp. 323--336.

Algorithm
---------
OutGuess improves on JSteg's sequential LSB embedding by:

1.  **Pseudo-random embedding path** -- a PRNG-seeded permutation of
    the eligible non-zero AC coefficient list, so consecutive embedded
    bits are not in adjacent coefficients.  Defeats sequential-window
    chi^2 attacks.

2.  **Histogram-preserving correction** -- after embedding, identifies
    coefficients whose value changed due to LSB-flipping and flips
    additional coefficients in a reserved Q-set to restore the global
    histogram of each value-pair (2k, 2k+1) to its pre-embedding count.
    Defeats Westfeld's chi^2 test on the GLOBAL histogram by construction.

The Q-set is the second portion of the shuffled eligible list, held
back from embedding for use in the correction step.  P-set / Q-set
boundary is at the same fill-rate convention as JSteg: at fill_rate r,
M = floor(r * N_eligible) coefficients form the P-set; the remaining
(1 - r) * N_eligible form the Q-set candidate pool.

Why this matters for our paper
------------------------------
OutGuess was the historical motivation for Fridrich et al.'s
calibration-chi^2 (2003): the global Westfeld chi^2 returns AUC ~ 0.5
on OutGuess stegos by construction (the histogram-correction step
restores the very statistic chi^2 measures).  The tile-local chi^2
variant we propose (Section VII.A) operates on per-tile histograms;
the histogram-correction step in OutGuess uses a GLOBAL correction
reserve and therefore cannot guarantee per-tile histogram preservation.
A finding that tile-local chi^2 retains detection power on OutGuess
where global chi^2 fails would establish tile-local as the natural
extension of Westfeld's test to histogram-preserving embeddings.

Failure mode
------------
If the Q-set has insufficient candidates of a particular coefficient
value to fully undo the histogram shift, the correction step issues a
warning and proceeds with partial correction.  In practice this is
rare at fill rates <= 0.5 on natural-image covers (a P-set of M
coefficients requires at most M/2 corrections in expectation, and the
Q-set has N_eligible - M >= M candidates available).  Tracked via an
optional ``return_diagnostics`` flag for audit.
"""
from __future__ import annotations

import random
import warnings

import numpy as np

from src.embedding.dct import eligible_positions_helper
from src.embedding.jpeg_dct import (
    luminance_coefficients,
    read_dct_jpeg,
    write_dct_jpeg,
)


def _pair_partner(v: int) -> int:
    """Return the LSB-partner of a coefficient value.

    Each non-zero AC coefficient with |v| >= 2 has a pair-partner whose
    absolute value differs by 1 and shares the same sign.  LSB-replace
    embedding moves values within these pairs (e.g. 2 <-> 3, -4 <-> -5).
    """
    if v == 0:
        return 0
    sign = 1 if v > 0 else -1
    return sign * (abs(v) ^ 1)


def embed_outguess_jpeg(
    cover_jpeg_bytes: bytes,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    jpeg_quality: int = 95,
    seed: int = 0,
    return_diagnostics: bool = False,
):
    """Embed ``payload_bytes`` into ``cover_jpeg_bytes`` via OutGuess.

    Parameters
    ----------
    cover_jpeg_bytes :
        JPEG bytes to embed into.  Same parsing path as
        :func:`src.embedding.dct.embed_dct_lsb_jpeg`.
    payload_bytes :
        Payload to embed.  Length must satisfy
        ``len(payload_bytes) * 8 <= floor(fill_rate * N_eligible)`` where
        N_eligible is the count of non-zero AC coefficients with |v| >= 2.
    fill_rate :
        Fraction of eligible coefficients reserved for the P-set
        (embedding); the remaining fraction is the Q-set candidate pool
        used for histogram correction.
    jpeg_quality :
        Unused for parity with :func:`embed_dct_lsb_jpeg`; the output
        JPEG reuses the cover's quantization tables, not this value.
        Accepted for API symmetry only.
    seed :
        PRNG seed for the embedding-path shuffle.  Same (cover, payload,
        seed) input -> bit-identical stego.
    return_diagnostics :
        If True, return ``(stego_bytes, diag)`` where diag contains
        ``n_p`` (P-set size), ``n_q`` (Q-set size), ``n_payload_bits``,
        ``n_corrections_applied``, ``n_corrections_failed``.  Useful for
        verifying the histogram-preservation claim.

    Returns
    -------
    Stego JPEG bytes (and optional diagnostics dict).
    """
    if not 0.0 < fill_rate <= 1.0:
        raise ValueError(f"fill_rate must be in (0, 1], got {fill_rate}")

    jpeg_struct = read_dct_jpeg(cover_jpeg_bytes)
    coef_array = luminance_coefficients(jpeg_struct)

    eligible_positions = eligible_positions_helper(coef_array)
    n_eligible = len(eligible_positions)
    if n_eligible == 0:
        raise ValueError("Cover has no eligible non-zero AC coefficients with |v| >= 2.")

    # PRNG-seeded shuffle for the embedding path
    rng = random.Random(seed)
    shuffled = list(eligible_positions)
    rng.shuffle(shuffled)

    # P/Q split
    n_p = int(n_eligible * fill_rate)
    p_set = shuffled[:n_p]
    q_set = shuffled[n_p:]

    payload_bits = np.unpackbits(np.frombuffer(payload_bytes, dtype=np.uint8))
    total_payload_bits = int(len(payload_bits))
    if total_payload_bits > n_p:
        raise ValueError(
            f"Payload too large for OutGuess at fill_rate {fill_rate}: "
            f"{total_payload_bits} bits requested, P-set capacity {n_p}"
        )

    # --- Stage 1: LSB-replace embedding on P-set positions --------------
    # Record (pos, original_value) so we can compute the per-value histogram
    # delta caused by embedding without re-scanning the whole image.
    touched: list[tuple] = []  # (pos, original_v, new_v)
    for i, pos in enumerate(p_set[:total_payload_bits]):
        orig = int(coef_array[pos])
        bit = int(payload_bits[i])
        if orig > 0:
            new = (orig & ~1) | bit
        else:
            new = -((-orig & ~1) | bit)
        # Defensive: skip if LSB-replace would zero out the coef (shouldn't
        # happen given the |v| >= 2 eligibility, but bail rather than emit
        # an invalid coefficient).
        if new == 0:
            continue
        if new != orig:
            coef_array[pos] = new
        touched.append((pos, orig, new))

    # --- Stage 2: histogram correction via Q-set flips ------------------
    # Compute the per-value delta caused by the embedding.  LSB replacement
    # can only move values within a (2k, 2k+1) pair (or the negative
    # analogue), so all deltas come in pair sums that equal zero.
    pair_deltas: dict[int, int] = {}
    for _pos, orig, new in touched:
        if orig == new:
            continue
        pair_deltas[orig] = pair_deltas.get(orig, 0) - 1
        pair_deltas[new] = pair_deltas.get(new, 0) + 1

    # Index Q-set positions by current value, so we can find candidates to flip.
    q_by_value: dict[int, list] = {}
    for pos in q_set:
        v = int(coef_array[pos])
        if v != 0:
            q_by_value.setdefault(v, []).append(pos)

    n_corrections_applied = 0
    n_corrections_failed = 0

    # We act on each positive-delta value only -- the partner's negative
    # delta is resolved automatically (a flip of the over-represented v
    # to its partner restores both counts to their cover values).
    for v, delta in list(pair_deltas.items()):
        if delta <= 0:
            continue
        partner = _pair_partner(v)
        if partner == 0:
            # v has |v|==1; shouldn't be possible given eligibility filter.
            n_corrections_failed += delta
            continue
        available = q_by_value.get(v, [])
        # Take from the END of the list so we don't disturb the iteration
        # order if we happen to re-enter this loop in the future.
        n_flip = min(delta, len(available))
        for _ in range(n_flip):
            pos = available.pop()
            coef_array[pos] = partner
            q_by_value.setdefault(partner, []).append(pos)
        n_corrections_applied += n_flip
        if n_flip < delta:
            n_corrections_failed += (delta - n_flip)

    if n_corrections_failed > 0:
        warnings.warn(
            f"OutGuess: {n_corrections_failed} histogram corrections failed "
            f"(insufficient Q-set candidates); stego is not perfectly "
            f"histogram-preserving on those value pairs."
        )

    stego_bytes = write_dct_jpeg(jpeg_struct)
    if return_diagnostics:
        return stego_bytes, {
            "n_eligible": n_eligible,
            "n_p": n_p,
            "n_q": len(q_set),
            "n_payload_bits": total_payload_bits,
            "n_corrections_applied": n_corrections_applied,
            "n_corrections_failed": n_corrections_failed,
        }
    return stego_bytes


def outguess_payload_capacity_bytes(cover_jpeg_bytes: bytes, fill_rate: float) -> int:
    """Return the byte capacity of OutGuess at the given fill rate.

    Matches the JSteg convention: payload bits = floor(fill_rate * N_eligible),
    so the byte capacity is payload_bits // 8.  The Q-set overhead is
    invisible to this number; the caller passes a payload no larger than
    this and OutGuess silently reserves the remaining (1-fill_rate) of
    coefficients for histogram correction.
    """
    jpeg_struct = read_dct_jpeg(cover_jpeg_bytes)
    coef_array = luminance_coefficients(jpeg_struct)
    n_eligible = len(eligible_positions_helper(coef_array))
    return (int(n_eligible * fill_rate)) // 8

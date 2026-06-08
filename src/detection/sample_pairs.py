#Authors: Nico Muller-Spätz and David Wicker
"""Sample Pairs steganalysis detector.

Estimates the embedding rate of sequential LSB replacement by analysing
trace multiset statistics over adjacent pixel pairs.

Reference
---------
- S. Dumitrescu, X. Wu, and Z. Wang,
  "Detection of LSB steganography via sample pair analysis,"
  IEEE Trans. Signal Process., vol. 51, no. 7, pp. 1995--2007, 2003.
"""

from __future__ import annotations

import math
import numpy as np
from PIL import Image


def sample_pairs_score(image: Image.Image) -> float:
    """Return the Sample Pairs steganalysis score for one grayscale image.

    Vectorised implementation: builds the full (u, v) pair vectors for
    horizontal and vertical neighbours, then derives every accumulator
    with a single NumPy reduction. Bit-equivalent to the Python double
    loop it replaces; ~50x faster on 512x512 images.
    """

    gray = image.convert("L")
    pixels = np.array(gray, dtype=np.int32)
    height, width = pixels.shape

    j = 30  # threshold defined in paper

    # Horizontal pairs (u = pixels[r, c], v = pixels[r, c+1]) for every c < width-1.
    u_h = pixels[:, :-1].ravel()
    v_h = pixels[:, 1:].ravel()
    # Vertical pairs (u = pixels[r, c], v = pixels[r+1, c]) for every r < height-1.
    u_v = pixels[:-1, :].ravel()
    v_v = pixels[1:, :].ravel()

    u = np.concatenate([u_h, u_v])
    v = np.concatenate([v_h, v_v])

    diff = np.abs(u - v)
    upper_diff = np.abs((u >> 1) - (v >> 1))

    d_0 = int(np.sum(diff == 0))
    d_2j2 = int(np.sum(diff == 2 * (j + 1)))
    c_0 = int(np.sum(upper_diff == 0))
    c_j1 = int(np.sum(upper_diff == j + 1))

    # Odd-difference subset (1, 3, ..., 2j+1=61). Within each such pair
    # exactly one element is even and one is odd; figure out which is which.
    odd_mask = ((diff & 1) == 1) & (diff <= 2 * j + 1)
    u_odd = u[odd_mask]
    v_odd = v[odd_mask]
    u_is_even = (u_odd & 1) == 0
    even_vals = np.where(u_is_even, u_odd, v_odd)
    odd_vals = np.where(u_is_even, v_odd, u_odd)

    sum_x = int(np.sum(even_vals > odd_vals))
    sum_y = int(np.sum(even_vals < odd_vals))

    # a*q^2 + b*q + c = 0
    #   a = 2*C_0 - C_{j+1}
    #   b = -(2*D_0 - D_{2(j+1)} + 2c)
    #   c = sum_y - sum_x
    c_coeff = float(sum_y - sum_x)
    a_coeff = float(2 * c_0 - c_j1)
    b_coeff = -(2.0 * d_0 - d_2j2 + 2.0 * c_coeff)

    if a_coeff == 0:
        if b_coeff == 0:
            return 0.0
        q = -c_coeff / b_coeff
        return max(0.0, min(2.0 * q, 1.0))

    discriminant = b_coeff * b_coeff - 4.0 * a_coeff * c_coeff

    if discriminant < 0:
        return 0.0

    sqrt_d = math.sqrt(discriminant)

    q1 = (-b_coeff - sqrt_d) / (2.0 * a_coeff)
    q2 = (-b_coeff + sqrt_d) / (2.0 * a_coeff)

    # q = p/2 so p = 2*q.
    p1 = 2.0 * q1
    p2 = 2.0 * q2

    candidates = []
    if -0.1 <= p1 <= 1.1:
        candidates.append(p1)
    if -0.1 <= p2 <= 1.1:
        candidates.append(p2)

    if not candidates:
        return 0.0

    p_est = min(candidates)  # smaller p is proven to be the better approximation
    return max(0.0, min(p_est, 1.0))

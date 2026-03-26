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
    """Return the Sample Pairs steganalysis score for one grayscale image."""

    gray = image.convert("L")
    pixels = np.array(gray, dtype=np.int32)
    height, width = pixels.shape

    j = 30  # threshold defined in paper

    sum_x = 0
    sum_y = 0
    d_0 = 0
    c_0 = 0
    c_j1 = 0
    d_2j2 = 0

    for r in range(height):
        for c in range(width):

            neighbors = []
            if c + 1 < width:  # right neighbour
                neighbors.append(pixels[r, c + 1])
            if r + 1 < height:  # bottom neighbour
                neighbors.append(pixels[r + 1, c])

            for v in neighbors:
                u = pixels[r, c]
                diff = abs(u - v)
                upper_diff = abs((u >> 1) - (v >> 1))

                if diff == 0:  # same pixel
                    d_0 += 1

                if diff == 2 * (j + 1):  # difference 62
                    d_2j2 += 1

                if upper_diff == 0:  # upper 7 bits equal
                    c_0 += 1

                if upper_diff == j + 1:  # upper 7 bits different by 31
                    c_j1 += 1

                if diff % 2 == 1 and diff <= 2 * j + 1:  # for odd numbers <= 62

                    if u % 2 == 0:  # determine which value is equal
                        even_val = u
                        odd_val = v
                    else:
                        even_val = v
                        odd_val = u

                    if even_val > odd_val:
                        sum_x += 1  # add to x if even component is larger
                    else:
                        sum_y += 1  # add to y if odd component is larger

    #   a·q² + b·q + c = 0

    #   a = 2·C₀ − C₃₁
    #   b = −(2·D₀ − D₆₂ + 2·c)
    #   c = ΣY − ΣX

    c_coeff = float(sum_y - sum_x)
    a_coeff = float(2 * c_0 - c_j1)
    b_coeff = -(2.0 * d_0 - d_2j2 + 2.0 * c_coeff)

    if a_coeff == 0:  # exception if a == 0
        if b_coeff == 0:  # if b is also 0
            return 0.0  # not solvable
        q = -c_coeff / b_coeff
        return max(0.0, min(2.0 * q, 1.0))  # clip between 0,1

    discriminant = b_coeff * b_coeff - 4.0 * a_coeff * c_coeff  # tells us whether equation is solvable

    if discriminant < 0:
        return 0.0  # most likely clean

    sqrt_d = math.sqrt(discriminant)

    q1 = (-b_coeff - sqrt_d) / (2.0 * a_coeff)
    q2 = (-b_coeff + sqrt_d) / (2.0 * a_coeff)

    # q = p/2 so p = 2·q.
    p1 = 2.0 * q1
    p2 = 2.0 * q2

    # only including estimated in the right range including rounding error
    candidates = []
    if -0.1 <= p1 <= 1.1:
        candidates.append(p1)
    if -0.1 <= p2 <= 1.1:
        candidates.append(p2)

    if not candidates:
        return 0.0  # most likely clean

    p_est = min(candidates)  # smaller p is proven to be the better approximation
    return max(0.0, min(p_est, 1.0))  # clip p to 0,1

if __name__ == "__main__":
    files = ["test.png", "output_keyed.png", "output_sequential.png"]

    for filename in files:
        image = Image.open(filename)
        score = sample_pairs_score(image)

        print(f"{filename}: score = {score:.6f}", end="  →  ")

        if score < 0.02:
            print("most likely clean")
        elif score < 0.10:
            print("small embedding")
        else:
            print(f"embedding recognized({score * 100:.1f}%)")


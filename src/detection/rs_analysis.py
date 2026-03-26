"""RS analysis steganalysis detector.

Detects sequential LSB replacement by partitioning pixel groups into
Regular and Singular classes under flipping masks.

Reference
---------
- J. Fridrich, M. Goljan, and R. Du,
  "Reliable detection of LSB steganography in color and grayscale images,"
  IEEE Multimedia, vol. 8, no. 4, pp. 22--28, 2001.
"""

from __future__ import annotations

from PIL import Image
import numpy as np


def rs_analysis_score(image: Image.Image) -> float:
  """Return an RS-analysis score for one grayscale spatial image.

  Intended implementation:
  - Follow Fridrich, Goljan, and Du [fridrich2001lsb].
  - Work on the same grayscale row-major spatial branch used by
    ``embed_lsb``.
  - Partition pixels into the group structure required by the paper, apply
    the regular/singular flipping masks, and derive one scalar detection
    score where larger values indicate stronger evidence of LSB replacement.
  """

  channels = get_color_blocks(image)

  best_score = 0.0
  for blocks in channels:

    # RS is testing in groups of four
    # we need to find the remainder for math sake and remove it from the block
    # we are losing at most 3 pixels, which are insignificant to the whole pixel space for the analysis
    remainder = len(blocks) % 4
    if remainder:
      blocks = blocks[:-remainder]
    blocks = blocks.reshape(-1, 4)

    # the original scores
    f = calculate_smoothness(blocks)

    blocks_m = blocks.copy()
    blocks_minus_m = blocks.copy()

    # applying the positive mask [0, 1, 1, 0]
    blocks_m[:, 1] = blocks_m[:, 1] ^ 1
    blocks_m[:, 2] = blocks_m[:, 2] ^ 1

    # applying the negative mask
    # depending on if the LSB is even or odd, increase/decrease by 1
    blocks_minus_m[:, 1] = np.where(blocks_minus_m[:, 1] % 2 == 0, blocks_minus_m[:, 1] - 1, blocks_minus_m[:, 1] + 1)
    blocks_minus_m[:, 2] = np.where(blocks_minus_m[:, 2] % 2 == 0, blocks_minus_m[:, 2] - 1, blocks_minus_m[:, 2] + 1)

    # calculate scores
    scores_m = calculate_smoothness(blocks_m)
    scores_minus_m = calculate_smoothness(blocks_minus_m)

    # calculate the Regular and Singular groups for positive mask
    R_m = np.sum(scores_m > f)
    S_m = np.sum(scores_m < f)

    # calculate the Regular and Singular groups for negative mask
    R_minus_m = np.sum(scores_minus_m > f)
    S_minus_m = np.sum(scores_minus_m < f)

    # calculate the final RS score for this channel
    rs = abs(R_m - R_minus_m) + abs(S_m - S_minus_m)
    best_score = max(best_score, rs)

  # return the highest channel score to catch anomalies
  return float(best_score)

# helper for rs analysis, calculates the smoothness between the pixels, aka f score
# return a 1D array of scores for each color block
def calculate_smoothness(block: np.ndarray) -> np.ndarray:

  right_side = block[:, 1:]
  left_side = block[:, :-1]
  diff = np.abs(right_side-left_side)

  return np.sum(diff, axis=1)

# helper method for rs_analysis_score to get pixel blocks per channel
# returns a list of arrays: one per channel (1 for grayscale, 3 for RGB)
def get_color_blocks(image: Image.Image) -> list[np.ndarray]:
    # support both grayscale and RGB input
    if image.mode == "L":
        pixels = np.array(image, dtype=np.int16)
        height, width = pixels.shape
        safe_height = height - (height % 2)
        safe_width = width - (width % 2)

        gray = []
        for y in range(0, safe_height, 2):
            for x in range(0, safe_width, 2):
                block = pixels[y:y+2, x:x+2]
                gray.append(block.flatten())

        return [np.array(gray)]

    image = image.convert("RGB")
    pixels = np.array(image, dtype = np.int16)
    height, width, channels = pixels.shape

    safe_height = height - (height %2) #2 is the block size
    safe_width = width - (width%2)

    red = []
    green = []
    blue = []

    for y in range(0, safe_height, 2):
        for x in range(0, safe_width, 2):

            block = pixels[y:y+2, x:x+2]
            red.append(block[:,:,0].flatten())
            green.append(block[:,:,1].flatten())
            blue.append(block[:,:,2].flatten())

    return [np.array(red), np.array(green), np.array(blue)]

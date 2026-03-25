"""Re-exports all statistical steganalysis detectors.

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

  red_blocks, green_blocks, blue_blocks = get_color_blocks(image)

  # RS is testing in groups of four
  # we need to find the remainder for math sake and remove it from the block
  # we are losing at most 3 pixels, which are insignificant to the whole pixel space for the analysis
  red_remainder = len(red_blocks) % 4
  if red_remainder:                        
    red_blocks = red_blocks[:-red_remainder]
  red_blocks = red_blocks[:-red_remainder].reshape(-1, 4)

  green_remainder = len(green_blocks) % 4
  if green_remainder:                        
    green_blocks = green_blocks[:-green_remainder]
  green_blocks = green_blocks[:-green_remainder].reshape(-1, 4)

  blue_remainder = len(blue_blocks) % 4
  if blue_remainder:                        
    blue_blocks = blue_blocks[:-blue_remainder]
  blue_blocks = blue_blocks[:-blue_remainder].reshape(-1, 4)

# the original scores
  f_red = calculate_smoothness(red_blocks)
  f_green = calculate_smoothness(green_blocks)
  f_blue = calculate_smoothness(blue_blocks)

  red_m = red_blocks.copy()
  red_minus_m = red_blocks.copy()
  f_green_m = green_blocks.copy()
  f_green_minus_m = green_blocks.copy()
  f_blue_m = blue_blocks.copy()
  f_blue_minus_m = blue_blocks.copy()

# applying the positive mask [0, 1, 1, 0]
  red_m[:, 1] = red_m[:, 1] ^ 1
  red_m[:, 2] = red_m[:, 2] ^ 1

  f_green_m[:, 1] = f_green_m[:, 1] ^ 1
  f_green_m[:, 2] = f_green_m[:, 2] ^ 1

  f_blue_m[:, 1] = f_blue_m[:, 1] ^ 1
  f_blue_m[:, 2] = f_blue_m[:, 2] ^ 1

# applying the negative mask
# depending on if the LSB is even or odd, increase/decrease by 1
  red_minus_m[:, 1] = np.where(red_minus_m[:, 1] % 2 == 0, red_minus_m[:, 1] - 1, red_minus_m[:, 1] + 1)
  red_minus_m[:, 2] = np.where(red_minus_m[:, 2] % 2 == 0, red_minus_m[:, 2] - 1, red_minus_m[:, 2] + 1)

  f_green_minus_m[:, 1] = np.where(f_green_minus_m[:, 1] % 2 == 0, f_green_minus_m[:, 1] - 1, f_green_minus_m[:, 1] + 1)
  f_green_minus_m[:, 2] = np.where(f_green_minus_m[:, 2] % 2 == 0, f_green_minus_m[:, 2] - 1, f_green_minus_m[:, 2] + 1)

  f_blue_minus_m[:, 1] = np.where(f_blue_minus_m[:, 1] % 2 == 0, f_blue_minus_m[:, 1] - 1, f_blue_minus_m[:, 1] + 1)
  f_blue_minus_m[:, 2] = np.where(f_blue_minus_m[:, 2] % 2 == 0, f_blue_minus_m[:, 2] - 1, f_blue_minus_m[:, 2] + 1)

# calculate scores
  scores_red_m = calculate_smoothness(red_m)
  scores_red_minus_m = calculate_smoothness(red_minus_m)
  scores_green_m = calculate_smoothness(f_green_m)
  scores_green_minus_m = calculate_smoothness(f_green_minus_m)
  scores_blue_m = calculate_smoothness(f_blue_m)
  scores_blue_minus_m = calculate_smoothness(f_blue_minus_m)

# calculate the Regular and Signular groups for positivi mask
  R_red_m = np.sum(scores_red_m > f_red)
  S_red_m = np.sum(scores_red_m < f_red)

  R_green_m = np.sum(scores_green_m > f_green)
  S_green_m = np.sum(scores_green_m < f_green)

  R_blue_m = np.sum(scores_blue_m > f_blue)
  S_blue_m = np.sum(scores_blue_m < f_blue)

  # calculate the Regular and Signular groups for negative mask
  R_red_minus_m = np.sum(scores_red_minus_m > f_red)
  S_red_minus_m = np.sum(scores_red_minus_m < f_red)

  R_green_minus_m = np.sum(scores_green_minus_m > f_green)
  S_green_minus_m = np.sum(scores_green_minus_m < f_green)

  R_blue_minus_m= np.sum(scores_blue_minus_m > f_blue)
  S_blue_minus_m = np.sum(scores_blue_minus_m < f_blue)

# calculate the final RS score
  rs_red = abs(R_red_m - R_red_minus_m) + abs(S_red_m - S_red_minus_m)
  rs_green = abs(R_green_m - R_green_minus_m) + abs(S_green_m - S_green_minus_m)
  rs_blue = abs(R_blue_m - R_blue_minus_m) + abs(S_blue_m - S_blue_minus_m)

# return the highest channel score to catch anomalies
  return float(max(rs_red,rs_green,rs_blue))

# helper for rs analysis, calculates the smoothness between the pixels, aka f score
# return a 1D array of scores for each color block
def calculate_smoothness(block: np.ndarray) -> np.ndarray:

  right_side = block[:, 1:]
  left_side = block[:, :-1]
  diff = np.abs(right_side-left_side)

  return np.sum(diff, axis=1)

# helper method for rs_analysis_score to get all different pixel blocks per color
def get_color_blocks(image: Image.Image) -> np.ndarray:
    image = image.convert("RGB")
    pixels = np.array(image, dtype = np.int16)
    height, width, channgels = pixels.shape

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

    return np.array(red), np.array(green), np.array(blue)


def chi_square_spatial_score(image: Image.Image) -> float:
    """Return the classical chi-square LSB score for one grayscale image.

    Intended implementation:
    - Follow Westfeld and Pfitzmann [westfeld1999chi].
    - Build the pairs-of-values histogram over spatial intensity values
      ``(2k, 2k+1)``.
    - Compare the observed imbalance against the equalization expected under
      LSB replacement.
    - Return one scalar score with larger values meaning stronger stego
      evidence.
    """
    raise NotImplementedError("Spatial chi-square steganalysis is not implemented yet.")


def sample_pairs_score(image: Image.Image) -> float:
    """Return the Sample Pairs steganalysis score for one grayscale image.

    Intended implementation:
    - Follow Dumitrescu, Wu, and Wang [dumitrescu2003sp].
    - Compute the trace multiset statistics over pixel pairs in the row-major
      spatial image.
    - Derive the sample-pair estimate/statistic used to detect sequential
      LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of embedding.
    """
    raise NotImplementedError("Sample Pairs analysis is not implemented yet.")


def chi_square_dct_score(jpeg_bytes: bytes) -> float:
    """Return the DCT-domain chi-square score for one JPEG carrier/stego.

    Intended implementation:
    - Follow the JPEG/JSteg framing from Westfeld and Pfitzmann
      [westfeld1999chi].
    - Parse quantized DCT coefficients directly from the JPEG bitstream.
    - Exclude DC coefficients and operate on the non-zero AC coefficient value
      pairs relevant to DCT-LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of coefficient-LSB embedding.
    """
    raise NotImplementedError("DCT chi-square steganalysis is not implemented yet.")


def calibration_chi_square_score(jpeg_bytes: bytes, *, jpeg_quality: int = 95) -> float:
    """Return the calibration-based chi-square score for one JPEG image.

    Intended implementation:
    - Follow Fridrich, Goljan, and Hogea [fridrich2003calib].
    - Build a calibration reference by taking a non-block-aligned crop,
      recompressing it at the same quality level, and comparing the resulting
      coefficient histogram against the candidate image.
    - Keep the recompression quality aligned with the proposal's Q=95 setup.
    - Return one scalar score where larger values indicate stronger stego
      evidence.
    """
    raise NotImplementedError("Calibration chi-square steganalysis is not implemented yet.")

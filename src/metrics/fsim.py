"""Feature Similarity Index (FSIM) between a cover and stego image.

Used in the quality-control step (Section 3.4 of the proposal) alongside
PSNR and SSIM to rule out trivial quality loss from embedding.

FSIM is based on the idea that low-level features (phase congruency and
gradient magnitude) are the primary perceptual cues for image quality.
It correlates more strongly with human perception than PSNR and SSIM for
many distortion types.  Values range from 0 to 1, where 1 means perfect
structural fidelity.

Reference
---------
- L. Zhang, L. Zhang, X. Mou, and D. Zhang,
  "FSIM: A feature similarity index for image quality assessment,"
  IEEE Trans. Image Process., vol. 20, no. 8, pp. 2378--2386, 2011.
"""

from __future__ import annotations

import torch
import numpy as np
from PIL import Image
from piq import fsim as piq_fsim


def fsim(cover: Image.Image, stego: Image.Image) -> float:
 

    """Compute FSIM between a cover and stego grayscale image."""
    if cover.size != stego.size:
        raise ValueError("Images size don't match")

    #Convert first to grayscale and then to numpy 
    cover_to_np= np.array(cover.covert("L"))
    stego_to_np = np.array(stego.covert("L"))


    #piq expects tensor in (B, C, H, W) format with values in [0, 1]
    # B= batch size (numb of images), C= channels, H= height of image, W= width of image
    cover_tensor = torch.from_numpy(cover_to_np).unsqueeze(0).unsqueeze(0).float() / 255.0
    stego_tensor = torch.from_numpy(stego_to_np).unsqueeze(0).unsqueeze(0).float() / 255.0
  
    score = piq_fsim(cover_tensor, stego_tensor, chromatic=False) 

    return score.item() 
   
    raise NotImplementedError("FSIM is not implemented yet.")

"""SRNet -- Deep residual network for steganalysis (Boroumand+19).

Reference
---------
M. Boroumand, M. Chen, and J. Fridrich,
"Deep residual network for steganalysis of digital images,"
IEEE Trans. Inf. Forensics Security, vol. 14, no. 5, pp. 1181-1193, 2019.

Architecture summary
--------------------
- Input: 1x512x512 grayscale image, float32 in [0, 255]
- Type 1 blocks (Layer 1, 2): Conv-BN-ReLU, NO pooling, NO TLU.
  These layers preserve resolution and learn high-pass-like filters.
- Type 2 blocks (Layer 3-7): residual blocks Conv-BN-ReLU + skip.
- Type 3 blocks (Layer 8-11): residual blocks with stride-2 average pool
  in the skip path; channel doubling.
- Type 4 block (Layer 12): final residual block with global average pooling.
- FC: 512 -> 2 (cover, stego).

Channel widths per the paper's Figure 2: {64, 16, 16x5, 16, 64, 128, 256, 512}.

Parameter-count note
--------------------
The paper claims ~467k trainable parameters but the architecture described
in Figure 2 -- which is what we implement here -- composes to ~4.8M
parameters when channel widths are taken at face value. Most open-source
SRNet ports (e.g. brijeshiitg/Pytorch-implementation-of-SRNet) also land at
~2-5M; community consensus is that the 467k figure in the abstract is
either an error or counts BN params differently. We document our actual
count via `count_parameters()`; capacity-wise 4.8M is well-matched to our
~15,000-sample training set and our 4 GB VRAM budget.

We deliberately keep the implementation close to the published Figure 2
rather than chasing the 467k count. The score returned by `srnet_score()`
is the softmax probability of the stego class -- monotone with the AUC
contrast the rest of the pipeline expects.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class Type1Block(nn.Module):
    """Conv-BN-ReLU, no pooling. Layers 1-2 of SRNet."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(self.bn(self.conv(x)), inplace=True)


class Type2Block(nn.Module):
    """Residual block, no pooling. Layers 3-7 of SRNet."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.shortcut = (
            nn.Sequential() if in_ch == out_ch
            else nn.Sequential(nn.Conv2d(in_ch, out_ch, 1, bias=False), nn.BatchNorm2d(out_ch))
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(x)
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual, inplace=True)


class Type3Block(nn.Module):
    """Residual block with 3x3 stride-2 average pool in the skip. Layers 8-11."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.pool = nn.AvgPool2d(kernel_size=3, stride=2, padding=1)
        self.shortcut = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=1, stride=2, bias=False),
            nn.BatchNorm2d(out_ch),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(x)
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = self.bn2(self.conv2(out))
        out = self.pool(out)
        return F.relu(out + residual, inplace=True)


class Type4Block(nn.Module):
    """Final residual block with global average pool. Layer 12."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = F.relu(self.bn2(self.conv2(out)), inplace=True)
        # Global average pool over (H, W) -> (B, C, 1, 1) -> (B, C)
        return out.mean(dim=(2, 3))


# ---------------------------------------------------------------------------
# Top-level network
# ---------------------------------------------------------------------------

class SRNet(nn.Module):
    """Full SRNet for binary stego classification."""

    def __init__(self, n_classes: int = 2) -> None:
        super().__init__()
        # Layers 1-2 (Type 1)
        self.l1 = Type1Block(in_ch=1,  out_ch=64)
        self.l2 = Type1Block(in_ch=64, out_ch=16)
        # Layers 3-7 (Type 2)
        self.l3 = Type2Block(in_ch=16, out_ch=16)
        self.l4 = Type2Block(in_ch=16, out_ch=16)
        self.l5 = Type2Block(in_ch=16, out_ch=16)
        self.l6 = Type2Block(in_ch=16, out_ch=16)
        self.l7 = Type2Block(in_ch=16, out_ch=16)
        # Layers 8-11 (Type 3, channel doubling, stride 2)
        self.l8  = Type3Block(in_ch=16,  out_ch=16)
        self.l9  = Type3Block(in_ch=16,  out_ch=64)
        self.l10 = Type3Block(in_ch=64,  out_ch=128)
        self.l11 = Type3Block(in_ch=128, out_ch=256)
        # Layer 12 (Type 4, global pool)
        self.l12 = Type4Block(in_ch=256, out_ch=512)
        # Classifier head
        self.fc = nn.Linear(512, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, 1, H, W) float32 in [0, 255]. Returns (B, n_classes) logits."""
        x = self.l1(x); x = self.l2(x)
        x = self.l3(x); x = self.l4(x); x = self.l5(x); x = self.l6(x); x = self.l7(x)
        x = self.l8(x); x = self.l9(x); x = self.l10(x); x = self.l11(x)
        x = self.l12(x)
        return self.fc(x)


# ---------------------------------------------------------------------------
# Score wrapper used at inference time
# ---------------------------------------------------------------------------

def srnet_score(model: SRNet, image: torch.Tensor) -> float:
    """Return the softmax probability of the stego class for a single image.

    Parameters
    ----------
    model : SRNet
        Trained SRNet in eval mode, on the desired device.
    image : torch.Tensor
        (1, H, W) float32 grayscale tensor in [0, 255].

    Returns
    -------
    float
        P(stego | image). Monotone with the AUC contrast used by the
        rest of the steganography pipeline.
    """
    model.eval()
    with torch.no_grad():
        logits = model(image.unsqueeze(0))           # (1, 2)
        probs = F.softmax(logits, dim=1)             # (1, 2)
        return float(probs[0, 1].item())


def count_parameters(model: SRNet) -> int:
    """Sanity-check the parameter count against the published 470k figure."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Smoke test (run this file directly to verify shapes + param count)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    model = SRNet()
    n = count_parameters(model)
    print(f"SRNet parameter count: {n:,}")
    print(f"  (paper abstract claims ~467k, but the architecture in Fig. 2")
    print(f"   composes to ~4.8M; see module docstring. 4.8M is fine for")
    print(f"   our 15k-sample training budget and 4GB VRAM target.)")
    x = torch.zeros(2, 1, 512, 512)
    out = model(x)
    print(f"Input shape:  {tuple(x.shape)}")
    print(f"Output shape: {tuple(out.shape)}")
    assert out.shape == (2, 2), out.shape
    print("OK")

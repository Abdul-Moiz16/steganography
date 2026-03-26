from __future__ import annotations

"""Named experiment profiles for prototype and full-design runs.

Two profiles are defined:

``prototype``
    20 groups downloaded per run (3 sources each = 60 images per run),
    spatial LSB only, low fill rate only,
    plain + AES-256-CBC encryption — 6 conditions total.
    Used for rapid iteration and examiner-reproducible demonstration.

``full_design``
    500 groups downloaded per run (3 sources each = 1500 images per run),
    spatial LSB + DCT-LSB, all three fill rates,
    plain + AES-256-CBC encryption — 36 conditions total.
    Mirrors the full proposal_updated_3.tex experimental design.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunProfile:
    """Static specification for one named experiment profile."""

    name: str
    n_groups: int        # groups sampled per run
    pool_groups: int     # total groups in the download pool (>= n_groups)
    active_methods: tuple[str, ...]
    active_payload_levels: tuple[str, ...]
    description: str

    @property
    def n_conditions(self) -> int:
        """Number of conditions: sources(3) × methods × payload_levels × encryptions(2)."""
        return 3 * len(self.active_methods) * len(self.active_payload_levels) * 2

    def __str__(self) -> str:
        return (
            f"{self.name}: {self.n_groups} images | "
            f"methods={self.active_methods} | "
            f"payload_levels={self.active_payload_levels} | "
            f"{self.n_conditions} conditions"
        )


PROFILES: dict[str, RunProfile] = {
    "prototype": RunProfile(
        name="prototype",
        # 20 unique caption-linked groups downloaded per run across all three sources.
        # Per-run images = 20 groups × 3 sources = 60 images.
        # Real breakdown: ~12 COCO + ~8 Flickr30k per run.
        n_groups=20,
        pool_groups=20,
        active_methods=("lsb",),
        active_payload_levels=("low",),
        description=(
            "Prototype run: 20 groups downloaded per run; 20 groups × 3 sources = 60 images per run "
            "(real: ~12 COCO + ~8 Flickr30k / SDXL / FLUX), "
            "spatial LSB embedding only, low fill rate (0.25 bpp), "
            "plain + AES-256-CBC encryption. 6 conditions total."
        ),
    ),
    "full_design": RunProfile(
        name="full_design",
        # 500 unique groups per run shared across all three sources.
        # Pool: 500 groups (pool_groups=500 — pool equals per-run sample for full design).
        # Total images per run = 500 groups × 3 sources = 1500 images.
        # Real breakdown: 300 COCO + 200 Flickr30k.
        n_groups=500,
        pool_groups=500,
        active_methods=("lsb", "dct"),
        active_payload_levels=("low", "medium", "high"),
        description=(
            "Full design: 500 groups downloaded per run; 500 groups × 3 sources = 1500 images per run "
            "(real: 300 COCO + 200 Flickr30k / SDXL 1.0 / FLUX.1-schnell), "
            "spatial LSB + DCT-LSB embedding, all fill rates (0.25 / 0.50 / 0.75 bpp), "
            "plain + AES-256-CBC encryption. 36 conditions total."
        ),
    ),
}

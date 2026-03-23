from __future__ import annotations

"""Pipeline configuration locked to ``proposal_updated_3.tex``.

The final proposal fixes the repository to:
- 500 caption-linked groups
- grayscale 512x512 carriers
- branch-specific storage: PNG for spatial LSB, JPEG Q=95 for DCT-LSB
- main payload levels defined by fill rate (25/50/75%)
- classical statistical primary detectors

This file stores those experiment-wide constants in one place so the
manifests, runner, and docs stay in sync.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.common.contracts import PipelinePaths


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable configuration for the proposal-locked experiment pipeline."""

    project_root: Path
    image_size: tuple[int, int] = (512, 512)
    n_groups: int = 500
    split_seed: int = 42
    payload_seed: int = 42
    embed_seed: int = 42
    aes_key_id: str = "aes256cbc-v1"
    jpeg_quality: int = 95
    saturation_low_threshold: int = 10
    saturation_high_threshold: int = 245
    primary_lsb_bit_depth: int = 1
    auxiliary_bd_sens_bit_depth: int = 2
    include_bd_sens_auxiliary: bool = False
    payload_fill_rates: dict[str, float] = field(
        default_factory=lambda: {"low": 0.25, "medium": 0.50, "high": 0.75}
    )

    @property
    def paths(self) -> PipelinePaths:
        """Return canonical repository paths derived from ``project_root``."""
        return PipelinePaths.from_project_root(self.project_root)

    @property
    def pixels_per_image(self) -> int:
        """Return the total number of grayscale pixels per standardized image."""
        return self.image_size[0] * self.image_size[1]

    def spatial_payload_bits(self, payload_level: str, *, bit_depth: int | None = None) -> int:
        """Return the nominal spatial payload size in bits for one payload level.

        The proposal matches the three primary conditions by fill rate.
        For spatial LSB replacement, that becomes:
        - low:  0.25 bpp
        - medium: 0.50 bpp
        - high: 0.75 bpp

        ``BD-Sens`` is not part of the main manifest by default; callers can
        request it explicitly by passing ``bit_depth=2`` and a 75% fill level.
        """
        fill_rate = self.payload_fill_rates[payload_level]
        resolved_bit_depth = bit_depth or self.primary_lsb_bit_depth
        return int(self.pixels_per_image * fill_rate * resolved_bit_depth)

    @classmethod
    def from_project_root(cls, project_root: Path) -> "PipelineConfig":
        """Build config with defaults and a resolved absolute project root."""
        return cls(project_root=project_root.resolve())

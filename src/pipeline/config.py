#Author: David Wicker
from __future__ import annotations

"""Pipeline configuration locked to ``proposal_updated_3.tex``.

The final proposal fixes the repository to:
- 500 caption-linked groups (full design) / 60 groups (prototype)
- grayscale 512x512 carriers
- branch-specific storage: PNG for spatial LSB, JPEG Q=95 for DCT-LSB
- main payload levels defined by fill rate (25/50/75%)
- classical statistical primary detectors

``active_methods``, ``active_payload_levels``, ``active_encryption``,
and ``active_detectors`` narrow the experiment scope for a named profile
or interactive run without altering any locked constants.  When built
via ``from_project_root`` every active_* field defaults to the full
proposal set so existing code and tests remain unaffected.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.common.contracts import PipelinePaths


PAYLOAD_MODE_RANDOM = "random"
PAYLOAD_MODE_HARDCODED = "hardcoded"
PAYLOAD_MODES = (PAYLOAD_MODE_RANDOM, PAYLOAD_MODE_HARDCODED)
AES_CBC_BLOCK_BYTES = 16

# Detector registries (mirror src/detection/statistical.py).
SPATIAL_DETECTORS: tuple[str, ...] = ("rs", "chi_square_spatial", "sample_pairs")
DCT_DETECTORS: tuple[str, ...] = (
    "chi_square_dct",
    "calibration_chi_square",
    "chi_square_dct_tiled",
)
ALL_DETECTORS: tuple[str, ...] = SPATIAL_DETECTORS + DCT_DETECTORS

ALL_METHODS: tuple[str, ...] = ("lsb", "dct")
ALL_PAYLOAD_LEVELS: tuple[str, ...] = ("low", "medium", "high")
ALL_ENCRYPTIONS: tuple[str, ...] = ("plain", "encrypted")

# Minimum group counts. R1: DeLong variance becomes meaningless below ~5
# pairs. R2: confirmatory testing (Exp 1, Exp 2) needs at least 20 pairs to
# keep Holm-adjusted p-values interpretable. Both come from the proposal's
# statistical-protocol discussion.
MIN_N_GROUPS_RUN = 5
MIN_N_GROUPS_CONFIRMATORY = 20

# Locked JPEG quality from the proposal §3.2. Other values are accepted by
# validate() but trigger a warning.
PROPOSAL_JPEG_QUALITY = 95


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable configuration for the proposal-locked experiment pipeline."""

    project_root: Path
    image_size: tuple[int, int] = (512, 512)
    n_groups: int = 500
    split_seed: int = 42
    payload_seed: int = 42
    payload_mode: str = PAYLOAD_MODE_RANDOM
    hardcoded_payload_text: str | None = None
    embed_seed: int = 42
    aes_key_id: str = "aes256cbc-v1"
    jpeg_quality: int = PROPOSAL_JPEG_QUALITY
    saturation_low_threshold: int = 10
    saturation_high_threshold: int = 245
    primary_lsb_bit_depth: int = 1
    auxiliary_bd_sens_bit_depth: int = 2
    include_bd_sens_auxiliary: bool = False
    payload_fill_rates: dict[str, float] = field(
        default_factory=lambda: {"low": 0.05, "medium": 0.15, "high": 0.30}
    )
    # Profile-scoped constraints. Defaults keep the full proposal set active
    # so existing code and tests that construct PipelineConfig directly are
    # unaffected.
    active_methods: tuple[str, ...] = field(default_factory=lambda: ALL_METHODS)
    active_payload_levels: tuple[str, ...] = field(
        default_factory=lambda: ALL_PAYLOAD_LEVELS
    )
    active_encryption: tuple[str, ...] = field(default_factory=lambda: ALL_ENCRYPTIONS)
    active_detectors: tuple[str, ...] = field(default_factory=lambda: ALL_DETECTORS)

    def __post_init__(self) -> None:
        if self.payload_mode not in PAYLOAD_MODES:
            raise ValueError(
                f"Unknown payload mode '{self.payload_mode}'. Available: {list(PAYLOAD_MODES)}"
            )
        if self.payload_mode == PAYLOAD_MODE_RANDOM:
            if self.hardcoded_payload_text not in (None, ""):
                raise ValueError("hardcoded_payload_text is only valid with payload_mode='hardcoded'.")
            return
        self.validate_hardcoded_payload_text(self.hardcoded_payload_text)

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

        The three primary conditions are matched by LSB fill rate. The
        defaults target operationally realistic embedding densities and
        keep the strong detectors (RS, Sample Pairs) below saturation so
        the carrier-source signal can show up across the whole detector
        family:

        - low:    0.05 bpp
        - medium: 0.15 bpp
        - high:   0.30 bpp

        ``BD-Sens`` is not part of the main manifest by default; callers can
        request it explicitly by passing ``bit_depth=2``.
        """
        fill_rate = self.payload_fill_rates[payload_level]
        resolved_bit_depth = bit_depth or self.primary_lsb_bit_depth
        return int(self.pixels_per_image * fill_rate * resolved_bit_depth)

    @property
    def min_plaintext_payload_bytes(self) -> int:
        """Smallest plaintext payload byte budget across active levels/encryption states."""
        if not self.active_payload_levels:
            return 0
        smallest_stream_bytes = min(
            self.spatial_payload_bits(level) // 8 for level in self.active_payload_levels
        )
        return max(0, smallest_stream_bytes - AES_CBC_BLOCK_BYTES)

    def validate_hardcoded_payload_text(self, payload_text: str | None) -> bytes:
        """Validate and return UTF-8 bytes for a user-supplied deterministic payload."""
        if not isinstance(payload_text, str) or not payload_text:
            raise ValueError("Hardcoded payload must be non-empty UTF-8 text.")
        invalid = [
            ch for ch in payload_text
            if ord(ch) < 32 and ch not in ("\n", "\r", "\t")
        ]
        if invalid:
            raise ValueError("Hardcoded payload may not contain control characters.")
        payload_bytes = payload_text.encode("utf-8")
        max_bytes = self.min_plaintext_payload_bytes
        if len(payload_bytes) > max_bytes:
            raise ValueError(
                "Hardcoded payload is too large for the active run parameters: "
                f"{len(payload_bytes)} bytes > {max_bytes} bytes."
            )
        return payload_bytes

    # ── Knob-compatibility validation ─────────────────────────────────────────

    def validate(self) -> tuple[list[str], list[str]]:
        """Check the knob combination is internally consistent.

        Returns ``(errors, warnings)``. An empty ``errors`` list means the
        config is safe to execute. Warnings are advisory: the run may be
        valid but produce limited or weaker analyses (e.g. exploratory-only
        instead of confirmatory).

        Rules (R1-R8 from the polish plan):
            R1  n_groups >= MIN_N_GROUPS_RUN (DeLong CI feasibility)
            R2  n_groups >= MIN_N_GROUPS_CONFIRMATORY for confirmatory tests
            R3  active_methods is a non-empty subset of {lsb, dct}
            R4  at least one detector matched to each active method
            R5  active_payload_levels is non-empty subset of {low, medium, high}
            R6  active_encryption is non-empty subset of {plain, encrypted}
            R7  jpeg_quality in [50, 100]; warn if != 95
            R8  payload_mode == hardcoded => hardcoded_payload_text non-empty
                and fits the smallest active level/encryption capacity
        """
        errors: list[str] = []
        warnings: list[str] = []

        # R1, R2
        if self.n_groups < MIN_N_GROUPS_RUN:
            errors.append(
                f"R1: n_groups={self.n_groups} is below the minimum {MIN_N_GROUPS_RUN} "
                "required for any DeLong-based comparison."
            )
        elif self.n_groups < MIN_N_GROUPS_CONFIRMATORY:
            warnings.append(
                f"R2: n_groups={self.n_groups} is below the confirmatory minimum "
                f"{MIN_N_GROUPS_CONFIRMATORY}. Exp 1 and Exp 2 results will be "
                "reported as exploratory rather than confirmatory."
            )

        # R3
        unknown_methods = [m for m in self.active_methods if m not in ALL_METHODS]
        if unknown_methods:
            errors.append(f"R3: unknown method(s) {unknown_methods}; allowed: {list(ALL_METHODS)}.")
        if not self.active_methods:
            errors.append("R3: active_methods must contain at least one of {'lsb', 'dct'}.")

        # R4
        unknown_detectors = [d for d in self.active_detectors if d not in ALL_DETECTORS]
        if unknown_detectors:
            errors.append(
                f"R4: unknown detector(s) {unknown_detectors}; allowed: {list(ALL_DETECTORS)}."
            )
        if not self.active_detectors:
            errors.append("R4: active_detectors must contain at least one detector.")
        else:
            if "lsb" in self.active_methods and not any(
                d in SPATIAL_DETECTORS for d in self.active_detectors
            ):
                errors.append(
                    "R4: 'lsb' is active but no spatial detector is selected. "
                    f"Pick one of {list(SPATIAL_DETECTORS)}."
                )
            if "dct" in self.active_methods and not any(
                d in DCT_DETECTORS for d in self.active_detectors
            ):
                errors.append(
                    "R4: 'dct' is active but no DCT detector is selected. "
                    f"Pick one of {list(DCT_DETECTORS)}."
                )

        # R5
        unknown_levels = [p for p in self.active_payload_levels if p not in ALL_PAYLOAD_LEVELS]
        if unknown_levels:
            errors.append(
                f"R5: unknown payload level(s) {unknown_levels}; allowed: {list(ALL_PAYLOAD_LEVELS)}."
            )
        if not self.active_payload_levels:
            errors.append("R5: active_payload_levels must contain at least one level.")

        # R6
        unknown_encs = [e for e in self.active_encryption if e not in ALL_ENCRYPTIONS]
        if unknown_encs:
            errors.append(
                f"R6: unknown encryption arm(s) {unknown_encs}; allowed: {list(ALL_ENCRYPTIONS)}."
            )
        if not self.active_encryption:
            errors.append("R6: active_encryption must contain 'plain' and/or 'encrypted'.")

        # R7
        if not 50 <= self.jpeg_quality <= 100:
            errors.append(f"R7: jpeg_quality={self.jpeg_quality} is outside the supported range [50, 100].")
        elif self.jpeg_quality != PROPOSAL_JPEG_QUALITY:
            warnings.append(
                f"R7: jpeg_quality={self.jpeg_quality} differs from the proposal-locked Q=95. "
                "DCT results will not be directly comparable to the proposal's reference figures."
            )

        # R8 — hardcoded payload size check is already enforced by __post_init__
        # via validate_hardcoded_payload_text. We re-run it here only to surface
        # the failure as a recoverable warning when checked in advance from the
        # GUI preview path.
        if self.payload_mode == PAYLOAD_MODE_HARDCODED:
            if not self.hardcoded_payload_text:
                errors.append("R8: payload_mode='hardcoded' requires a non-empty hardcoded_payload_text.")

        return errors, warnings

    # ── Figure enablement matrix ──────────────────────────────────────────────

    def planned_figures(self) -> set[str]:
        """Names of figures that this config can produce.

        Each figure name maps to a real plot in ``src/evaluation/plots.py``.
        ``src/pipeline/runner.py`` and the GUI preview endpoint consult this
        set so disabled figures are skipped quietly instead of producing
        placeholder PNGs or raising at plot-time.
        """
        figures: set[str] = set()

        has_spatial = "lsb" in self.active_methods
        has_dct = "dct" in self.active_methods
        spatial_detectors_present = any(
            d in SPATIAL_DETECTORS for d in self.active_detectors
        )
        dct_detectors_present = any(d in DCT_DETECTORS for d in self.active_detectors)
        any_method = bool(self.active_methods)
        any_detector = bool(self.active_detectors)
        any_payload = bool(self.active_payload_levels)

        if not (any_method and any_detector and any_payload):
            return figures

        # Overview / always-on figures
        figures.add("auc_by_source_detector")
        figures.add("auc_by_method_detector")
        figures.add("roc_panels")
        figures.add("quality_summary")

        # Exp 1, 2 — sources are fixed by the pipeline; real + ml_a + ml_b
        # always run together at the run.py layer. Render if any data exists.
        figures.add("exp1_real_vs_ml")
        figures.add("exp2_ml_a_vs_ml_b")

        # Exp 3a — payload interaction needs at least two payload levels.
        if len(self.active_payload_levels) >= 2:
            figures.add("exp3a_payload_interaction")

        # Exp 3b — BD-Sens, or a surrogate disclaimer otherwise.
        if self.include_bd_sens_auxiliary:
            figures.add("exp3b_bd_sens")
        else:
            figures.add("exp3b_bd_sens_surrogate")

        # Exp 4 — branch interaction needs both methods and at least one
        # detector from each branch.
        if has_spatial and has_dct and spatial_detectors_present and dct_detectors_present:
            figures.add("exp4_branch_interaction")

        # Exp 5 — encryption invariance needs both encryption arms.
        if {"plain", "encrypted"}.issubset(self.active_encryption):
            figures.add("exp5_encryption_invariance")
            figures.add("exp5_source_encryption_interaction")

        return figures

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_project_root(cls, project_root: Path) -> "PipelineConfig":
        """Build config with defaults and a resolved absolute project root."""
        return cls(project_root=project_root.resolve())

    @classmethod
    def from_profile(
        cls,
        project_root: Path,
        profile_name: str,
        *,
        n_groups: int | None = None,
        active_methods: tuple[str, ...] | None = None,
        active_payload_levels: tuple[str, ...] | None = None,
        active_encryption: tuple[str, ...] | None = None,
        active_detectors: tuple[str, ...] | None = None,
        include_bd_sens_auxiliary: bool | None = None,
        jpeg_quality: int | None = None,
        payload_mode: str | None = None,
        hardcoded_payload_text: str | None = None,
    ) -> "PipelineConfig":
        """Build a profile-scoped config, optionally overriding individual knobs.

        Any keyword argument left as ``None`` falls through to the profile's
        own default. This is the single entry point the CLI and the GUI use
        when the user customises a run.
        """
        from src.pipeline.profile import PROFILES

        if profile_name not in PROFILES:
            raise ValueError(
                f"Unknown profile '{profile_name}'. "
                f"Available: {list(PROFILES.keys())}"
            )
        profile = PROFILES[profile_name]
        config = cls(
            project_root=project_root.resolve(),
            n_groups=n_groups if n_groups is not None else profile.n_groups,
            active_methods=active_methods if active_methods is not None else profile.active_methods,
            active_payload_levels=(
                active_payload_levels
                if active_payload_levels is not None
                else profile.active_payload_levels
            ),
        )
        overrides: dict[str, object] = {}
        if active_encryption is not None:
            overrides["active_encryption"] = active_encryption
        if active_detectors is not None:
            overrides["active_detectors"] = active_detectors
        if include_bd_sens_auxiliary is not None:
            overrides["include_bd_sens_auxiliary"] = include_bd_sens_auxiliary
        if jpeg_quality is not None:
            overrides["jpeg_quality"] = jpeg_quality
        if payload_mode is not None:
            overrides["payload_mode"] = payload_mode
        if hardcoded_payload_text is not None:
            overrides["hardcoded_payload_text"] = hardcoded_payload_text
        if overrides:
            config = replace(config, **overrides)
        return config

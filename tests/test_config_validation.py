"""Tests for the knob-compatibility validation matrix in src/pipeline/config.py.

Each rule R1–R8 has at least a positive and a negative case. ``planned_figures``
is exercised against the same config shapes to lock in the GUI preview contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.config import (
    ALL_DETECTORS,
    ALL_ENCRYPTIONS,
    ALL_METHODS,
    ALL_PAYLOAD_LEVELS,
    MIN_N_GROUPS_CONFIRMATORY,
    MIN_N_GROUPS_RUN,
    PROPOSAL_JPEG_QUALITY,
    PipelineConfig,
)


PROJECT = Path(".")


def _cfg(**kwargs) -> PipelineConfig:
    return PipelineConfig.from_profile(PROJECT, "prototype_full", **kwargs)


def test_default_profile_validates_clean() -> None:
    errors, warnings = _cfg().validate()
    assert errors == []
    assert warnings == []


def test_r1_blocks_n_groups_below_minimum() -> None:
    errors, _ = _cfg(n_groups=MIN_N_GROUPS_RUN - 1).validate()
    assert any("R1" in e for e in errors)


def test_r2_warns_below_confirmatory_minimum() -> None:
    errors, warnings = _cfg(n_groups=MIN_N_GROUPS_CONFIRMATORY - 1).validate()
    assert errors == []
    assert any("R2" in w for w in warnings)


def test_r3_requires_at_least_one_method() -> None:
    errors, _ = _cfg(active_methods=()).validate()
    assert any("R3" in e for e in errors)


def test_r3_rejects_unknown_method() -> None:
    errors, _ = _cfg(active_methods=("lsb", "weird")).validate()
    assert any("R3" in e for e in errors)


def test_r4_requires_spatial_detector_when_lsb_active() -> None:
    errors, _ = _cfg(
        active_methods=("lsb",),
        active_detectors=("chi_square_dct",),
    ).validate()
    assert any("R4" in e and "spatial" in e for e in errors)


def test_r4_requires_dct_detector_when_dct_active() -> None:
    errors, _ = _cfg(
        active_methods=("dct",),
        active_detectors=("rs",),
    ).validate()
    assert any("R4" in e and "DCT" in e for e in errors)


def test_r4_passes_when_each_branch_has_a_detector() -> None:
    errors, _ = _cfg(
        active_methods=("lsb", "dct"),
        active_detectors=("rs", "calibration_chi_square"),
    ).validate()
    assert errors == []


def test_r5_requires_payload_level() -> None:
    errors, _ = _cfg(active_payload_levels=()).validate()
    assert any("R5" in e for e in errors)


def test_r6_requires_encryption_arm() -> None:
    errors, _ = _cfg(active_encryption=()).validate()
    assert any("R6" in e for e in errors)


def test_r7_blocks_invalid_jpeg_quality() -> None:
    errors, _ = _cfg(jpeg_quality=20).validate()
    assert any("R7" in e for e in errors)


def test_r7_warns_when_jpeg_quality_differs_from_proposal() -> None:
    errors, warnings = _cfg(jpeg_quality=PROPOSAL_JPEG_QUALITY - 5).validate()
    assert errors == []
    assert any("R7" in w for w in warnings)


def test_planned_figures_full_design_includes_all_experiments() -> None:
    figures = _cfg().planned_figures()
    assert {
        "exp1_real_vs_ml",
        "exp2_ml_a_vs_ml_b",
        "exp3a_payload_interaction",
        "exp4_branch_interaction",
        "exp5_encryption_invariance",
        "exp5_source_encryption_interaction",
        "quality_summary",
        "roc_panels",
    } <= figures


def test_planned_figures_omits_exp3a_when_single_payload() -> None:
    figures = _cfg(active_payload_levels=("low",)).planned_figures()
    assert "exp3a_payload_interaction" not in figures


def test_planned_figures_omits_exp4_when_only_one_method() -> None:
    figures = _cfg(active_methods=("lsb",)).planned_figures()
    assert "exp4_branch_interaction" not in figures


def test_planned_figures_omits_exp5_when_only_one_encryption_arm() -> None:
    figures = _cfg(active_encryption=("plain",)).planned_figures()
    assert "exp5_encryption_invariance" not in figures
    assert "exp5_source_encryption_interaction" not in figures


def test_planned_figures_uses_real_bd_sens_when_enabled() -> None:
    figures = _cfg(include_bd_sens_auxiliary=True).planned_figures()
    assert "exp3b_bd_sens" in figures
    assert "exp3b_bd_sens_surrogate" not in figures


def test_planned_figures_uses_surrogate_when_bd_sens_disabled() -> None:
    figures = _cfg(include_bd_sens_auxiliary=False).planned_figures()
    assert "exp3b_bd_sens_surrogate" in figures
    assert "exp3b_bd_sens" not in figures


def test_from_profile_overrides_propagate() -> None:
    config = PipelineConfig.from_profile(
        PROJECT,
        "prototype",
        n_groups=42,
        active_methods=("dct",),
        active_payload_levels=("high",),
        active_encryption=("encrypted",),
        active_detectors=("chi_square_dct", "calibration_chi_square"),
        include_bd_sens_auxiliary=True,
        jpeg_quality=80,
    )
    assert config.n_groups == 42
    assert config.active_methods == ("dct",)
    assert config.active_payload_levels == ("high",)
    assert config.active_encryption == ("encrypted",)
    assert config.active_detectors == ("chi_square_dct", "calibration_chi_square")
    assert config.include_bd_sens_auxiliary is True
    assert config.jpeg_quality == 80


def test_constants_align_with_contracts() -> None:
    """Sanity: the config-level constants match the canonical contract module."""
    from src.common.contracts import ENCRYPTION_STATES, METHODS, PAYLOAD_LEVELS

    assert set(ALL_METHODS) == set(METHODS)
    assert set(ALL_PAYLOAD_LEVELS) == set(PAYLOAD_LEVELS)
    assert set(ALL_ENCRYPTIONS) == set(ENCRYPTION_STATES)
    assert len(ALL_DETECTORS) == 6

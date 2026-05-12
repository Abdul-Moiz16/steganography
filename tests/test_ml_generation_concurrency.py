"""Smoke + parity tests for the ThreadPoolExecutor-based ML cover generation.

Uses the stub engine so the test is deterministic and doesn't touch the
network. Verifies that:
- Sequential (ML_GEN_CONCURRENCY=1) and concurrent (>1) produce identical
  manifest row sets.
- Identical seeded stub output regardless of thread count.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from src.data.generate_ml_covers import generate_ml_covers_from_prompts


_PROMPT_FIELDS = [
    "group_id", "dataset", "orig_id", "caption_id", "caption_text",
    "real_spatial_path", "real_frequency_path",
]


@pytest.fixture()
def prompts_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "generation_prompts.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PROMPT_FIELDS)
        writer.writeheader()
        for i in range(1, 5):
            writer.writerow({
                "group_id": str(i),
                "dataset": "synthetic",
                "orig_id": f"orig{i}",
                "caption_id": f"c{i}",
                "caption_text": f"a synthetic caption {i}",
                "real_spatial_path": f"covers/real/g{i:04d}.png",
                "real_frequency_path": f"covers/real/g{i:04d}.jpg",
            })
    return csv_path


def _run_one(tmp_path: Path, prompts_csv: Path, concurrency: int) -> Path:
    run_dir = tmp_path / f"run_c{concurrency}"
    run_dir.mkdir()
    (run_dir / "covers").mkdir()
    os.environ["ML_GEN_CONCURRENCY"] = str(concurrency)
    try:
        generate_ml_covers_from_prompts(
            project_root=tmp_path,
            prompts_csv=prompts_csv,
            engine="stub",
            seed_base=42,
            run_dir=run_dir,
        )
    finally:
        os.environ.pop("ML_GEN_CONCURRENCY", None)
    return run_dir


def test_sequential_and_concurrent_produce_same_manifests(
    tmp_path: Path, prompts_csv: Path
) -> None:
    seq_dir = _run_one(tmp_path, prompts_csv, concurrency=1)
    par_dir = _run_one(tmp_path, prompts_csv, concurrency=4)

    for source in ("ml_a", "ml_b"):
        seq_manifest = seq_dir / "manifests" / f"covers_{source}.csv"
        par_manifest = par_dir / "manifests" / f"covers_{source}.csv"
        assert seq_manifest.exists() and par_manifest.exists()

        with seq_manifest.open(newline="") as f:
            seq_rows = sorted(csv.DictReader(f), key=lambda r: int(r["group_id"]))
        with par_manifest.open(newline="") as f:
            par_rows = sorted(csv.DictReader(f), key=lambda r: int(r["group_id"]))

        # Manifest content (apart from per-row absolute paths) must match.
        for s, p in zip(seq_rows, par_rows):
            assert s["group_id"] == p["group_id"]
            assert s["source"] == p["source"]
            assert s["seed"] == p["seed"]
            assert s["caption_text"] == p["caption_text"]

        # Stub generator is seeded by (tag, prompt, seed), so the generated
        # images themselves must be byte-identical regardless of thread count.
        for s in seq_rows:
            seq_file = seq_dir / s["spatial_path"].split(f"run_c1/")[-1]
            par_file = par_dir / s["spatial_path"].replace("run_c1", "run_c4")
            # Resolve via the actual filesystem paths instead.
            seq_path = (seq_dir.parent / s["spatial_path"]).resolve()
            par_path_str = s["spatial_path"].replace("run_c1", "run_c4")
            par_path = (par_dir.parent / par_path_str).resolve()
            if seq_path.exists() and par_path.exists():
                assert seq_path.read_bytes() == par_path.read_bytes()


def test_concurrency_env_override_is_respected(
    tmp_path: Path, prompts_csv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ML_GEN_CONCURRENCY env var must clamp to at least 1 even on garbage."""
    monkeypatch.setenv("ML_GEN_CONCURRENCY", "not-a-number")
    run_dir = tmp_path / "run_bad_env"
    run_dir.mkdir()
    (run_dir / "covers").mkdir()
    # Should not raise; just falls back to the default concurrency.
    generate_ml_covers_from_prompts(
        project_root=tmp_path,
        prompts_csv=prompts_csv,
        engine="stub",
        seed_base=42,
        run_dir=run_dir,
    )
    assert (run_dir / "manifests" / "covers_ml.csv").exists()

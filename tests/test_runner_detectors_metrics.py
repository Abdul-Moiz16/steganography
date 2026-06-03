from __future__ import annotations

from pathlib import Path

from src.data.manifests import read_rows_csv, write_rows_csv
from src.pipeline.config import PipelineConfig
from src.pipeline.runner import PipelineRunner


STEGO_FIELDS = [
    "group_id",
    "source",
    "method",
    "payload_level",
    "encryption",
    "cover_path",
    "payload_path",
    "stego_path",
    "embed_params",
    "seed",
]


def _write_test_images(project_root: Path) -> tuple[Path, Path, Path, Path]:
    from PIL import Image

    spatial_cover = project_root / "data" / "covers" / "spatial" / "real" / "g0001__src-real.png"
    spatial_stego = project_root / "data" / "stego" / "lsb" / "low" / "plain" / "real" / "g0001__src-real__m-lsb__p-low__e-plain.png"
    dct_cover = project_root / "data" / "covers" / "frequency" / "real" / "g0001__src-real.jpg"
    dct_stego = project_root / "data" / "stego" / "dct" / "high" / "encrypted" / "real" / "g0001__src-real__m-dct__p-high__e-encrypted.jpg"
    spatial_cover.parent.mkdir(parents=True, exist_ok=True)
    spatial_stego.parent.mkdir(parents=True, exist_ok=True)
    dct_cover.parent.mkdir(parents=True, exist_ok=True)
    dct_stego.parent.mkdir(parents=True, exist_ok=True)

    Image.new("L", (32, 32), color=30).save(spatial_cover)
    Image.new("L", (32, 32), color=35).save(spatial_stego)
    Image.new("L", (32, 32), color=40).save(dct_cover, format="JPEG")
    Image.new("L", (32, 32), color=45).save(dct_stego, format="JPEG")
    return spatial_cover, spatial_stego, dct_cover, dct_stego


def test_run_detector_stage_dry_run_and_compute_metrics(tmp_path: Path) -> None:
    runner = PipelineRunner(PipelineConfig(project_root=tmp_path, n_groups=2))

    spatial_cover, spatial_stego, dct_cover, dct_stego = _write_test_images(tmp_path)
    stego_manifest = tmp_path / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(spatial_cover.relative_to(tmp_path)),
                "payload_path": "data/payloads/plain/low/g0001__p-low__e-plain.bin",
                "stego_path": str(spatial_stego.relative_to(tmp_path)),
                "embed_params": "{}",
                "seed": "42",
            },
            {
                "group_id": "1",
                "source": "real",
                "method": "dct",
                "payload_level": "high",
                "encryption": "encrypted",
                "cover_path": str(dct_cover.relative_to(tmp_path)),
                "payload_path": "data/payloads/encrypted/high/g0001__p-high__e-encrypted.bin",
                "stego_path": str(dct_stego.relative_to(tmp_path)),
                "embed_params": "{}",
                "seed": "42",
            },
            {
                "group_id": "2",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(spatial_cover.relative_to(tmp_path)),
                "payload_path": "data/payloads/plain/low/g0002__p-low__e-plain.bin",
                "stego_path": str(spatial_stego.relative_to(tmp_path)),
                "embed_params": "{}",
                "seed": "42",
            },
        ],
        fieldnames=STEGO_FIELDS,
    )

    pred_path = runner.run_detector_stage(
        stego_manifest_path=stego_manifest,
        execute=False,
    )

    pred_rows = read_rows_csv(pred_path)
    # 2 lsb rows * 3 spatial detectors * 2 score rows (cover+stego) +
    # 1 dct row * 3 frequency detectors * 2 score rows = 12 + 6 = 18.
    assert len(pred_rows) == 18
    assert all(r["score"] == "" for r in pred_rows)


def test_run_detector_stage_execute_with_stub_scores_and_metrics(tmp_path: Path) -> None:
    runner = PipelineRunner(PipelineConfig(project_root=tmp_path, n_groups=1))

    spatial_cover, spatial_stego, _, _ = _write_test_images(tmp_path)
    stego_manifest = tmp_path / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(spatial_cover.relative_to(tmp_path)),
                "payload_path": "data/payloads/plain/low/g0001__p-low__e-plain.bin",
                "stego_path": str(spatial_stego.relative_to(tmp_path)),
                "embed_params": "{}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDS,
    )

    # Stub the detector dispatch so we get deterministic, perfect-AUC scores.
    # The runner farms work out to multiprocessing workers, but they would not
    # see a monkey-patch applied in this process, so force sequential mode
    # (n_workers=1) and patch the module-level helper that both paths use.
    import src.pipeline.runner as runner_mod

    def fake_score_path(detector, path, jpeg_quality):
        _ = (detector, jpeg_quality)
        return 0.9 if "stego" in str(path) else 0.1

    monkeypatch_real = runner_mod._score_path
    runner_mod._score_path = fake_score_path
    try:
        pred_path = runner.run_detector_stage(
            stego_manifest_path=stego_manifest,
            execute=True,
            n_workers=1,
        )
    finally:
        runner_mod._score_path = monkeypatch_real
    preds = read_rows_csv(pred_path)
    assert len(preds) == 6
    assert {p["detector"] for p in preds} == {"rs", "chi_square_spatial", "sample_pairs"}

    outputs = runner.compute_metrics_from_predictions(predictions_path=pred_path)

    detector_rows = read_rows_csv(outputs["detector_metrics"])
    cond_rows = read_rows_csv(outputs["condition_metrics"])
    src_rows = read_rows_csv(outputs["source_metrics"])

    assert len(detector_rows) == 3
    assert len(cond_rows) == 3
    assert len(src_rows) == 3
    assert all(float(r["roc_auc"]) == 1.0 for r in detector_rows)


def test_run_detector_stage_skip_unimplemented(tmp_path: Path) -> None:
    runner = PipelineRunner(PipelineConfig(project_root=tmp_path, n_groups=1))

    spatial_cover, spatial_stego, _, _ = _write_test_images(tmp_path)
    stego_manifest = tmp_path / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(spatial_cover.relative_to(tmp_path)),
                "payload_path": "data/payloads/plain/low/g0001__p-low__e-plain.bin",
                "stego_path": str(spatial_stego.relative_to(tmp_path)),
                "embed_params": "{}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDS,
    )

    pred_path = runner.run_detector_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        skip_unimplemented=True,
    )

    preds = read_rows_csv(pred_path)
    # rs, chi_square_spatial, and sample_pairs are all implemented;
    # skip_unimplemented only drops detectors that raise NotImplementedError.
    detectors_found = {p["detector"] for p in preds}
    assert "rs" in detectors_found
    assert "chi_square_spatial" in detectors_found
    assert "sample_pairs" in detectors_found

from __future__ import annotations

from pathlib import Path

from src.data.manifests import write_rows_csv
from src.pipeline.cli import _resolve_path, main
from tests.helpers import STEGO_FIELDNAMES, write_cover_manifest


def test_resolve_path_relative_and_absolute(tmp_path: Path) -> None:
    project_root = tmp_path
    relative = Path("data/x.csv")
    absolute = tmp_path / "abs.csv"

    assert _resolve_path(relative, project_root) == project_root / relative
    assert _resolve_path(absolute, project_root) == absolute


def test_cli_init_layout(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--project-root", str(tmp_path), "init-layout"],
    )
    main()
    out = capsys.readouterr().out

    assert "Layout initialized" in out
    assert (tmp_path / "data" / "covers" / "spatial" / "real").is_dir()
    assert (tmp_path / "data" / "covers" / "frequency" / "real").is_dir()
    assert (tmp_path / "results" / "metrics").is_dir()
    assert (tmp_path / "results" / "figures").is_dir()


def test_cli_run_embedding_stage_dry_run(monkeypatch, capsys, tmp_path: Path) -> None:
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
                "cover_path": "/tmp/cover.png",
                "payload_path": "/tmp/payload.bin",
                "stego_path": "/tmp/stego.png",
                "embed_params": "{}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--project-root",
            str(tmp_path),
            "run-embedding-stage",
            "--stego-manifest",
            "data/manifests/stego_manifest.csv",
        ],
    )
    main()
    out = capsys.readouterr().out

    assert "Embedding rows processed: 1" in out


def test_cli_run_detectors_dry_run(monkeypatch, capsys, tmp_path: Path) -> None:
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
                "cover_path": "data/covers/spatial/real/g0001__src-real.png",
                "payload_path": "data/payloads/plain/low/g0001__p-low__e-plain.bin",
                "stego_path": "data/stego/lsb/low/plain/real/g0001__src-real__m-lsb__p-low__e-plain.png",
                "embed_params": "{}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--project-root",
            str(tmp_path),
            "run-detectors",
            "--stego-manifest",
            "data/manifests/stego_manifest.csv",
        ],
    )
    main()
    out = capsys.readouterr().out

    assert "Predictions CSV" in out
    assert (tmp_path / "results" / "predictions" / "predictions.csv").exists()


def test_cli_compute_metrics(monkeypatch, capsys, tmp_path: Path) -> None:
    predictions = tmp_path / "results" / "predictions" / "predictions.csv"
    write_rows_csv(
        predictions,
        rows=[
            {
                "detector": "rs",
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "label": "0",
                "score": "0.1",
            },
            {
                "detector": "rs",
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "label": "1",
                "score": "0.9",
            },
        ],
        fieldnames=[
            "detector",
            "group_id",
            "source",
            "method",
            "payload_level",
            "encryption",
            "label",
            "score",
        ],
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--project-root",
            str(tmp_path),
            "compute-metrics",
            "--predictions",
            "results/predictions/predictions.csv",
        ],
    )
    main()
    out = capsys.readouterr().out

    assert "Detector metrics CSV" in out
    assert (tmp_path / "results" / "metrics" / "detector_metrics.csv").exists()
    assert (tmp_path / "results" / "metrics" / "condition_metrics.csv").exists()
    assert (tmp_path / "results" / "metrics" / "source_metrics.csv").exists()


def test_cli_plot_metrics(monkeypatch, capsys, tmp_path: Path) -> None:
    import pytest

    pytest.importorskip("matplotlib")

    metrics_dir = tmp_path / "results" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    write_rows_csv(
        metrics_dir / "source_metrics.csv",
        rows=[
            {
                "detector": "rs",
                "source": "real",
                "n_samples": "2",
                "n_pos": "1",
                "n_neg": "1",
                "roc_auc": "0.75",
                "eer": "0.2",
                "accuracy_at_youden_j": "0.8",
                "fpr_at_fixed_fnr": "0.1",
            }
        ],
        fieldnames=[
            "detector",
            "source",
            "n_samples",
            "n_pos",
            "n_neg",
            "roc_auc",
            "eer",
            "accuracy_at_youden_j",
            "fpr_at_fixed_fnr",
        ],
    )
    write_rows_csv(
        metrics_dir / "condition_metrics.csv",
        rows=[
            {
                "detector": "rs",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "n_samples": "2",
                "n_pos": "1",
                "n_neg": "1",
                "roc_auc": "0.75",
                "eer": "0.2",
                "accuracy_at_youden_j": "0.8",
                "fpr_at_fixed_fnr": "0.1",
            }
        ],
        fieldnames=[
            "detector",
            "method",
            "payload_level",
            "encryption",
            "n_samples",
            "n_pos",
            "n_neg",
            "roc_auc",
            "eer",
            "accuracy_at_youden_j",
            "fpr_at_fixed_fnr",
        ],
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--project-root",
            str(tmp_path),
            "plot-metrics",
        ],
    )
    main()
    out = capsys.readouterr().out

    assert "AUC by source figure" in out
    assert (tmp_path / "results" / "figures" / "auc_by_source_detector.png").exists()
    assert (tmp_path / "results" / "figures" / "auc_by_method_detector.png").exists()


def test_cli_run_all_dry_run(monkeypatch, capsys, tmp_path: Path) -> None:
    covers_manifest = write_cover_manifest(
        tmp_path / "data" / "manifests" / "covers_master.csv",
        group_ids=range(1, 501),
    )
    assert covers_manifest.exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--project-root",
            str(tmp_path),
            "run-all",
            "--covers-manifest",
            "data/manifests/covers_master.csv",
        ],
    )
    main()
    out = capsys.readouterr().out

    assert "Embedding rows processed: 18000" in out
    assert (tmp_path / "data" / "manifests" / "payload_manifest.csv").exists()
    assert (tmp_path / "data" / "manifests" / "stego_manifest.csv").exists()
    assert (tmp_path / "results" / "predictions" / "predictions.csv").exists()
    assert (tmp_path / "results" / "metrics" / "detector_metrics.csv").exists()

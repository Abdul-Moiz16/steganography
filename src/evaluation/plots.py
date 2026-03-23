from __future__ import annotations

"""Figure generation from computed metrics tables."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_placeholder_plot(path: Path, title: str, reason: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(10, 5))
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0.5, 0.6, title, ha="center", va="center", fontsize=14, fontweight="bold")
    ax.text(0.5, 0.4, reason, ha="center", va="center", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def generate_metrics_figures(metrics_dir: Path, figures_dir: Path) -> dict[str, Path]:
    """Generate core AUC figures from metrics outputs.

    Outputs:
    - auc_by_source_detector.png
    - auc_by_method_detector.png
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics_dir = metrics_dir.resolve()
    figures_dir = figures_dir.resolve()
    figures_dir.mkdir(parents=True, exist_ok=True)

    source_metrics_path = metrics_dir / "source_metrics.csv"
    condition_metrics_path = metrics_dir / "condition_metrics.csv"

    source_fig_path = figures_dir / "auc_by_source_detector.png"
    method_fig_path = figures_dir / "auc_by_method_detector.png"

    source_rows = _read_csv_rows(source_metrics_path)
    condition_rows = _read_csv_rows(condition_metrics_path)

    # ---- Figure 1: detector x source mean AUC ----
    source_grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    detectors: set[str] = set()
    sources: set[str] = set()

    for row in source_rows:
        auc = _maybe_float(row.get("roc_auc"))
        if auc is None:
            continue
        detector = row.get("detector", "")
        source = row.get("source", "")
        if not detector or not source:
            continue
        detectors.add(detector)
        sources.add(source)
        source_grouped[(detector, source)].append(auc)

    if not source_grouped:
        _write_placeholder_plot(
            source_fig_path,
            "AUC by Source and Detector",
            "No numeric source_metrics available yet.",
        )
    else:
        det_sorted = sorted(detectors)
        src_sorted = sorted(sources)

        x = list(range(len(det_sorted)))
        width = 0.8 / max(len(src_sorted), 1)

        fig, ax = plt.subplots(figsize=(11, 5))
        for i, source in enumerate(src_sorted):
            values = [
                mean(source_grouped[(det, source)])
                if (det, source) in source_grouped
                else 0.0
                for det in det_sorted
            ]
            shift = (i - (len(src_sorted) - 1) / 2.0) * width
            ax.bar([v + shift for v in x], values, width=width, label=source)

        ax.set_xticks(x)
        ax.set_xticklabels(det_sorted)
        ax.set_ylim(0.0, 1.0)
        ax.set_ylabel("ROC-AUC")
        ax.set_title("ROC-AUC by Detector and Source")
        ax.legend(title="Source")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(source_fig_path, dpi=150)
        plt.close(fig)

    # ---- Figure 2: detector x method mean AUC ----
    method_grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    detectors2: set[str] = set()
    methods: set[str] = set()

    for row in condition_rows:
        auc = _maybe_float(row.get("roc_auc"))
        if auc is None:
            continue
        detector = row.get("detector", "")
        method = row.get("method", "")
        if not detector or not method:
            continue
        detectors2.add(detector)
        methods.add(method)
        method_grouped[(detector, method)].append(auc)

    if not method_grouped:
        _write_placeholder_plot(
            method_fig_path,
            "AUC by Method and Detector",
            "No numeric condition_metrics available yet.",
        )
    else:
        det_sorted = sorted(detectors2)
        method_sorted = sorted(methods)

        x = list(range(len(det_sorted)))
        width = 0.8 / max(len(method_sorted), 1)

        fig, ax = plt.subplots(figsize=(11, 5))
        for i, method in enumerate(method_sorted):
            values = [
                mean(method_grouped[(det, method)])
                if (det, method) in method_grouped
                else 0.0
                for det in det_sorted
            ]
            shift = (i - (len(method_sorted) - 1) / 2.0) * width
            ax.bar([v + shift for v in x], values, width=width, label=method)

        ax.set_xticks(x)
        ax.set_xticklabels(det_sorted)
        ax.set_ylim(0.0, 1.0)
        ax.set_ylabel("ROC-AUC")
        ax.set_title("ROC-AUC by Detector and Embedding Method")
        ax.legend(title="Method")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(method_fig_path, dpi=150)
        plt.close(fig)

    return {
        "auc_by_source_detector": source_fig_path,
        "auc_by_method_detector": method_fig_path,
    }

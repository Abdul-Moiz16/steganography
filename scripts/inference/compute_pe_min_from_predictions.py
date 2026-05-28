"""Per-stratum AUC + P_E^min summary from a predictions CSV.

Reads a `predictions_*.csv` written by the apply_dctr_to_run.py /
apply_srnet_to_run.py inference scripts (or the main pipeline's
predictions.csv) and emits a small results CSV with one row per
(detector, method, payload_level, encryption, source) stratum:

    detector, method, payload_level, encryption, source,
    n_pos, n_neg, auc, pe_min

This is the test-set operational error rate -- the same quantity
SRNet (Boroumand+17) reports under "minimal detection error under
equal priors" and that DCTR (Holub & Fridrich 2015) reports as
E_OOB for its trained ensemble (the OOB residual is sklearn's
analogue; for a non-ensemble detector like SRNet there is no OOB
and the held-out P_E^min is the correct cross-paper counterpart).

The computation is a pure function of the (label, score) pairs in
the input CSV; same input -> bit-identical output.

Usage
-----
    python scripts/inference/compute_pe_min_from_predictions.py \
        --predictions runs/<run>/predictions/predictions_dctr.csv \
        --out runs/<run>/predictions/pe_min_dctr.csv

Multiple input files in one call (writes one summary per input):

    python scripts/inference/compute_pe_min_from_predictions.py \
        --predictions runs/<run>/predictions/predictions_dctr.csv \
                      runs/<run>/predictions/predictions_srnet.csv \
        --out-dir runs/<run>/predictions/

Stratification keys default to the canonical
(method, payload_level, encryption, source) tuple; the per-row
``detector`` column is preserved on every output row.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

# Make runnable without PYTHONPATH=. and identical to the rest of the
# scripts/ tree's bootstrap.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.evaluation.metrics import pe_min, roc_auc_score_binary  # noqa: E402


STRATIFY = ("detector", "method", "payload_level", "encryption", "source")
OUT_FIELDS = list(STRATIFY) + ["n_pos", "n_neg", "auc", "pe_min"]


def _summarise(csv_path: Path) -> list[dict]:
    """Compute per-stratum AUC + P_E^min from a predictions CSV.

    Strata with <2 of either class are skipped (no meaningful threshold
    sweep possible).  Detector column is preserved -- if the file mixes
    multiple detectors (it shouldn't, but predictions.csv from the main
    pipeline does) each detector's strata are reported separately.
    """
    buckets: dict[tuple, list[tuple[int, float]]] = defaultdict(list)
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        missing = [k for k in STRATIFY + ("label", "score") if k not in reader.fieldnames]
        if missing:
            raise SystemExit(
                f"{csv_path}: missing required columns {missing}; "
                f"saw {reader.fieldnames}"
            )
        for r in reader:
            key = tuple(r[k] for k in STRATIFY)
            buckets[key].append((int(r["label"]), float(r["score"])))

    out: list[dict] = []
    for key, items in sorted(buckets.items()):
        labels = [y for y, _ in items]
        scores = [s for _, s in items]
        n_pos = sum(1 for y in labels if y == 1)
        n_neg = len(labels) - n_pos
        if n_pos < 2 or n_neg < 2:
            continue
        try:
            auc = roc_auc_score_binary(labels, scores)
        except ValueError:
            continue
        entry = {k: v for k, v in zip(STRATIFY, key)}
        entry.update({
            "n_pos": n_pos,
            "n_neg": n_neg,
            "auc": f"{float(auc):.6f}",
            "pe_min": f"{pe_min(labels, scores):.6f}",
        })
        out.append(entry)
    return out


def _write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _default_out_for(predictions_path: Path) -> Path:
    """For predictions_<x>.csv -> pe_min_<x>.csv in the same directory."""
    stem = predictions_path.stem
    suffix = stem[len("predictions_"):] if stem.startswith("predictions_") else stem
    return predictions_path.with_name(f"pe_min_{suffix}.csv")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--predictions", type=Path, nargs="+", required=True,
                   help="One or more predictions CSV paths.")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--out", type=Path, default=None,
                     help="Single output CSV path. Only valid with exactly one --predictions input.")
    grp.add_argument("--out-dir", type=Path, default=None,
                     help="Directory; one pe_min_<x>.csv emitted per input. "
                          "Default: write next to each input CSV.")
    args = p.parse_args()

    if args.out is not None and len(args.predictions) != 1:
        raise SystemExit("--out requires exactly one --predictions input; use --out-dir for multiple.")

    for pred_path in args.predictions:
        if not pred_path.exists():
            raise SystemExit(f"predictions file not found: {pred_path}")
        rows = _summarise(pred_path)
        if args.out is not None:
            out_path = args.out
        elif args.out_dir is not None:
            out_path = args.out_dir / _default_out_for(pred_path).name
        else:
            out_path = _default_out_for(pred_path)
        _write_csv(rows, out_path)
        # Compact stdout summary: one line per stratum, mean per detector.
        per_detector: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for r in rows:
            per_detector[r["detector"]].append((float(r["auc"]), float(r["pe_min"])))
        print(f"wrote {out_path} ({len(rows)} strata from {pred_path.name})")
        for det, pairs in sorted(per_detector.items()):
            mean_auc = sum(a for a, _ in pairs) / len(pairs)
            mean_pe = sum(p for _, p in pairs) / len(pairs)
            print(f"  {det}: {len(pairs)} strata, mean AUC {mean_auc:.4f}, mean P_E^min {mean_pe:.4f}")


if __name__ == "__main__":
    main()

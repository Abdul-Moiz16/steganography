"""
Worker : Daria Gjonbalaj

RQ5 encryption-invariance analysis.

Reads predictions.csv from a finished run and compares plain vs encrypted
detector AUC per stratum (detector x source x method x payload_level) using
the paired DeLong test. AUC equivalence is reported via a confidence-interval
margin: encryption is "practically invariant" when the 95% CI for the AUC
difference lies inside [-margin, +margin].

Proposal alignment
------------------
- ``docs/proposals/proposal_updated_3.tex``, Section Experiments, Exp. 5 (RQ5).
- DeLong test [delong1988]: same covers across the two conditions, so the
  paired form of the test is used (in-tree implementation, see
  ``src/evaluation/plots.py:_delong_compare``).

Usage
-----
    python -m src.analysis.encryption_invariance runs/<run-id>

Output CSV: ``metrics/encryption_invariance.csv`` (one row per stratum):
    detector, source, method, payload_level
    n_pos_plain, n_neg_plain, n_pos_enc, n_neg_enc
    auc_plain, auc_encrypted, auc_diff
    ci_lo, ci_hi, p_value
    invariant_within_margin
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from src.evaluation.plots import _delong_compare


def _load_predictions(predictions_csv: Path) -> list[dict[str, str]]:
    """Read predictions.csv into row dicts."""
    with predictions_csv.open(newline="") as f:
        return list(csv.DictReader(f))


def _pos_neg(
    rows: list[dict[str, str]], encryption: str
) -> tuple[list[float], list[float]]:
    """Split a stratum's rows into stego (label=1) and cover (label=0) scores
    for the requested encryption condition.
    """
    pos: list[float] = []
    neg: list[float] = []
    for r in rows:
        if r["encryption"] != encryption:
            continue
        score = float(r["score"])
        if r["label"] == "1":
            pos.append(score)
        elif r["label"] == "0":
            neg.append(score)
    return pos, neg


def _stratum_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row["detector"], row["source"], row["method"], row["payload_level"])


def analyse_stratum(
    rows: list[dict[str, str]],
    *,
    margin: float = 0.025,
) -> dict[str, object]:
    """Run paired DeLong on plain vs encrypted scores within one stratum.

    Returns AUC for each condition, the difference, its 95% CI, the DeLong
    p-value, and a boolean flag set when the full CI lies in [-margin, margin].
    """
    pos_plain, neg_plain = _pos_neg(rows, "plain")
    pos_enc, neg_enc = _pos_neg(rows, "encrypted")

    result = _delong_compare(pos_plain, neg_plain, pos_enc, neg_enc, paired=True)

    auc_plain = result["auc_a"]
    auc_enc = result["auc_b"]
    ci_lo = result["ci_lo"]
    ci_hi = result["ci_hi"]

    invariant = (
        ci_lo is not None
        and ci_hi is not None
        and ci_lo >= -margin
        and ci_hi <= margin
    )

    return {
        "n_pos_plain": len(pos_plain),
        "n_neg_plain": len(neg_plain),
        "n_pos_enc": len(pos_enc),
        "n_neg_enc": len(neg_enc),
        "auc_plain": auc_plain,
        "auc_encrypted": auc_enc,
        "auc_diff": result["diff"],
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "p_value": result["p"],
        "invariant_within_margin": invariant,
    }


def run_encryption_invariance(
    run_dir: Path,
    *,
    margin: float = 0.025,
) -> Path:
    """Compute the per-stratum RQ5 invariance table and save it under metrics/.

    Strata are (detector, source, method, payload_level). Only strata that
    contain at least one row in each of the plain and encrypted conditions
    contribute to the output.
    """
    predictions_csv = run_dir / "predictions" / "predictions.csv"
    if not predictions_csv.exists():
        raise FileNotFoundError(f"predictions.csv not found at {predictions_csv}")

    rows = _load_predictions(predictions_csv)

    buckets: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        buckets[_stratum_key(r)].append(r)

    output_rows: list[dict[str, object]] = []
    for key in sorted(buckets):
        detector, source, method, payload_level = key
        stratum_rows = buckets[key]
        encryptions = {r["encryption"] for r in stratum_rows}
        if not {"plain", "encrypted"}.issubset(encryptions):
            continue

        stats = analyse_stratum(stratum_rows, margin=margin)
        output_rows.append(
            {
                "detector": detector,
                "source": source,
                "method": method,
                "payload_level": payload_level,
                **stats,
            }
        )

    out_path = run_dir / "metrics" / "encryption_invariance.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "detector", "source", "method", "payload_level",
        "n_pos_plain", "n_neg_plain", "n_pos_enc", "n_neg_enc",
        "auc_plain", "auc_encrypted", "auc_diff",
        "ci_lo", "ci_hi", "p_value",
        "invariant_within_margin",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} stratum rows to {out_path}")
    return out_path


def main() -> None:
    """CLI entry: ``python -m src.analysis.encryption_invariance <run_dir>``."""
    if len(sys.argv) != 2:
        print("Usage: python -m src.analysis.encryption_invariance <run_dir>")
        sys.exit(1)
    run_encryption_invariance(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

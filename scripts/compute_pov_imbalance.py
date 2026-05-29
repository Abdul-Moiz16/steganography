"""Compute the cover-only Pairs-of-Values (PoV) imbalance per carrier source.

Falsifying test for the chi^2-spatial reversal mechanism (Eq. 1 of the final
report): for each cover image c, count its grayscale histogram h[0..255] and
compute

    S(c) = sum_{k=0..127} | h[2k] - h[2k+1] |

The mechanistic claim is that ML carriers have systematically lower S than
real photographs (smoother tone curves => more balanced adjacent-value pair
counts). We compute S per cover, then plot per-source distributions.

Outputs:
  - runs/<id>/metrics/pov_imbalance.csv          (per-image S, source, group_id)
  - runs/<id>/metrics/pov_imbalance_summary.json (per-source mean/median/IQR)
  - runs/<id>/figures/pov_imbalance_hist.png     (overlaid density plot)
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image
import pandas as pd
import matplotlib.pyplot as plt


def pov_imbalance(img: Image.Image) -> int:
    arr = np.asarray(img.convert("L")).ravel()
    counts = np.bincount(arr, minlength=256)
    pairs = counts.reshape(128, 2)
    return int(np.abs(pairs[:, 0] - pairs[:, 1]).sum())


def main(run_dir: Path) -> None:
    covers_root = run_dir / "covers"
    rows = []
    for src in ("real", "ml_a", "ml_b"):
        files = sorted((covers_root / src).glob("*.png"))
        print(f"  {src}: {len(files)} covers")
        for f in files:
            try:
                gid = int(f.name.split("__")[0].lstrip("g"))
            except (ValueError, IndexError):
                gid = -1
            with Image.open(f) as im:
                S = pov_imbalance(im)
            rows.append({"source": src, "group_id": gid, "pov_imbalance": S})
    df = pd.DataFrame(rows)
    out_csv = run_dir / "metrics" / "pov_imbalance.csv"
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(df)} rows)")

    # Per-source summary
    summary = {}
    for src in ("real", "ml_a", "ml_b"):
        s = df[df.source == src]["pov_imbalance"]
        summary[src] = {
            "n": int(s.shape[0]),
            "mean": float(s.mean()),
            "median": float(s.median()),
            "p10": float(s.quantile(0.10)),
            "p90": float(s.quantile(0.90)),
            "std": float(s.std()),
        }
    # Paired Welch t-test summary (one-sided: real > ml)
    from scipy import stats
    pair_results = {}
    real_vals = df[df.source == "real"].sort_values("group_id")["pov_imbalance"].values
    for src in ("ml_a", "ml_b"):
        ml_vals = df[df.source == src].sort_values("group_id")["pov_imbalance"].values
        n = min(len(real_vals), len(ml_vals))
        t_stat, p_two = stats.ttest_rel(real_vals[:n], ml_vals[:n])
        # one-sided p that real > ml
        p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
        d = (real_vals[:n] - ml_vals[:n]).mean() / (real_vals[:n] - ml_vals[:n]).std()
        pair_results[f"real_vs_{src}"] = {
            "n_pairs": int(n),
            "mean_diff": float((real_vals[:n] - ml_vals[:n]).mean()),
            "t": float(t_stat),
            "p_two_sided": float(p_two),
            "p_one_sided_real_gt_ml": float(p_one),
            "cohens_dz": float(d),
        }
    summary["paired_tests"] = pair_results
    out_json = run_dir / "metrics" / "pov_imbalance_summary.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {out_json}")
    print(json.dumps(summary, indent=2))

    # Overlaid histogram (matplotlib for diagnostic; the report uses a clean TikZ version)
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = {"real": "#001C3D", "ml_a": "#4A90C4", "ml_b": "#E84E10"}
    bins = np.linspace(df["pov_imbalance"].quantile(0.005), df["pov_imbalance"].quantile(0.995), 80)
    for src in ("real", "ml_a", "ml_b"):
        s = df[df.source == src]["pov_imbalance"]
        ax.hist(s, bins=bins, alpha=0.45, label=f"{src} (median {s.median():,.0f})", color=colors[src], density=True)
    ax.set_xlabel("PoV imbalance  $S = \\sum_k |n_{2k}-n_{2k+1}|$")
    ax.set_ylabel("density")
    ax.set_title("Cover-only PoV imbalance per carrier source ($N$=3{,}000 each)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "figures" / "pov_imbalance_hist.png", dpi=150)
    print("Wrote pov_imbalance_hist.png")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", type=Path)
    args = p.parse_args()
    main(args.run_dir)

"""Shared helpers for the tile-local chi^2-DCT validation experiments.

This module is NOT part of the main analysis pipeline.  It lives under
``scripts/experiments/tiled_chi2_validation/`` and is loaded only by the
five experiment runners in the same directory.

What it provides
----------------

* :func:`tiled_chi2_score` -- a generalised version of
  :func:`src.detection.chi_square_dct_tiled.chi_square_dct_tiled_score`
  with two extra knobs the production detector hardcodes:

    - ``tiles``: tile-grid size T (production default = 2)
    - ``pool``: one of ``"max"``, ``"mean"``, ``"median"``, ``"topk_mean"``
      (production default = ``"max"``)

  These are the levers Experiments 1, 2 and 3 sweep over.

* :func:`enumerate_dct_test_cells` -- iterator over the existing test
  corpus that yields (group_id, source, method, payload_level, encryption,
  cover_path, stego_path) tuples, restricted to ``method='dct'`` so the
  tile-local detector applies.  Used by every experiment to score the
  same fixed set of test cells.

* :func:`compute_auc_per_cell` -- given a per-row (label, score) DataFrame
  with stratification columns, compute one ROC-AUC per stratum.  Uses the
  numpy-vectorised metrics module from the main pipeline (so AUC values
  here are directly comparable to the v4 paper's classical-detector AUCs).

* :func:`write_results` -- standard output writer: a CSV under
  ``runs/tiled_validation/<exp_id>/results.csv`` plus a single PNG figure
  rendered via :mod:`matplotlib` in the v4 paper's brand colour palette.

Run any experiment with

    venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp1_tsweep [options]

Each script's ``--help`` documents its CLI; defaults reproduce the
configuration cited in the paper.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Literal

import numpy as np

# Local-pipeline imports (resolved by adding the project root to sys.path
# in each experiment runner before importing this module).
from src.detection.chi_square_dct import _build_pairs, _count_ac_frequencies
from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg
from src.evaluation.metrics import pe_min as _pe_min, roc_auc_score_binary


PoolName = Literal["max", "mean", "median", "topk_mean"]


# ---------------------------------------------------------------------------
# Detector: generalised tile-local Westfeld chi^2-DCT
# ---------------------------------------------------------------------------

_AC_MASK_8x8: np.ndarray | None = None


def tiled_chi2_score(
    jpeg_bytes: bytes,
    *,
    tiles: int = 2,
    pool: PoolName = "max",
    topk: int = 3,
) -> float:
    """Score a JPEG with the generalised tile-local Westfeld chi^2 test.

    Parameters
    ----------
    jpeg_bytes : raw JPEG file bytes.
    tiles : int
        Tile-grid size T.  T=1 recovers the global Westfeld chi^2 (a single
        tile covers the whole image).  T=2 matches the production detector.
        Higher T gives finer spatial localisation at the cost of fewer
        coefficients per tile.
    pool : {"max", "mean", "median", "topk_mean"}
        How to aggregate the per-tile scores into a single image-level score.
        "max" matches the production detector.  "mean" tests whether
        heterogeneity averages out (the global null).  "median" is the
        robust counterpart of "mean".  "topk_mean" is the mean of the top-K
        tile scores; equivalent to "max" when K=1, equivalent to "mean"
        when K=T^2.  Default K=3.
    topk : int
        K for the "topk_mean" pool.  Ignored otherwise.

    Returns
    -------
    float
        Image-level score.  Higher = stronger stego evidence.  Returns 0.0
        when no tile yields enough paired coefficients to form a valid
        chi^2 test (e.g. extremely flat image).
    """
    if tiles < 1:
        raise ValueError(f"tiles must be >= 1, got {tiles}")
    if pool not in ("max", "mean", "median", "topk_mean"):
        raise ValueError(f"unknown pool: {pool!r}")

    jpeg_struct = read_dct_jpeg(jpeg_bytes)
    dct = luminance_coefficients(jpeg_struct)  # (Bh, Bw, 8, 8)

    global _AC_MASK_8x8
    if _AC_MASK_8x8 is None:
        mask = np.ones((8, 8), dtype=bool)
        mask[0, 0] = False
        _AC_MASK_8x8 = mask

    bh, bw = dct.shape[:2]
    if bh == 0 or bw == 0:
        return 0.0

    per_tile: list[float] = []
    for ti in range(tiles):
        r0, r1 = (bh * ti) // tiles, (bh * (ti + 1)) // tiles
        if r0 == r1:
            continue
        for tj in range(tiles):
            c0, c1 = (bw * tj) // tiles, (bw * (tj + 1)) // tiles
            if c0 == c1:
                continue
            tile = dct[r0:r1, c0:c1]
            ac = tile[..., _AC_MASK_8x8].ravel()
            ac = ac[ac != 0]
            if ac.size == 0:
                continue
            frequencies = _count_ac_frequencies(ac.astype(int, copy=False))
            pairs = _build_pairs(frequencies)
            if not pairs:
                continue
            chi_stat = 0.0
            pair_count = 0
            for n_lower, n_upper in pairs:
                total = n_lower + n_upper
                if total == 0:
                    continue
                expected = total / 2.0
                chi_stat += ((n_lower - expected) ** 2) / expected
                pair_count += 1
            if pair_count <= 1:
                continue
            per_tile.append(-float(chi_stat) / (pair_count - 1))

    if not per_tile:
        return 0.0

    if pool == "max":
        return max(per_tile)
    if pool == "mean":
        return float(np.mean(per_tile))
    if pool == "median":
        return float(np.median(per_tile))
    # topk_mean
    k = max(1, min(topk, len(per_tile)))
    return float(np.mean(sorted(per_tile, reverse=True)[:k]))


# ---------------------------------------------------------------------------
# Sliding-window variant (Experiment 4: literature-precedent comparison)
# ---------------------------------------------------------------------------

def sliding_chi2_score(
    jpeg_bytes: bytes,
    *,
    window: int = 4,
    stride: int = 2,
    pool: PoolName = "max",
    topk: int = 3,
) -> float:
    """Sliding-window Westfeld chi^2 over overlapping windows of DCT blocks.

    Approximates the sliding-window variant suggested by Westfeld &
    Pfitzmann (1999) for sequential payloads.  Windows are ``window x
    window`` DCT-block boxes with stride ``stride`` (in DCT blocks); a
    Westfeld chi^2 is computed within each, and the image-level score is
    the configured ``pool`` over the per-window scores.
    """
    if window < 1 or stride < 1:
        raise ValueError(f"window and stride must be >= 1, got {window}/{stride}")
    if pool not in ("max", "mean", "median", "topk_mean"):
        raise ValueError(f"unknown pool: {pool!r}")

    jpeg_struct = read_dct_jpeg(jpeg_bytes)
    dct = luminance_coefficients(jpeg_struct)
    global _AC_MASK_8x8
    if _AC_MASK_8x8 is None:
        mask = np.ones((8, 8), dtype=bool)
        mask[0, 0] = False
        _AC_MASK_8x8 = mask
    bh, bw = dct.shape[:2]
    if bh < window or bw < window:
        return 0.0

    per_win: list[float] = []
    for r0 in range(0, bh - window + 1, stride):
        for c0 in range(0, bw - window + 1, stride):
            tile = dct[r0:r0 + window, c0:c0 + window]
            ac = tile[..., _AC_MASK_8x8].ravel()
            ac = ac[ac != 0]
            if ac.size == 0:
                continue
            frequencies = _count_ac_frequencies(ac.astype(int, copy=False))
            pairs = _build_pairs(frequencies)
            if not pairs:
                continue
            chi_stat = 0.0
            pair_count = 0
            for n_lower, n_upper in pairs:
                total = n_lower + n_upper
                if total == 0:
                    continue
                expected = total / 2.0
                chi_stat += ((n_lower - expected) ** 2) / expected
                pair_count += 1
            if pair_count <= 1:
                continue
            per_win.append(-float(chi_stat) / (pair_count - 1))

    if not per_win:
        return 0.0
    if pool == "max":
        return max(per_win)
    if pool == "mean":
        return float(np.mean(per_win))
    if pool == "median":
        return float(np.median(per_win))
    k = max(1, min(topk, len(per_win)))
    return float(np.mean(sorted(per_win, reverse=True)[:k]))


# ---------------------------------------------------------------------------
# Test-corpus iteration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestCell:
    """One scoring task: a (cover, stego) JPEG pair in a (method, payload, source, encryption) cell."""
    group_id: int
    source: str
    method: str           # always "dct" for tile-local chi^2 experiments
    payload_level: str    # low / medium / high
    encryption: str       # plain / encrypted
    cover_path: Path      # the JPEG cover (frequency variant)
    stego_path: Path      # the matching JPEG stego


def enumerate_dct_test_cells(
    run_dir: Path,
    *,
    payload_levels: Iterable[str] = ("low", "medium", "high"),
    encryptions: Iterable[str] = ("plain", "encrypted"),
    sources: Iterable[str] = ("real", "ml_a", "ml_b"),
    max_cells_per_strata: int | None = None,
) -> Iterator[TestCell]:
    """Yield DCT-method (cover, stego) JPEG pairs from a completed test run.

    Walks ``run_dir/stego/dct/{payload}/{encryption}/{source}/g*.jpg`` and
    pairs each stego with its cover at ``run_dir/covers/{source}/g*.jpg``.
    Cells with a missing cover or stego file are silently skipped.

    Parameters
    ----------
    max_cells_per_strata : int | None
        If set, cap the number of yielded cells in any one
        (payload, encryption, source) stratum.  Useful for quick smoke
        tests before running the full evaluation.
    """
    stego_root = run_dir / "stego" / "dct"
    covers_root = run_dir / "covers"
    for payload in payload_levels:
        for encryption in encryptions:
            for source in sources:
                stego_dir = stego_root / payload / encryption / source
                cover_dir = covers_root / source
                if not stego_dir.is_dir() or not cover_dir.is_dir():
                    continue
                yielded = 0
                for stego in sorted(stego_dir.glob("g*__src-*__m-dct__p-*__e-*.jpg")):
                    gid_str = stego.name.split("__")[0].lstrip("g")
                    try:
                        gid = int(gid_str)
                    except ValueError:
                        continue
                    cover = cover_dir / f"g{gid:04d}__src-{source}.jpg"
                    if not cover.exists():
                        continue
                    yield TestCell(
                        group_id=gid,
                        source=source,
                        method="dct",
                        payload_level=payload,
                        encryption=encryption,
                        cover_path=cover,
                        stego_path=stego,
                    )
                    yielded += 1
                    if max_cells_per_strata and yielded >= max_cells_per_strata:
                        break


# ---------------------------------------------------------------------------
# Scoring + AUC
# ---------------------------------------------------------------------------

def _score_one_cell(args: tuple) -> list[dict]:
    """Worker for parallel scoring.  Top-level so spawn-mode workers can
    pickle it.  Returns the two-row payload (cover + stego) for one cell.

    ``score_fn`` must itself be pickleable: top-level callables and
    ``functools.partial`` wrappers around top-level callables both work,
    but lambdas and closures do not.
    """
    cell, score_fn = args
    cover_bytes = cell.cover_path.read_bytes()
    stego_bytes = cell.stego_path.read_bytes()
    cover_score = score_fn(cover_bytes)
    stego_score = score_fn(stego_bytes)
    rows = []
    for path, label, score in (
        (cell.cover_path, 0, cover_score),
        (cell.stego_path, 1, stego_score),
    ):
        rows.append({
            "group_id": cell.group_id,
            "source": cell.source,
            "method": cell.method,
            "payload_level": cell.payload_level,
            "encryption": cell.encryption,
            "label": label,
            "score": score,
        })
    return rows


def score_cells(
    cells: Iterable[TestCell],
    score_fn: Callable[[bytes], float],
    *,
    n_workers: int = 1,
    progress_every: int = 500,
) -> list[dict]:
    """Score every (cover, stego) pair in ``cells`` and return per-row records.

    Each emitted record is one row with columns
    ``(group_id, source, method, payload_level, encryption, label, score)``
    where ``label`` is 0 for the cover and 1 for the stego.  Two rows per
    cell.

    When ``n_workers > 1`` the scoring runs in a multiprocessing-spawn pool
    of that size.  ``score_fn`` MUST then be pickleable: top-level callables
    and ``functools.partial(top_level_callable, **kwargs)`` both work;
    lambdas and closure-captured functions do NOT.  The serial path
    (n_workers=1) accepts any callable.

    Per-cell wall-clock is dominated by JPEG decoding + the per-tile
    chi-square statistic, both pure CPU; on a 16-core box the parallel
    speedup is essentially linear up to n_workers~16, after which the
    JPEG-decode I/O starts to share-cap the workers.
    """
    cells_list = list(cells)
    n_total = len(cells_list)
    out: list[dict] = []

    if n_workers <= 1:
        # Serial path: identical behaviour to pre-parallel versions.
        for i, cell in enumerate(cells_list, start=1):
            out.extend(_score_one_cell((cell, score_fn)))
            if progress_every and i % progress_every == 0:
                print(f"  scored {i}/{n_total} cells ({2 * i} rows so far)")
        return out

    # Parallel path.
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    work = [(cell, score_fn) for cell in cells_list]
    print(f"  scoring {n_total} cells with {n_workers} workers ...")
    with ctx.Pool(n_workers) as pool:
        for i, rows in enumerate(
            pool.imap_unordered(_score_one_cell, work, chunksize=16),
            start=1,
        ):
            out.extend(rows)
            if progress_every and i % progress_every == 0:
                print(f"  scored {i}/{n_total} cells ({2 * i} rows so far)")
    return out


def compute_metrics_per_cell(
    rows: list[dict],
    *,
    strata: tuple[str, ...] = ("method", "payload_level", "encryption", "source"),
) -> list[dict]:
    """Aggregate per-row (label, score) records into per-stratum metric entries.

    Each output row has columns:
      - the stratification keys (e.g. method, payload_level, ...)
      - n_pos, n_neg          : class counts
      - auc                   : ROC area-under-curve (chance = 0.5, perfect = 1.0)
      - pe_min                : minimum total detection error (Fridrich/DCTR convention,
                                chance = 0.5, perfect = 0.0)

    Strata with fewer than 2 of either class are skipped.
    """
    buckets: dict[tuple, list[tuple[int, float]]] = defaultdict(list)
    for r in rows:
        key = tuple(r[s] for s in strata)
        buckets[key].append((int(r["label"]), float(r["score"])))

    out: list[dict] = []
    for key, items in sorted(buckets.items()):
        labels = [y for y, _ in items]
        scores = [s for _, s in items]
        n_pos = sum(1 for y in labels if y == 1)
        n_neg = sum(1 for y in labels if y == 0)
        if n_pos < 2 or n_neg < 2:
            continue
        try:
            auc = roc_auc_score_binary(labels, scores)
        except ValueError:
            continue
        pe = _pe_min(labels, scores)
        entry = {s: v for s, v in zip(strata, key)}
        entry.update({
            "n_pos": n_pos,
            "n_neg": n_neg,
            "auc": float(auc),
            "pe_min": float(pe),
        })
        out.append(entry)
    return out


# Backwards-compatible alias: the original name remains so existing
# experiment scripts continue to import compute_auc_per_cell.  The
# implementation now also reports pe_min, but callers that only access
# the "auc" column see no behaviour change.
compute_auc_per_cell = compute_metrics_per_cell


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict]) -> None:
    """Standard CSV writer.  Uses the union of all row keys as the field set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("(empty)\n")
        return
    fieldnames: list[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# v4 paper's brand-colour palette (matches src/evaluation/plots.py THEME).
PALETTE = {
    "umdark": "#001C3D",
    "umlight": "#4A90C4",
    "umorange": "#E84E10",
    "umgray": "#6B7280",
}


def palette_for_payloads(payload_levels: Iterable[str]) -> dict[str, str]:
    """Return a colour per payload level for plotting.

    For the canonical three-level ``low/medium/high`` axis (the main paper's
    convention) the brand palette is used so figures match the rest of the
    paper.  For arbitrary N (e.g. the six-level ``p005..p050`` axis the
    BOSSBase importer emits), a graduated ``plasma`` sample is returned so
    ordered payload sweeps render as a perceptually uniform gradient.
    """
    levels = list(payload_levels)
    if levels == ["low", "medium", "high"]:
        return {"low": PALETTE["umdark"],
                "medium": PALETTE["umlight"],
                "high": PALETTE["umorange"]}
    import matplotlib.cm as cm
    import matplotlib.colors as mc
    cmap = cm.get_cmap("plasma")
    n = max(len(levels), 1)
    return {p: mc.to_hex(cmap((i + 0.5) / n)) for i, p in enumerate(levels)}


def configure_matplotlib_for_paper() -> None:
    """Match the v4 paper figure style (Latin Modern serif, gray grid, umdark text)."""
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Latin Modern Roman", "CMU Serif", "DejaVu Serif", "serif"],
        "mathtext.fontset": "cm",
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelcolor": PALETTE["umdark"],
        "axes.edgecolor": PALETTE["umdark"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#E5E7EB",
        "grid.linewidth": 0.6,
        "xtick.color": PALETTE["umdark"],
        "ytick.color": PALETTE["umdark"],
        "legend.frameon": False,
        "figure.facecolor": "white",
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })


# ---------------------------------------------------------------------------
# Dual-metric plotting convention
# ---------------------------------------------------------------------------
#
# Every experiment runner emits two figures with parallel filenames -- one
# keyed on ROC-AUC, one keyed on P_E^min -- so the results can be read by
# both the AUC-reporting modern literature (our v4 paper, recent learned
# detectors) and the P_E / E_OOB-reporting Fridrich-lab classical-detector
# lineage (Westfeld 1999, Fridrich 2001 RS, Fridrich 2003 calibration-chi^2,
# Holub & Fridrich 2015 DCTR).  ``METRICS`` is the canonical list of
# (column, axis_label, lower_is_better) tuples plot helpers iterate over.

METRICS: list[tuple[str, str, bool]] = [
    ("auc", "ROC-AUC (higher is better)", False),
    ("pe_min", r"$P_E^{\min}$ (lower is better)", True),
]


def apply_metric_axis_style(ax, metric: str) -> None:
    """Apply axis label + y-limits + chance-line for ``metric`` in METRICS.

    Both metric plots use the natural orientation (smaller y at bottom)
    with a dashed chance line at 0.5; the y-axis label carries the
    'higher/lower is better' directionality.  Bar charts therefore render
    consistently in both metric variants: short bars = bad detector for
    AUC, short bars = good detector for P_E^min.
    """
    if metric == "auc":
        ax.set_ylim(0.45, 1.02)
        ax.axhline(0.5, color=PALETTE["umgray"], linestyle=":", linewidth=0.6,
                   label="_nolegend_")
    elif metric == "pe_min":
        ax.set_ylim(0.0, 0.55)
        ax.axhline(0.5, color=PALETTE["umgray"], linestyle=":", linewidth=0.6,
                   label="_nolegend_")


def ensure_project_root_on_sys_path() -> Path:
    """Add the project root to sys.path so ``from src...`` imports resolve.

    Returns the project-root Path.  Each experiment runner calls this at
    the top of ``main()`` so the runners are launchable from anywhere.
    """
    import sys
    here = Path(__file__).resolve().parent
    root = here.parents[2]  # scripts/experiments/tiled_chi2_validation/ -> repo root
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root

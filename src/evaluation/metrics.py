from __future__ import annotations

"""Metric utilities for detector prediction tables."""

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class BinaryMetrics:
    n_samples: int
    n_pos: int
    n_neg: int
    roc_auc: float
    eer: float
    accuracy_at_youden_j: float
    fpr_at_fixed_fnr: float


def _average_ranks(values: list[float]) -> list[float]:
    """Return average ranks (1-based) with tie handling."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def roc_auc_score_binary(labels: list[int], scores: list[float]) -> float:
    """Compute binary ROC-AUC using the rank-based formulation."""
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have the same length")
    if not labels:
        raise ValueError("labels must not be empty")

    n_pos = sum(1 for y in labels if y == 1)
    n_neg = sum(1 for y in labels if y == 0)
    if n_pos == 0 or n_neg == 0:
        raise ValueError("ROC-AUC requires both positive and negative labels")

    ranks = _average_ranks(scores)
    sum_pos_ranks = sum(r for r, y in zip(ranks, labels) if y == 1)
    auc = (sum_pos_ranks - (n_pos * (n_pos + 1) / 2.0)) / (n_pos * n_neg)
    return float(auc)


def _roc_points(labels: list[int], scores: list[float]) -> list[tuple[float, float, float, float]]:
    """Return (threshold, tpr, fpr, fnr) points over score thresholds.

    Implemented with numpy sort + cumsum (O(n log n)).  The earlier pure-Python
    nested-loop version was O(n^2) in unique scores and became the bottleneck of
    compute_metrics_from_predictions for large prediction tables (108k+ samples
    per detector took 10+ minutes per group).  Output format is preserved
    exactly: one (threshold, tpr, fpr, fnr) tuple per unique score plus a
    boundary point above the maximum and below the minimum, all in descending
    threshold order.
    """
    if not scores:
        return []

    scores_arr = np.asarray(scores, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)

    n_pos = int((labels_arr == 1).sum())
    n_neg = int((labels_arr == 0).sum())

    # Sort by score descending; on ties we still recover the right cumulative
    # counts at each unique threshold by collapsing on the score boundary below.
    order = np.argsort(-scores_arr, kind="mergesort")
    scores_desc = scores_arr[order]
    labels_desc = labels_arr[order]

    # tp_cum[k] = #positives in the top-(k+1) by score; fp_cum[k] analogous.
    tp_cum = np.cumsum(labels_desc == 1)
    fp_cum = np.cumsum(labels_desc == 0)

    # Pick the last index of each unique score (i.e. once we've crossed the
    # entire equal-score run) so the (tp, fp) counts include every tied sample.
    unique_boundary = np.r_[np.flatnonzero(np.diff(scores_desc) != 0),
                            len(scores_desc) - 1]
    unique_thresholds = scores_desc[unique_boundary]
    tp_at_unique = tp_cum[unique_boundary]
    fp_at_unique = fp_cum[unique_boundary]

    # Prepend the "predict nothing" extreme (threshold above max -> tp=fp=0)
    # and append the "predict everything" extreme (threshold below min ->
    # tp=n_pos, fp=n_neg) to mirror the original helper's behaviour.
    thresholds = np.r_[unique_thresholds[0] + 1.0,
                       unique_thresholds,
                       unique_thresholds[-1] - 1.0]
    tp_arr = np.r_[0, tp_at_unique, n_pos]
    fp_arr = np.r_[0, fp_at_unique, n_neg]

    tpr = tp_arr / n_pos if n_pos else np.zeros_like(tp_arr, dtype=np.float64)
    fpr = fp_arr / n_neg if n_neg else np.zeros_like(fp_arr, dtype=np.float64)
    fnr = 1.0 - tpr if n_pos else np.zeros_like(tpr)

    return list(zip(thresholds.tolist(), tpr.tolist(), fpr.tolist(), fnr.tolist()))


def eer_score(labels: list[int], scores: list[float]) -> float:
    """Compute EER as the midpoint where |FPR-FNR| is minimal."""
    points = _roc_points(labels, scores)
    thr, tpr, fpr, fnr = min(points, key=lambda x: abs(x[2] - x[3]))
    _ = (thr, tpr)
    return (fpr + fnr) / 2.0


def accuracy_at_youden_j(labels: list[int], scores: list[float]) -> float:
    """Compute accuracy at threshold maximizing Youden's J = TPR - FPR."""
    points = _roc_points(labels, scores)
    best_thr, _, _, _ = max(points, key=lambda x: x[1] - x[2])

    correct = 0
    for y, s in zip(labels, scores):
        pred = 1 if s >= best_thr else 0
        correct += int(pred == y)
    return correct / len(labels)


def fpr_at_fixed_fnr(labels: list[int], scores: list[float], target_fnr: float = 0.10) -> float:
    """Compute FPR at threshold whose FNR is closest to target_fnr."""
    points = _roc_points(labels, scores)
    _, _, fpr, _ = min(points, key=lambda x: abs(x[3] - target_fnr))
    return fpr


def compute_binary_metrics(
    labels: list[int],
    scores: list[float],
    *,
    target_fnr: float = 0.10,
) -> BinaryMetrics:
    n_pos = sum(1 for y in labels if y == 1)
    n_neg = sum(1 for y in labels if y == 0)

    return BinaryMetrics(
        n_samples=len(labels),
        n_pos=n_pos,
        n_neg=n_neg,
        roc_auc=roc_auc_score_binary(labels, scores),
        eer=eer_score(labels, scores),
        accuracy_at_youden_j=accuracy_at_youden_j(labels, scores),
        fpr_at_fixed_fnr=fpr_at_fixed_fnr(labels, scores, target_fnr=target_fnr),
    )


def try_parse_score(value: str) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(score) or math.isinf(score):
        return None
    return score


def aggregate_by_groups(
    rows: list[dict[str, str]],
    group_keys: list[str],
    *,
    target_fnr: float = 0.10,
) -> list[dict[str, object]]:
    """Aggregate metrics by arbitrary group keys over prediction rows."""
    grouped: dict[tuple[str, ...], list[tuple[int, float]]] = {}
    for row in rows:
        score = try_parse_score(row.get("score", ""))
        if score is None:
            continue
        label = int(row["label"])
        key = tuple(row[k] for k in group_keys)
        grouped.setdefault(key, []).append((label, score))

    out: list[dict[str, object]] = []
    for key, items in grouped.items():
        labels = [y for y, _ in items]
        scores = [s for _, s in items]
        if len(set(labels)) < 2:
            # Undefined AUC without both classes.
            continue
        metrics = compute_binary_metrics(labels, scores, target_fnr=target_fnr)
        row: dict[str, object] = {k: v for k, v in zip(group_keys, key)}
        row.update(
            {
                "n_samples": metrics.n_samples,
                "n_pos": metrics.n_pos,
                "n_neg": metrics.n_neg,
                "roc_auc": metrics.roc_auc,
                "eer": metrics.eer,
                "accuracy_at_youden_j": metrics.accuracy_at_youden_j,
                "fpr_at_fixed_fnr": metrics.fpr_at_fixed_fnr,
            }
        )
        out.append(row)

    out.sort(key=lambda r: tuple(str(r[k]) for k in group_keys))
    return out


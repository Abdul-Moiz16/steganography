from __future__ import annotations

"""Metric utilities for detector prediction tables."""

from dataclasses import dataclass
import math
from typing import Iterable


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
    """Return (threshold, tpr, fpr, fnr) points over score thresholds."""
    thresholds = sorted(set(scores), reverse=True)
    if thresholds:
        thresholds = [thresholds[0] + 1.0] + thresholds + [thresholds[-1] - 1.0]

    n_pos = sum(1 for y in labels if y == 1)
    n_neg = sum(1 for y in labels if y == 0)

    points: list[tuple[float, float, float, float]] = []
    for thr in thresholds:
        tp = fp = tn = fn = 0
        for y, s in zip(labels, scores):
            pred_pos = s >= thr
            if y == 1 and pred_pos:
                tp += 1
            elif y == 1 and not pred_pos:
                fn += 1
            elif y == 0 and pred_pos:
                fp += 1
            else:
                tn += 1

        tpr = tp / n_pos if n_pos else 0.0
        fpr = fp / n_neg if n_neg else 0.0
        fnr = fn / n_pos if n_pos else 0.0
        points.append((thr, tpr, fpr, fnr))
    return points


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


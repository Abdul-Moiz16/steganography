from __future__ import annotations

from src.evaluation.metrics import (
    accuracy_at_youden_j,
    aggregate_by_groups,
    compute_binary_metrics,
    eer_score,
    fpr_at_fixed_fnr,
    roc_auc_score_binary,
)


def test_binary_metric_functions_perfect_separation() -> None:
    labels = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]

    assert roc_auc_score_binary(labels, scores) == 1.0
    assert eer_score(labels, scores) == 0.0
    assert accuracy_at_youden_j(labels, scores) == 1.0
    assert fpr_at_fixed_fnr(labels, scores, target_fnr=0.1) == 0.0

    metrics = compute_binary_metrics(labels, scores)
    assert metrics.roc_auc == 1.0
    assert metrics.n_pos == 2
    assert metrics.n_neg == 2


def test_aggregate_by_groups() -> None:
    rows = [
        {
            "detector": "rs",
            "source": "real",
            "label": "0",
            "score": "0.1",
        },
        {
            "detector": "rs",
            "source": "real",
            "label": "1",
            "score": "0.9",
        },
        {
            "detector": "chi_square_spatial",
            "source": "real",
            "label": "0",
            "score": "0.2",
        },
        {
            "detector": "chi_square_spatial",
            "source": "real",
            "label": "1",
            "score": "0.8",
        },
    ]

    agg = aggregate_by_groups(rows, ["detector", "source"])
    assert len(agg) == 2
    assert all(r["roc_auc"] == 1.0 for r in agg)

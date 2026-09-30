"""Inference-time dense-confidence gate for experimental E020 reranking."""

import numpy as np

from benchmark.e020_ranker import rank_top50

MEASURES = ("top1_top2", "top1_top10", "top10_top11")


def margins(dense):
    values = np.asarray(dense, dtype=np.float64)
    if len(values) < 11 or not np.isfinite(values).all():
        raise ValueError("at least 11 finite dense scores are required")
    top = np.sort(values)[-11:][::-1]
    return {"top1_top2": float(top[0] - top[1]),
            "top1_top10": float(top[0] - top[9]),
            "top10_top11": float(top[9] - top[10])}


def gated_order(query, ids, corpus, dense, idf, mean, scale, coef, measure, threshold, enabled=True):
    if measure not in MEASURES or not np.isfinite(threshold):
        raise ValueError("invalid gate")
    confidence = margins(dense)[measure]
    triggered = bool(enabled and confidence <= threshold)
    if triggered:
        return rank_top50(query, ids, corpus, dense, idf, mean, scale, coef, depth=50), True
    return np.argsort(-np.asarray(dense), kind="stable").tolist(), False

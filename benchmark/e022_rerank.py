"""Experimental pure cross-encoder ordering of frozen dense top-50 candidates."""

import numpy as np


def input_pairs(query, doc_ids, corpus):
    return [(query, corpus[d]) for d in doc_ids]


def rerank(query, ids, corpus, dense, model, depth=50, batch_size=8, enabled=True):
    dense = np.asarray(dense, dtype=np.float64)
    if len(dense) != len(ids) or len(set(ids)) != len(ids) or not np.isfinite(dense).all():
        raise ValueError("invalid dense candidate set")
    base = np.argsort(-dense, kind="stable")
    if not enabled:
        return base.tolist()
    if depth != 50 or batch_size < 1:
        raise ValueError("E022 depth is fixed at 50 and batch size must be positive")
    top = base[:depth]
    pairs = input_pairs(query, [ids[i] for i in top], corpus)
    scores = np.asarray(model.predict(pairs, batch_size=batch_size, show_progress_bar=False), dtype=np.float64).reshape(-1)
    if len(scores) != len(top) or not np.isfinite(scores).all():
        raise ValueError("invalid joint relevance scores")
    result = top[np.argsort(-scores, kind="stable")].tolist() + base[depth:].tolist()
    assert len(result) == len(ids) and len(set(result)) == len(ids)
    return result

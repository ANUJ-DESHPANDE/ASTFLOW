import numpy as np
import pytest

from benchmark.e020_ranker import FEATURES
from benchmark.e021_gate import gated_order, margins


def fixture_inputs(close=True):
    ids = [str(i) for i in range(11)]
    corpus = {i: "other" for i in ids}
    corpus["1"] = "alpha"
    dense = np.array([0.8, 0.799 if close else 0.5] + [0.4 - i * 0.01 for i in range(9)])
    coef = np.zeros(len(FEATURES))
    coef[1] = 10
    return ("alpha", ids, corpus, dense, {}, np.zeros(len(FEATURES)),
            np.ones(len(FEATURES)), coef, "top1_top2", 0.01)


def test_high_confidence_and_disabled_gate_preserve_dense_exactly():
    args = fixture_inputs(close=False)
    order, triggered = gated_order(*args)
    assert not triggered
    assert order == np.argsort(-args[3], kind="stable").tolist()
    order2, triggered2 = gated_order(*fixture_inputs(close=True), enabled=False)
    assert not triggered2
    assert order2 == np.argsort(-fixture_inputs(close=True)[3], kind="stable").tolist()


def test_near_tie_invokes_deterministic_reranker_without_changing_candidate_set():
    args = fixture_inputs(close=True)
    first, triggered = gated_order(*args)
    second, triggered2 = gated_order(*args)
    assert triggered and triggered2 and first == second
    assert first[0] == 1
    assert len(first) == len(set(first)) == len(args[1])
    assert set(first) == set(range(len(args[1])))


def test_ties_are_stable_and_nonfinite_scores_rejected():
    args = list(fixture_inputs(close=True))
    args[3][1] = args[3][0]
    args[7][:] = 0
    order, triggered = gated_order(*args)
    assert triggered and order[:2] == [0, 1]
    args[3][1] = float("nan")
    with pytest.raises(ValueError):
        margins(args[3])
    with pytest.raises(ValueError):
        gated_order(*args)

import numpy as np
import pytest

from benchmark.e020_ranker import FEATURES, features, normalize_identifier, rank_top50


def test_identifier_normalization_and_missing_metadata():
    assert normalize_identifier("getUserToken") == ("get", "user", "token")
    assert normalize_identifier("validate_token") == ("validate", "token")
    value = features("getUserToken 100", None, 0.5, {})
    assert len(value) == len(FEATURES) and np.isfinite(value).all()


def test_ranker_is_stable_and_preserves_candidates():
    ids = ["a", "b", "c", "d"]
    corpus = {"a": "validate_token", "b": "getUserToken", "c": "", "d": "other"}
    dense = np.array([0.8, 0.8, 0.4, 0.3])
    args = ("get user token", ids, corpus, dense, {}, np.zeros(len(FEATURES)),
            np.ones(len(FEATURES)), np.array([1., 0., 0., 0., 0., 0., 0.]))
    first = rank_top50(*args, depth=3)
    assert first == rank_top50(*args, depth=3)
    assert first == [0, 1, 2, 3]
    assert len(first) == len(set(first)) == len(ids)


def test_nonfinite_input_rejected():
    with pytest.raises(ValueError):
        features("q", "d", float("nan"), {})
    with pytest.raises(ValueError):
        rank_top50("q", ["a"], {"a": "d"}, [float("inf")], {},
                   np.zeros(len(FEATURES)), np.ones(len(FEATURES)), np.ones(len(FEATURES)))

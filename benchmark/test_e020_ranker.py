import numpy as np
import pytest
import hashlib
import json
from pathlib import Path

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


def test_pinned_model_schema_and_reproducible_inference():
    root = Path(__file__).parent / "results" / "E020-hard-negative-ranking"
    payload = (root / "model.json").read_bytes()
    prereg = json.loads((root / "preregister.json").read_text())
    model = json.loads(payload)
    # The preregistered artifact used CRLF; Git checks it out with LF on Linux.
    canonical_payload = payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    assert hashlib.sha256(canonical_payload).hexdigest() == prereg["model_sha256"]
    assert tuple(model["features"]) == FEATURES
    arrays = [np.asarray(model[k], dtype=float) for k in ("mean", "scale", "coef")]
    assert all(np.isfinite(a).all() and len(a) == len(FEATURES) for a in arrays)
    assert (arrays[1] > 0).all() and arrays[2][0] > 0
    args = ("sort list", ["a", "b"], {"a": "sort(a)", "b": "reverse(a)"},
            [0.5, 0.4], {}, *arrays)
    assert rank_top50(*args) == rank_top50(*args)

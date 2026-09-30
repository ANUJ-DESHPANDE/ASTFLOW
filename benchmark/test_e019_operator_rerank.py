import numpy as np

from backend.app.retrieval.operator_evidence import rerank_operator_evidence


def test_operator_evidence_only_changes_matching_dense_candidates():
    ids = ["a", "b", "c"]
    corpus = {"a": "print(x)", "b": "answer = x ^ y", "c": "answer = x ^ y"}
    dense = np.array([0.51, 0.50, 0.10])
    result = rerank_operator_evidence("find xor", ids, corpus, dense, depth=2, boost=0.02)
    assert result.tolist() == [0.51, 0.52, 0.10]
    assert dense.tolist() == [0.51, 0.50, 0.10]


def test_no_operator_mentioned_preserves_ranking():
    dense = np.array([0.51, 0.50])
    result = rerank_operator_evidence("find the answer", ["a", "b"],
                                      {"a": "x ^ y", "b": "print(x)"}, dense)
    assert np.array_equal(result, dense)

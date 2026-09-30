import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmark.e022_rerank import input_pairs, rerank


class FakeModel:
    def predict(self, pairs, batch_size, show_progress_bar):
        assert batch_size > 0 and show_progress_bar is False
        return [float(len(document)) for _, document in pairs]


def fixture_data():
    ids = [str(i) for i in range(52)]
    corpus = {d: ("x" * (i % 4)) for i, d in enumerate(ids)}
    dense = np.asarray([1 - i / 100 for i in range(52)])
    return ids, corpus, dense


def test_joint_input_and_stable_candidate_set():
    ids, corpus, dense = fixture_data()
    assert input_pairs("q", ids[:2], corpus) == [("q", ""), ("q", "x")]
    first = rerank("q", ids, corpus, dense, FakeModel())
    assert first == rerank("q", ids, corpus, dense, FakeModel(), batch_size=1)
    assert first == rerank("q", ids, corpus, dense, FakeModel(), batch_size=16)
    assert first[:2] == [3, 7]  # equal relevance ties follow the original dense order
    assert first[-2:] == [50, 51]
    assert len(first) == len(set(first)) == len(ids)
    assert set(first) == set(range(len(ids)))


def test_disabled_is_exact_dense_and_nonfinite_rejected():
    ids, corpus, dense = fixture_data()
    assert rerank("q", ids, corpus, dense, FakeModel(), enabled=False) == list(range(len(ids)))
    dense[1] = float("nan")
    with pytest.raises(ValueError):
        rerank("q", ids, corpus, dense, FakeModel())
    class BadModel:
        def predict(self, pairs, **kwargs):
            return [float("inf")] * len(pairs)
    dense[1] = 0.99
    with pytest.raises(ValueError):
        rerank("q", ids, corpus, dense, BadModel())


def test_model_artifact_pinned():
    root = Path(__file__).parent / "results" / "E022-strong-reranker"
    record = json.loads((root / "feasibility.json").read_text())
    # The recorded source path is anonymized for publication. Locate the same
    # revision in this machine's Hugging Face cache when the historical model is available.
    weight = (Path.home() / ".cache" / "huggingface" / "hub"
              / ("models--" + record["model"].replace("/", "--"))
              / "snapshots" / record["revision"] / "model.safetensors")
    if not weight.is_file():
        pytest.skip("Historical E022 model is not installed on this machine")
    assert hashlib.sha256(weight.read_bytes()).hexdigest() == record["weight_sha256"]

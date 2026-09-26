import math
from pathlib import Path

import numpy as np
import pytest

from backend.app.config import ROOT, Settings
from backend.app.indexing.service import IndexService
from backend.app.retrieval.embeddings import Embedder
from benchmark.metrics import metrics


def test_metrics_graded_order_duplicates_and_missing():
    relevance = {"a": 3, "b": 1}
    perfect = metrics(["a", "a", "b"], relevance)
    assert perfect == {"ndcg@10": 1., "mrr": 1., "recall@10": 1.}
    partial = metrics(["x", "b"], relevance)
    assert partial["mrr"] == .5 and partial["recall@10"] == .5
    assert 0 < partial["ndcg@10"] < 1
    assert metrics([], relevance)["mrr"] == 0


def test_actual_cpu_semantic_retrieval_and_persisted_vectors(tmp_path):
    pytest.importorskip("sentence_transformers", reason="Optional semantic dependencies are not installed")
    base = Settings()
    if not (base.cache / "models" / base.model.replace("/", "--") / "modules.json").exists():
        pytest.skip("Install the CPU model with astflow model-download for semantic integration testing")
    # Share model assets, isolate the index and its registry from application state.
    service = IndexService(Settings(cache=tmp_path / "cache", ts_enrich=False))
    service.embedder = Embedder(base)
    index = service.index(str(ROOT / "examples/demo-repo"))
    assert index.manifest["semantic"]["available"]
    rows, diagnostics = index.retriever.rank("Trim extra whitespace and lowercase spoken commands", mode="dense", boosts=False)
    assert diagnostics["semantic_available"]
    assert rows[0]["chunk"].qualified_name == "normalizeInput"
    embeddings = index.retriever.embeddings
    # Unit length (float32 on CPU; the float16 checkpoint dtype gave deviations up to 4e-4).
    assert np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-3)
    again = IndexService(service.settings)
    assert np.array_equal(again.get().retriever.embeddings, embeddings)

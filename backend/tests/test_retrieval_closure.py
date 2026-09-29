"""Cheap guard for the accepted retrieval configuration and dense ranking path."""

import numpy as np

from backend.app.config import FROZEN_MODEL, FROZEN_MODEL_REVISION, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import PRECISION, THREADS, physical_cores, profile, thread_limit
from backend.app.retrieval.search import Retriever


class QueryEmbedder:
    def encode(self, texts, kind="query"):
        assert texts == ["apple"] and kind == "query"
        return np.asarray([[1., 0.]], dtype=np.float32)


def test_accepted_defaults_and_safe_thread_override(monkeypatch):
    for name in ("ASTFLOW_MODEL", "ASTFLOW_SEMANTIC", "ASTFLOW_RETRIEVAL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.model == FROZEN_MODEL == "Alibaba-NLP/gte-modernbert-base"
    assert FROZEN_MODEL_REVISION.startswith("e7f32e3c")
    assert settings.retrieval == "dense" and settings.semantic == "on"
    assert settings.candidates == 1000 and settings.frozen
    assert profile(settings.model)["max_seq"] == 512 and PRECISION == "float32"
    assert 1 <= THREADS <= min(8, physical_cores())
    monkeypatch.setenv("ASTFLOW_THREADS", "bad")
    assert thread_limit() == min(8, physical_cores())
    monkeypatch.setenv("ASTFLOW_THREADS", "1000")
    assert thread_limit() == physical_cores()


def test_dense_order_ignores_bm25_and_has_no_experimental_reranker():
    chunks = [Chunk("a", "a", "a.js", "banana", "function", 1, 1, "banana", "banana", "a"),
              Chunk("b", "b", "b.js", "apple", "function", 1, 1, "apple", "apple", "b")]
    vectors = np.asarray([[1., 0.], [.6, .8]], dtype=np.float32)
    retriever = Retriever(chunks, vectors, QueryEmbedder(), Settings(ts_enrich=False))
    rows, evidence = retriever.rank("apple", mode="dense", boosts=False, limit=2)
    assert [r["chunk"].chunk_id for r in rows] == ["a", "b"]
    assert evidence["semantic_available"] is True
    assert rows[1]["evidence"]["lexical_score"] > rows[0]["evidence"]["lexical_score"]
    assert all(r["evidence"]["contributions"]["lexical"] == 0 for r in rows)
    assert all(r["evidence"]["contributions"]["structural"] == 0 for r in rows)

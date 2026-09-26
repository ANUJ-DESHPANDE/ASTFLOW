"""The product runs the frozen retrieval configuration by default and never falls back to it silently."""
import hashlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.investigate import investigate
from backend.app.config import FROZEN_MODEL, FROZEN_RETRIEVAL, ROOT, Settings
from backend.app.indexing.service import IndexService
from backend.app.main import create_app
from backend.app.retrieval.embeddings import ModelUnavailable
from backend.app.retrieval.search import tokenize

DEMO = str(ROOT / "examples/demo-repo")


class BagOfWordsEmbedder:
    """Deterministic stand-in for the CPU model: hashed bag of words, L2-normalised."""

    def __init__(self, settings):
        self.settings, self.model, self.reason, self.calls = settings, object(), f"{settings.model} loaded on CPU", []

    def load(self, download=False):
        return self.model

    @property
    def status(self):
        return {"available": True, "model": self.settings.model, "message": self.reason}

    def encode(self, texts, kind="document", **_):
        self.calls.append(kind)
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                out[row, int(hashlib.sha256(token.encode()).hexdigest(), 16) % 256] += 1
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def test_defaults_are_the_frozen_submission_configuration(monkeypatch):
    for name in ("ASTFLOW_MODEL", "ASTFLOW_SEMANTIC", "ASTFLOW_RETRIEVAL"):
        monkeypatch.delenv(name, raising=False)
    import importlib
    import backend.app.config as config
    fresh = importlib.reload(config).Settings()
    assert (fresh.model, fresh.retrieval, fresh.semantic) == (FROZEN_MODEL, FROZEN_RETRIEVAL, "on")
    assert FROZEN_MODEL == "Alibaba-NLP/gte-modernbert-base" and FROZEN_RETRIEVAL == "dense" and fresh.frozen
    importlib.reload(config)


def test_invalid_settings_fail_loudly():
    with pytest.raises(ValueError):
        Settings(retrieval="rerank")
    with pytest.raises(ValueError):
        Settings(semantic="maybe")


def test_missing_model_is_an_actionable_error_not_a_lexical_fallback(tmp_path):
    # An empty cache and no download: the model cannot load.
    service = IndexService(Settings(cache=tmp_path / "cache", ts_enrich=False))
    with pytest.raises(ModelUnavailable, match="model-download"):
        service.index(DEMO)
    assert service.status["state"] == "error" and "npm run setup" in service.status["stage"]
    client = TestClient(create_app(Settings(cache=tmp_path / "cache2", ts_enrich=False)))
    reply = client.post("/api/index", json={"repo_path": DEMO, "background": False})
    assert reply.status_code == 503 and "ASTFLOW_SEMANTIC=off" in reply.json()["detail"]


def test_search_ranks_with_the_configured_dense_first_stage_and_reports_it(tmp_path):
    settings = Settings(cache=tmp_path / "cache", ts_enrich=False)
    service = IndexService(settings)
    service.embedder = BagOfWordsEmbedder(settings)
    index = service.index(DEMO)
    assert index.manifest["retrieval"] == {"model": FROZEN_MODEL, "mode": "dense", "model_loaded": True, "device": "cpu",
                                           "frozen_submission_configuration": True,
                                           "message": f"{FROZEN_MODEL} loaded on CPU"}
    index.retriever.embedder = service.embedder
    found = investigate(index, "Where is Bluetooth settings handled?", "working-tree")
    assert found["retrieval"]["ranking"] == "dense" and found["retrieval"]["model"] == FROZEN_MODEL
    assert found["retrieval"]["index_model"] == FROZEN_MODEL
    search = [s for s in found["agent_trace"] if s["step"] == "SEARCH"][0]
    assert f"{FROZEN_MODEL} dense" in search["details"] and search["data"]["ranking"] == "dense"
    # Dense first stage: BM25 is recorded as evidence but contributes nothing to the score.
    assert all(r["evidence"]["contributions"].get("lexical", 0) == 0 for r in found["results"])
    assert "query" in service.embedder.calls


def test_health_names_the_running_configuration(tmp_path):
    frozen = TestClient(create_app(Settings(cache=tmp_path / "a", ts_enrich=False))).get("/api/health").json()
    assert frozen["retrieval"]["model"] == FROZEN_MODEL and frozen["retrieval"]["mode"] == "dense"
    assert frozen["retrieval"]["frozen_submission_configuration"] is True
    lexical = TestClient(create_app(Settings(cache=tmp_path / "b", semantic="off", ts_enrich=False)))
    assert lexical.post("/api/index", json={"repo_path": DEMO, "background": False}).status_code == 200
    health = lexical.get("/api/health").json()
    assert health["retrieval"]["model"] is None and health["retrieval"]["mode"].startswith("bm25")
    assert health["retrieval"]["frozen_submission_configuration"] is False
    assert health["indexed_versions"]["working-tree"]["embedding_model"] is None
    found = lexical.post("/api/search", json={"query": "Bluetooth settings"}).json()
    assert found["retrieval"]["ranking"] == "hybrid" and found["retrieval"]["model"] is None
    assert "lexical only" in [s for s in found["agent_trace"] if s["step"] == "SEARCH"][0]["details"]

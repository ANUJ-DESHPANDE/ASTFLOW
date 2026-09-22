"""Regression coverage for the dense-retrieval collapse root cause: precompute_embeddings.py
built its saved apps_fixed.npy in corpus.jsonl file order, while mteb_appretrieval.py built its
own chunk list in a *different* order (sorted by document id) and loaded that array positionally.
For any corpus whose file order isn't already id-sorted, embeddings[i] ended up paired with the
wrong document, so dense similarity degenerated to noise (measured NDCG@10 = 0.0010 on the full
3,765-query AppsRetrieval run; see docs/audit/DENSE-REGRESSION-INVESTIGATION.md).

These tests use a fake Embedder (no network, no real model) so they run in any environment.
"""
import csv
import json

import numpy as np
import pytest

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from benchmark import mteb_appretrieval, precompute_embeddings

DIM = 8


def _signal_vector(text: str) -> np.ndarray:
    """Deterministic 'embedding': a one-hot vector keyed by the SIGNAL_<n> marker in the text."""
    vec = np.zeros(DIM, dtype=np.float32)
    for token in text.split():
        if token.startswith("SIGNAL_"):
            vec[int(token.removeprefix("SIGNAL_")) % DIM] = 1.0
            return vec
    return vec


def _fake_encode(self, texts, use_windows=False, window_size=256, overlap=64):
    vectors = [np.expand_dims(_signal_vector(t), 0) for t in texts]  # each doc: exactly 1 "window"
    return vectors if use_windows else np.asarray([v[0] for v in vectors], dtype=np.float32)


@pytest.fixture
def fake_embedder(monkeypatch):
    monkeypatch.setattr(Embedder, "load", lambda self, download=False: setattr(self, "model", object()) or self.model)
    monkeypatch.setattr(Embedder, "encode", _fake_encode)


def _write_export(directory, doc_order):
    """doc_order: list of (doc_id, signal_n) written to corpus.jsonl in exactly that order.
    Query qN's only relevant document is dN, so correct alignment must rank dN first for qN."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "corpus.jsonl").open("w") as f:
        for doc_id, n in doc_order:
            f.write(json.dumps({"_id": doc_id, "title": "", "text": f"SIGNAL_{n} filler filler filler"}) + "\n")
    with (directory / "queries.jsonl").open("w") as f:
        for _, n in doc_order:
            f.write(json.dumps({"_id": f"q{n}", "text": f"looking for SIGNAL_{n}"}) + "\n")
    (directory / "qrels").mkdir(exist_ok=True)
    with (directory / "qrels" / "test.tsv").open("w", newline="") as f:
        writer = csv.DictWriter(f, ["query-id", "corpus-id", "score"], delimiter="\t")
        writer.writeheader()
        for doc_id, n in doc_order:
            writer.writerow({"query-id": f"q{n}", "corpus-id": doc_id, "score": 1})


# Corpus file order is deliberately NOT sorted by document id, exactly like the real
# CoIR-Retrieval/apps corpus.jsonl export (HF dataset row order != lexicographic _id order).
SHUFFLED_ORDER = [("d3", 3), ("d1", 1), ("d4", 4), ("d0", 0), ("d2", 2)]


def test_fixed_embeddings_realign_by_id_not_position(tmp_path, fake_embedder, monkeypatch):
    cache_dir = tmp_path / "cache"
    export_dir = tmp_path / "export"
    _write_export(export_dir, SHUFFLED_ORDER)
    # precompute_embeddings.py reads its corpus from settings.cache/datasets/apps/corpus.jsonl
    (cache_dir / "datasets" / "apps").mkdir(parents=True)
    (cache_dir / "datasets" / "apps" / "corpus.jsonl").write_text((export_dir / "corpus.jsonl").read_text())

    fixed_settings = Settings(cache=cache_dir)
    monkeypatch.setattr(precompute_embeddings, "Settings", lambda: fixed_settings)
    monkeypatch.setattr(mteb_appretrieval, "Settings", lambda: fixed_settings)

    precompute_embeddings.precompute()
    assert (cache_dir / "datasets" / "apps_fixed.npy").exists()
    assert (cache_dir / "datasets" / "apps_fixed.meta.json").exists()

    report = mteb_appretrieval.evaluate_export(export_dir, "test", 0, tmp_path / "out")

    # With correct id-based realignment, every query's one relevant document (matching SIGNAL_n)
    # scores a perfect dot product (1.0) and nothing else does, so ranking is exact.
    assert report["baselines"]["dense"]["ndcg@10"] == 1.0
    assert report["baselines"]["dense"]["recall@10"] == 1.0


def test_fixed_cache_without_id_metadata_is_rejected_not_silently_misaligned(tmp_path, fake_embedder, monkeypatch):
    """A legacy apps_fixed.npy saved without the companion id metadata (the pre-fix format)
    must fail loudly rather than being loaded positionally against a differently-ordered
    chunk list, which is exactly the bug that produced NDCG@10 = 0.0010."""
    cache_dir = tmp_path / "cache"
    export_dir = tmp_path / "export"
    _write_export(export_dir, SHUFFLED_ORDER)

    fixed_settings = Settings(cache=cache_dir)
    monkeypatch.setattr(mteb_appretrieval, "Settings", lambda: fixed_settings)

    # Simulate the OLD precompute_embeddings.py output: a bare object array, no *.meta.json.
    (cache_dir / "datasets").mkdir(parents=True)
    embedder = Embedder(fixed_settings)
    embedder.load()
    legacy_embeddings = embedder.encode([f"SIGNAL_{n} filler filler filler" for _, n in SHUFFLED_ORDER], use_windows=True)
    np.save(cache_dir / "datasets" / "apps_fixed.npy", np.asarray(legacy_embeddings, dtype=object))

    with pytest.raises(ValueError, match="companion"):
        mteb_appretrieval.evaluate_export(export_dir, "test", 0, tmp_path / "out")


def test_fixed_cache_rejects_mismatched_document_ids(tmp_path, fake_embedder, monkeypatch):
    cache_dir = tmp_path / "cache"
    export_dir = tmp_path / "export"
    _write_export(export_dir, SHUFFLED_ORDER)

    fixed_settings = Settings(cache=cache_dir)
    monkeypatch.setattr(mteb_appretrieval, "Settings", lambda: fixed_settings)

    (cache_dir / "datasets").mkdir(parents=True)
    embedder = Embedder(fixed_settings)
    embedder.load()
    embeddings = embedder.encode(["SIGNAL_0 x", "SIGNAL_1 x"], use_windows=True)
    np.save(cache_dir / "datasets" / "apps_fixed.npy", np.asarray(embeddings, dtype=object))
    (cache_dir / "datasets" / "apps_fixed.meta.json").write_text(json.dumps({
        "ids": ["d0", "d1"], "model": fixed_settings.model, "window_size": 256, "overlap": 64,
    }))

    with pytest.raises(ValueError, match="missing embeddings"):
        mteb_appretrieval.evaluate_export(export_dir, "test", 0, tmp_path / "out")

"""End-to-end plumbing tests for benchmark/verify_retrieval.py on a tiny synthetic export.

These prove the pipeline (integrity -> ranking -> freeze -> cross-evaluate -> forensics
-> manifest) is wired correctly. They are NOT AppsRetrieval measurements.
"""
import argparse
import csv
import hashlib
import json
import re

import numpy as np
import pytest

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from benchmark import verify_retrieval
from benchmark.trust.integrity import IntegrityError

TOPICS = ["sort array ascending", "database connection retry", "resize image thumbnail", "parse json string"]


def _vec(text):
    v = np.zeros(32, dtype=np.float32)
    for tok in re.findall(r"[a-z]+", text.lower()):
        v[int(hashlib.sha256(tok.encode()).hexdigest(), 16) % 32] += 1
    return v / (np.linalg.norm(v) or 1)


def _export(tmp_path, duplicate=False):
    d = tmp_path / "apps"
    (d / "qrels").mkdir(parents=True)
    rows = [{"_id": f"d{i}", "title": "", "text": f"def f{i}():\n    # {TOPICS[i % 4]}\n    return {i}"} for i in range(40)]
    if duplicate:
        rows.append(dict(rows[0]))
    (d / "corpus.jsonl").write_text("\n".join(json.dumps(r) for r in reversed(rows)) + "\n")
    (d / "queries.jsonl").write_text("\n".join(json.dumps({"_id": f"q{t}", "text": f"how to {TOPICS[t]}"}) for t in range(4)) + "\n")
    with (d / "qrels" / "test.tsv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["query-id", "corpus-id", "score"], delimiter="\t")
        w.writeheader()
        for t in range(4):
            w.writerow({"query-id": f"q{t}", "corpus-id": f"d{t}", "score": 1})
    (d / "metadata.json").write_text(json.dumps({"revision": verify_retrieval.EXPECTED_DATASET_REVISION}))
    return d


def _args(tmp_path, data, modes):
    return argparse.Namespace(data=str(data), out=str(tmp_path / "out"), split="all", modes=modes, max_queries=0,
                              tag="t", trec_eval=None, allow_unknown_revision=False,
                              skip_published_count_check=True)  # synthetic data is not the real corpus


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_retrieval, "Settings", lambda **kw: Settings(cache=tmp_path / "cache", **kw))


def test_bm25_pipeline_end_to_end(tmp_path, isolated_cache):
    assert verify_retrieval.full_run(_args(tmp_path, _export(tmp_path), "bm25")) == 0
    manifest = json.loads((tmp_path / "out" / "manifest-t.json").read_text())
    assert manifest["dataset"]["documents"] == 40 and manifest["dataset"]["judged_queries"] == 4
    assert manifest["evaluators"]["bm25"]["agree"] is True
    assert set(manifest["evaluators"]["bm25"]["aggregates"]) >= {"reference", "astflow", "pytrec_eval", "ir_measures"}
    assert (tmp_path / "out" / "runs" / "t-bm25.trec").exists()


def test_dense_and_hybrid_pipeline_with_injected_encoder(tmp_path, isolated_cache, monkeypatch):
    monkeypatch.setattr(Embedder, "load", lambda self, download=False: setattr(self, "model", object()) or self.model)
    monkeypatch.setattr(Embedder, "encode", lambda self, texts, **kw: np.stack([_vec(t) for t in texts]))
    monkeypatch.setattr(verify_retrieval, "model_identity", lambda e, s: {"name": "fake-bow", "weights_sha256": None})
    assert verify_retrieval.full_run(_args(tmp_path, _export(tmp_path), "bm25,dense,hybrid")) == 0
    m = json.loads((tmp_path / "out" / "manifest-t.json").read_text())
    assert m["vectors"]["alignment_probe"]["min_cosine"] > 0.999
    assert m["vectors"]["rows"] == 40
    assert set(m["forensics"]["oracle_ceiling_hybrid"]) == {"top10", "top20", "top50", "top100", "top500", "top1000"}
    assert all(m["evaluators"][mode]["agree"] for mode in ("bm25", "dense", "hybrid"))


def test_duplicate_corpus_ids_fail_loudly(tmp_path, isolated_cache):
    with pytest.raises(IntegrityError, match="Duplicate corpus ids"):
        verify_retrieval.full_run(_args(tmp_path, _export(tmp_path, duplicate=True), "bm25"))


def test_wrong_dataset_revision_fails_loudly(tmp_path, isolated_cache):
    data = _export(tmp_path)
    (data / "metadata.json").write_text(json.dumps({"revision": "something-else"}))
    with pytest.raises(IntegrityError, match="revision"):
        verify_retrieval.full_run(_args(tmp_path, data, "bm25"))


def test_published_count_check_rejects_wrong_corpus(tmp_path, isolated_cache):
    args = _args(tmp_path, _export(tmp_path), "bm25")
    args.skip_published_count_check = False
    if verify_retrieval.mteb_published_stats() is None:
        pytest.skip("mteb not installed")
    with pytest.raises(IntegrityError, match="MTEB"):
        verify_retrieval.full_run(args)


def test_self_test_passes():
    assert verify_retrieval.self_test(None) is True

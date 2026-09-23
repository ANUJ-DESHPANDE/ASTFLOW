"""The offline analyzer must work from committed artifacts alone. These tests build a
synthetic verification run with the real pipeline (injected encoder, no network), then
analyze it. Synthetic data must be flagged as NOT the real corpus."""
import json

import numpy as np
import pytest

from backend.app.retrieval.embeddings import Embedder
from benchmark import analyze_baseline, verify_retrieval
from benchmark.test_verify_retrieval import _args, _export, _vec, isolated_cache  # noqa: F401


@pytest.fixture
def synthetic_run(tmp_path, isolated_cache, monkeypatch):  # noqa: F811
    monkeypatch.setattr(Embedder, "load", lambda self, download=False: setattr(self, "model", object()) or self.model)
    monkeypatch.setattr(Embedder, "encode", lambda self, texts, **kw: np.stack([_vec(t) for t in texts]))
    monkeypatch.setattr(verify_retrieval, "model_identity", lambda e, s: {"name": "fake-bow", "weights_sha256": None})
    args = _args(tmp_path, _export(tmp_path), "bm25,dense,hybrid")
    assert verify_retrieval.full_run(args) == 0
    verification = tmp_path / "out"
    (tmp_path / "benchmark" / "results").mkdir(parents=True)
    monkeypatch.setattr(analyze_baseline, "VERIFICATION", verification)
    monkeypatch.setattr(analyze_baseline, "ROOT", tmp_path)
    return verification


def test_pack_rebuilds_identical_runs_and_analysis_uses_packed_files(synthetic_run):
    analyze_baseline.pack("t")
    for trec in (synthetic_run / "runs").glob("*.trec"):
        trec.unlink()  # prove the analysis works from the small committable files alone
    out = analyze_baseline.analyze("t")
    checks = out["trust"]["checks"]
    for mode in ("bm25", "dense", "hybrid"):
        assert checks[f"{mode} run checksum matches manifest"]["detail"].startswith("ranks/")
        assert checks[f"{mode}: evaluators agree (this machine)"]["ok"]
        assert checks[f"{mode}: NDCG@10 reproduces benchmark-machine value"]["ok"]
    assert checks["hybrid is exactly RRF of the frozen BM25 and Dense runs"]["ok"], checks


def test_synthetic_data_is_flagged_as_not_the_real_benchmark(synthetic_run):
    out = analyze_baseline.analyze("t")
    assert "8,765 documents" in out["trust"]["problems"]
    assert out["bottleneck"]["verdict"] == "MEASUREMENT"


def test_oracle_equals_hit_rate_with_one_relevant_document(synthetic_run):
    out = analyze_baseline.analyze("t")
    for mode, ceilings in out["oracle_ceiling"].items():
        for k, value in ceilings.items():
            assert value == pytest.approx(out["cumulative_hit_rate"][mode][k])


def test_tampered_run_is_rejected(synthetic_run):
    run = synthetic_run / "runs" / "t-dense.trec"
    lines = run.read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    run.write_text("\n".join(lines) + "\n")
    with pytest.raises(AssertionError, match="checksum"):
        analyze_baseline.analyze("t")


def test_reports_are_written(synthetic_run, tmp_path):
    analyze_baseline.analyze("t")
    results = tmp_path / "benchmark" / "results"
    assert "Oracle reranking ceiling" in (results / "retrieval_forensics-t.md").read_text()
    data = json.loads((results / "retrieval_forensics-t.json").read_text())
    assert data["bottleneck"]["rule_version"] == "BOTTLENECK_RULES_V1"
    assert (results / "first-relevant-rank-t.tsv").read_text().startswith("query\tbm25\tdense\thybrid")

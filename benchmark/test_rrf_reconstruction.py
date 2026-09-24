"""Deterministic tests proving RRF implementation and reconstruction from frozen runs."""
import pytest
from pathlib import Path
from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks, rrf


def test_rrf_formula_toy_case():
    """Verify exact formula: score = w_lex / (k + rank_bm25) + w_sem / (k + rank_dense)."""
    # Query 1: doc A is rank 1 in BM25, doc B is rank 2
    # In Dense: doc B is rank 1, doc A is rank 2
    bm25 = {"q1": ["docA", "docB"]}
    dense = {"q1": ["docB", "docA"]}

    # Equal weights, k=60:
    # docA score = 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.0163934 + 0.0161290 = 0.0325224
    # docB score = 1/(60+2) + 1/(60+1) = 0.0325224
    # Tie broken by doc ID ascending: docA before docB
    fused_equal = rrf(bm25, dense, k=60, w_lex=1.0, w_sem=1.0)
    assert fused_equal["q1"] == ["docA", "docB"]

    # BM25 favored (w_lex=2.0, w_sem=1.0):
    # docA score = 2/61 + 1/62 = 0.0327868 + 0.0161290 = 0.0489158
    # docB score = 2/62 + 1/61 = 0.0322580 + 0.0163934 = 0.0486514
    # docA > docB
    fused_bm25 = rrf(bm25, dense, k=60, w_lex=2.0, w_sem=1.0)
    assert fused_bm25["q1"] == ["docA", "docB"]

    # Dense favored (w_lex=1.0, w_sem=2.0):
    # docA score = 1/61 + 2/62 = 0.0163934 + 0.0322580 = 0.0486514
    # docB score = 1/62 + 2/61 = 0.0161290 + 0.0327868 = 0.0489158
    # docB > docA
    fused_dense = rrf(bm25, dense, k=60, w_lex=1.0, w_sem=2.0)
    assert fused_dense["q1"] == ["docB", "docA"]


def test_frozen_baseline_v1_rrf_exact_reconstruction():
    """Verify that RRF(k=60, 1:1, depth=1000) identically reconstructs baseline-v1-hybrid."""
    ranks_dir = ROOT / "benchmark" / "verification" / "ranks"
    bm25_file = ranks_dir / "baseline-v1-bm25.ranks.tsv.gz"
    dense_file = ranks_dir / "baseline-v1-dense.ranks.tsv.gz"
    hybrid_file = ranks_dir / "baseline-v1-hybrid.ranks.tsv.gz"

    if not (bm25_file.exists() and dense_file.exists() and hybrid_file.exists()):
        pytest.skip("Frozen baseline-v1 ranks not found")

    bm25 = load_ranks(bm25_file)
    dense = load_ranks(dense_file)
    hybrid_expected = load_ranks(hybrid_file)

    reconstructed = rrf(bm25, dense, k=60, w_lex=1.0, w_sem=1.0, depth=1000)

    assert set(reconstructed.keys()) == set(hybrid_expected.keys())
    assert len(reconstructed) == 3765

    mismatches = 0
    for qid in hybrid_expected:
        if reconstructed[qid] != hybrid_expected[qid]:
            mismatches += 1

    assert mismatches == 0, f"{mismatches} / 3765 queries had differing rankings"

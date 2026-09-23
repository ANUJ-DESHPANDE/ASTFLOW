"""Golden tests for the frozen evaluation protocol (benchmark/trust/evaluation.py).

Each case has an answer that can be worked out by hand. Every available evaluator
must produce it: the readable reference, ASTFLOW's benchmark/metrics.py,
pytrec_eval (the engine MTEB uses), ir_measures, and NIST trec_eval when built.
"""
import math
import random

import pytest

from benchmark.trust.evaluation import cross_check, find_trec_eval, write_qrels, write_run


def score(tmp_path, rankings, qrels):
    run_path, qrels_path = tmp_path / "run.trec", tmp_path / "qrels.txt"
    write_run(rankings, run_path)
    write_qrels(qrels, qrels_path)
    return cross_check(rankings, qrels, run_path, qrels_path)


def test_case1_relevant_at_rank_one_is_perfect(tmp_path):
    report = score(tmp_path, {"q1": ["a", "b", "c"]}, {"q1": {"a": 1}})
    assert report["agree"], report["disagreements"]
    assert report["evaluators"]["reference"]["ndcg@10"] == 1.0
    assert report["evaluators"]["reference"]["mrr@10"] == 1.0


def test_case2_relevant_document_absent_scores_zero(tmp_path):
    report = score(tmp_path, {"q1": ["b", "c"]}, {"q1": {"a": 1}})
    assert report["agree"], report["disagreements"]
    assert report["evaluators"]["reference"]["ndcg@10"] == 0.0


def test_case3_lower_rank_scores_lower(tmp_path):
    report = score(tmp_path, {"q1": ["b", "c", "a"]}, {"q1": {"a": 1}})
    assert report["agree"], report["disagreements"]
    assert report["evaluators"]["reference"]["ndcg@10"] == pytest.approx(1 / math.log2(4))
    assert report["evaluators"]["reference"]["mrr@10"] == pytest.approx(1 / 3)


def test_case4_graded_relevance_uses_linear_gain(tmp_path):
    # trec_eval gain = grade: DCG = 1/1 + 2/log2(3); IDCG = 2/1 + 1/log2(3)
    qrels = {"q1": {"a": 2, "b": 1}}
    report = score(tmp_path, {"q1": ["b", "a"]}, qrels)
    expected = (1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3))
    assert report["evaluators"]["reference"]["ndcg@10"] == pytest.approx(expected)
    assert report["evaluators"]["pytrec_eval"]["ndcg@10"] == pytest.approx(expected)
    # benchmark/metrics.py uses 2**grade - 1 and therefore differs on graded qrels only.
    assert report["evaluators"]["astflow"]["ndcg@10"] != pytest.approx(expected)
    assert report["agree"], report["disagreements"]


def test_case5_query_with_no_results_counts_as_zero(tmp_path):
    report = score(tmp_path, {"q1": ["a"], "q2": []}, {"q1": {"a": 1}, "q2": {"x": 1}})
    assert report["agree"], report["disagreements"]
    for name, agg in report["evaluators"].items():
        assert agg["ndcg@10"] == pytest.approx(0.5), name


def test_case5b_mteb_style_averaging_only_drops_absent_query_keys():
    """MTEB 2.21 averages over queries pytrec_eval returns. An empty result dict is
    still scored (0); only an absent key is dropped. run_mteb.py writes every key."""
    import pytrec_eval
    evaluator = pytrec_eval.RelevanceEvaluator({"q1": {"a": 1}, "q2": {"x": 1}}, {"ndcg_cut.10"})
    mteb_mean = lambda s: sum(v["ndcg_cut_10"] for v in s.values()) / len(s)
    assert mteb_mean(evaluator.evaluate({"q1": {"a": 1.0}, "q2": {}})) == pytest.approx(0.5)
    assert mteb_mean(evaluator.evaluate({"q1": {"a": 1.0}})) == pytest.approx(1.0)  # inflation if key omitted


def test_case6_tied_raw_scores_are_resolved_by_final_rank(tmp_path):
    """Raw ties are ambiguous to trec_eval (it breaks them by docid descending);
    the canonical export encodes ASTFLOW's own order, so the result is fixed."""
    import pytrec_eval
    raw_tied = {"q1": {"a": 0.5, "z": 0.5}}
    tied = pytrec_eval.RelevanceEvaluator({"q1": {"a": 1}}, {"ndcg_cut.10"}).evaluate(raw_tied)
    assert tied["q1"]["ndcg_cut_10"] == pytest.approx(1 / math.log2(3))  # trec_eval put "z" first
    report = score(tmp_path, {"q1": ["a", "z"]}, {"q1": {"a": 1}})  # ASTFLOW order: a, z
    assert report["agree"], report["disagreements"]
    assert report["evaluators"]["pytrec_eval"]["ndcg@10"] == 1.0


def test_duplicate_documents_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        write_run({"q1": ["a", "a"]}, tmp_path / "run.trec")


def test_randomized_cross_evaluator_agreement(tmp_path):
    rng = random.Random(20260923)
    pool = [f"d{i}" for i in range(400)]
    rankings, qrels = {}, {}
    for q in range(250):
        qid = f"q{q}"
        qrels[qid] = {d: 1 for d in rng.sample(pool, rng.randint(1, 3))}
        qrels[qid].update({d: 0 for d in rng.sample(pool, 2) if d not in qrels[qid]})
        rankings[qid] = [] if q % 40 == 0 else rng.sample(pool, rng.randint(1, 120))
    report = score(tmp_path, rankings, qrels)
    assert report["agree"], report["disagreements"][:5]
    if find_trec_eval():
        assert "trec_eval" in report["evaluators"]
        printed = report["trec_eval_aggregate_as_printed"]["ndcg@10"]
        assert printed == pytest.approx(report["evaluators"]["reference"]["ndcg@10"], abs=5e-5)

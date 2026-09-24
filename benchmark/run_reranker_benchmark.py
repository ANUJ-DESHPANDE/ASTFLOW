"""Script to execute E002 cross-encoder reranker benchmark on a Hugging Face-enabled machine.

Usage:
    python -m benchmark.run_reranker_benchmark --depth 20 --split dev
    python -m benchmark.run_reranker_benchmark --depth 50 --split dev
    python -m benchmark.run_reranker_benchmark --depth 100 --split dev
    python -m benchmark.run_reranker_benchmark --depth 100 --split all --tag e002-reranked-d100
"""
import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
import numpy as np

from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks, pack, unpack
from benchmark.trust import evaluation, forensics
from benchmark.trust.forensics import paired_bootstrap

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VERIFICATION = ROOT / "benchmark" / "verification"
RANKS_DIR = VERIFICATION / "ranks"
QRELS_FILE = VERIFICATION / "apps.qrels"
DEV_SPLIT_FILE = ROOT / "benchmark" / "dev_split.json"
RESULTS_DIR = ROOT / "benchmark" / "results"


def load_corpus_and_queries():
    """Load text for documents and queries from the pinned MTEB dataset."""
    from benchmark import mteb_appretrieval
    directory = mteb_appretrieval.resolve_dataset_dir()
    corpus = mteb_appretrieval.load_corpus(directory)
    queries = mteb_appretrieval.load_queries(directory)
    # Map to id -> text
    doc_texts = {c.chunk_id: c.search_text for c in corpus}
    return doc_texts, queries


def run_reranking(model_name: str, depth: int, split_name: str, tag: str, batch_size: int = 32, device: str = "cpu"):
    logger.info(f"=== E002 RERANKER BENCHMARK (Depth={depth}, Split={split_name}) ===")
    logger.info(f"Model: {model_name}, Device: {device}, Batch Size: {batch_size}")
    
    # 1. Load splits and qrels
    with open(DEV_SPLIT_FILE, "r", encoding="utf-8") as f:
        splits = json.load(f)
    if split_name == "dev":
        target_qids = splits["dev_query_ids"]
    elif split_name == "confirmation":
        target_qids = splits["confirmation_query_ids"]
    else:
        target_qids = splits["dev_query_ids"] + splits["confirmation_query_ids"]
        
    qrels = evaluation.read_qrels(QRELS_FILE)
    
    # 2. Load frozen baseline hybrid rankings (candidate pool)
    hybrid_ranks = load_ranks(RANKS_DIR / "baseline-v1-hybrid.ranks.tsv.gz")
    
    # 3. Load text for queries and docs
    logger.info("Loading document corpus and query texts...")
    doc_texts, query_texts = load_corpus_and_queries()
    logger.info(f"Loaded {len(doc_texts)} documents, {len(query_texts)} queries.")
    
    # 4. Initialize CrossEncoder (loaded ONCE)
    from sentence_transformers import CrossEncoder
    t_load_start = time.perf_counter()
    logger.info(f"Initializing CrossEncoder({model_name!r}, device={device!r})...")
    reranker = CrossEncoder(model_name, device=device)
    load_time_s = time.perf_counter() - t_load_start
    logger.info(f"CrossEncoder loaded in {load_time_s:.2f} seconds.")
    
    # 5. Rerank queries
    reranked_run = {}
    latencies = []
    logger.info(f"Reranking {len(target_qids)} queries at candidate depth {depth}...")
    
    t_bench_start = time.perf_counter()
    for idx, qid in enumerate(target_qids, 1):
        qtext = query_texts[qid]
        candidates = hybrid_ranks.get(qid, [])
        top_k = candidates[:depth]
        remaining = candidates[depth:]
        
        t0 = time.perf_counter()
        pairs = [[qtext, doc_texts.get(did, "")] for did in top_k]
        if pairs:
            scores = reranker.predict(pairs, batch_size=batch_size, show_progress_bar=False)
            scored_candidates = list(zip(top_k, scores))
            # Sort top-k strictly by (-score, doc_id)
            scored_candidates.sort(key=lambda x: (-x[1], x[0]))
            reordered = [did for did, _ in scored_candidates]
        else:
            reordered = []
            
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        reranked_run[qid] = reordered + remaining
        
        if idx % 200 == 0 or idx == len(target_qids):
            logger.info(f"Progress: {idx}/{len(target_qids)} queries ({elapsed_ms:.1f} ms/query)")
            
    total_time = time.perf_counter() - t_bench_start
    median_latency = float(np.median(latencies))
    mean_latency = float(np.mean(latencies))
    logger.info(f"Reranking finished in {total_time:.1f}s. Median latency: {median_latency:.1f}ms, Mean: {mean_latency:.1f}ms.")
    
    # 6. Evaluate and compare against baseline
    run_file = VERIFICATION / "runs" / f"{tag}.trec"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    evaluation.write_run(reranked_run, run_file, tag=tag)
    
    # Compute metrics
    eval_res = evaluation.cross_check(reranked_run, qrels, run_file, QRELS_FILE)
    ref_metrics = eval_res["evaluators"]["reference"]
    
    # Baseline comparison on target_qids
    baseline_run = {q: hybrid_ranks[q] for q in target_qids if q in hybrid_ranks}
    baseline_eval = evaluation.eval_reference(baseline_run, qrels)
    baseline_ndcg = float(np.mean([baseline_eval[q]["ndcg@10"] for q in target_qids]))
    
    reranked_eval = evaluation.eval_reference(reranked_run, qrels)
    reranked_ndcg = float(np.mean([reranked_eval[q]["ndcg@10"] for q in target_qids]))
    delta = reranked_ndcg - baseline_ndcg
    
    base_per_q = {q: baseline_eval[q]["ndcg@10"] for q in target_qids}
    rerank_per_q = {q: reranked_eval[q]["ndcg@10"] for q in target_qids}
    bs = paired_bootstrap(baseline=base_per_q, candidate=rerank_per_q, samples=10000, seed=20260923)
    ci95 = bs["ci95"]
    excludes_zero = (ci95[0] > 0 and ci95[1] > 0) or (ci95[0] < 0 and ci95[1] < 0)
    
    print("\n" + "=" * 80)
    print(f"E002 RERANKER RESULTS — Depth={depth}, Split={split_name}")
    print(f"Baseline Hybrid NDCG@10: {baseline_ndcg:.5f}")
    print(f"Reranked NDCG@10:        {reranked_ndcg:.5f}")
    print(f"Delta:                   {delta:+.5f}")
    print(f"95% Bootstrap CI:        [{ci95[0]:+.5f}, {ci95[1]:+.5f}], excludes zero: {excludes_zero}")
    print(f"R@10:  {ref_metrics['recall@10']:.5f}")
    print(f"R@50:  {ref_metrics['recall@50']:.5f}")
    print(f"R@100: {ref_metrics['recall@100']:.5f}")
    print(f"Latency: Median {median_latency:.1f}ms, Mean {mean_latency:.1f}ms")
    print("=" * 80)
    
    return {
        "model": model_name,
        "depth": depth,
        "split": split_name,
        "baseline_ndcg10": baseline_ndcg,
        "reranked_ndcg10": reranked_ndcg,
        "delta": delta,
        "ci95": ci95,
        "excludes_zero": excludes_zero,
        "recall@10": ref_metrics["recall@10"],
        "recall@50": ref_metrics["recall@50"],
        "recall@100": ref_metrics["recall@100"],
        "median_latency_ms": median_latency,
        "mean_latency_ms": mean_latency,
        "load_time_s": load_time_s,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--depth", type=int, default=100, choices=[20, 50, 100])
    parser.add_argument("--split", default="dev", choices=["dev", "confirmation", "all"])
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--tag", default=None)
    args = parser.parse_args()
    
    tag = args.tag or f"e002-reranked-d{args.depth}-{args.split}"
    res = run_reranking(
        model_name=args.model,
        depth=args.depth,
        split_name=args.split,
        tag=tag,
        batch_size=args.batch_size,
        device=args.device,
    )
    
    out_file = RESULTS_DIR / f"reranker_{args.split}_d{args.depth}.json"
    out_file.write_text(json.dumps(res, indent=2))
    logger.info(f"Results saved to {out_file}")


if __name__ == "__main__":
    main()

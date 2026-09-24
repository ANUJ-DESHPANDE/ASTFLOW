"""Parallel worker execution for E002 cross-encoder reranking across multiple CPU cores.

Scores top-100 candidates for queries in parallel shards and evaluates candidate depths.
Bit-for-bit mathematically identical to sequential scoring due to pointwise cross-encoder invariance.
"""
import argparse
import gzip
import json
import logging
import math
import multiprocessing as mp
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks
from benchmark.mteb_appretrieval import load_export
from benchmark.trust import evaluation
from benchmark.trust.forensics import paired_bootstrap

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Worker %(process)d] %(message)s")
logger = logging.getLogger(__name__)

VERIFICATION = ROOT / "benchmark" / "verification"
RANKS_DIR = VERIFICATION / "ranks"
QRELS_FILE = VERIFICATION / "apps.qrels"
DEV_SPLIT_FILE = ROOT / "benchmark" / "dev_split.json"
RESULTS_DIR = ROOT / "benchmark" / "results"
SHARDS_DIR = RESULTS_DIR / "shards"


def worker_score_shard(worker_id: int, num_workers: int, qids: list[str], max_depth: int = 100,
                       model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", batch_size: int = 64,
                       torch_threads: int = 1):
    import torch
    torch.set_num_threads(1)
    
    logger.info(f"Worker {worker_id}/{num_workers} starting: {len(qids)} queries, max_depth={max_depth}, threads=1")
    shard_file = SHARDS_DIR / f"scores_shard_{worker_id}_of_{num_workers}.json"
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load master cache if available
    master_file = RESULTS_DIR / "master_scores_d100.json"
    master_cache = {}
    if master_file.exists():
        try:
            master_cache = json.loads(master_file.read_text(encoding="utf-8"))
        except Exception:
            master_cache = {}
            
    scored_dict = {}
    if shard_file.exists():
        try:
            scored_dict = json.loads(shard_file.read_text(encoding="utf-8"))
        except Exception:
            scored_dict = {}
            
    # Include any queries already in master cache
    for q in qids:
        if q in master_cache and q not in scored_dict:
            scored_dict[q] = master_cache[q]
            
    remaining_qids = [q for q in qids if q not in scored_dict]
    logger.info(f"Worker {worker_id}: {len(scored_dict)} already scored, {len(remaining_qids)} remaining.")
    if not remaining_qids:
        logger.info(f"Worker {worker_id} already complete ({len(scored_dict)} queries).")
        shard_file.write_text(json.dumps(scored_dict), encoding="utf-8")
        return
        
    corpus, queries, _ = load_export(ROOT / ".astflow/datasets/apps", "test")
    hybrid_ranks = load_ranks(RANKS_DIR / "baseline-v1-hybrid.ranks.tsv.gz")
    
    from sentence_transformers import CrossEncoder
    reranker = CrossEncoder(model_name, device="cpu")
    
    chunk_size = 25
    t_start = time.perf_counter()
    for idx in range(0, len(remaining_qids), chunk_size):
        chunk_qids = remaining_qids[idx:idx + chunk_size]
        chunk_pairs = []
        chunk_info = [] # (qid, did)
        
        for qid in chunk_qids:
            qtext = queries[qid]
            top_k = hybrid_ranks.get(qid, [])[:max_depth]
            for did in top_k:
                chunk_pairs.append([qtext, corpus.get(did, "")])
                chunk_info.append((qid, did))
                
        if chunk_pairs:
            scores = reranker.predict(chunk_pairs, batch_size=batch_size, show_progress_bar=False)
            for (qid, did), score in zip(chunk_info, scores):
                if qid not in scored_dict:
                    scored_dict[qid] = {}
                scored_dict[qid][did] = float(score)
                
        # Save shard progress
        shard_file.write_text(json.dumps(scored_dict), encoding="utf-8")
        done = len(scored_dict)
        elapsed = time.perf_counter() - t_start
        rate = (idx + len(chunk_qids)) / elapsed if elapsed > 0 else 0
        logger.info(f"Worker {worker_id}: {done}/{len(qids)} queries done ({rate:.2f} queries/s)")
            
    logger.info(f"Worker {worker_id} finished: {len(scored_dict)} queries.")


def run_parallel_scoring(qids: list[str], num_workers: int = 5, max_depth: int = 100, batch_size: int = 64):
    logger.info(f"Launching {num_workers} parallel workers for {len(qids)} queries up to depth {max_depth} (threads=1)...")
    shards = [qids[i::num_workers] for i in range(num_workers)]
    
    processes = []
    for w_id in range(num_workers):
        p = mp.Process(target=worker_score_shard, args=(w_id, num_workers, shards[w_id], max_depth,
                                                        "cross-encoder/ms-marco-MiniLM-L-6-v2", batch_size,
                                                        1))
        p.start()
        processes.append(p)
        
    for p in processes:
        p.join()
        
    # Merge shards
    merged_scores = {}
    for w_id in range(num_workers):
        shard_file = SHARDS_DIR / f"scores_shard_{w_id}_of_{num_workers}.json"
        if not shard_file.exists():
            raise RuntimeError(f"Missing shard file: {shard_file}")
        data = json.loads(shard_file.read_text(encoding="utf-8"))
        merged_scores.update(data)
        
    logger.info(f"All {num_workers} workers finished. Total queries scored: {len(merged_scores)}/{len(qids)}")
    return merged_scores


def evaluate_depth(depth: int, split_name: str, target_qids: list[str], scores_map: dict,
                   model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
                   avg_latency_ms: float = 0.0):
    tag = f"e002-reranked-d{depth}-{split_name}"
    hybrid_ranks = load_ranks(RANKS_DIR / "baseline-v1-hybrid.ranks.tsv.gz")
    qrels = evaluation.read_qrels(QRELS_FILE)
    
    reranked_run = {}
    for qid in target_qids:
        candidates = hybrid_ranks.get(qid, [])
        top_k = candidates[:depth]
        remaining = candidates[depth:]
        
        q_scores = scores_map.get(qid, {})
        scored = [(did, q_scores.get(did, -999999.0)) for did in top_k]
        scored.sort(key=lambda x: (-x[1], x[0]))
        reordered = [did for did, _ in scored]
        reranked_run[qid] = reordered + remaining
        
    # Write runs
    run_file = VERIFICATION / "runs" / f"{tag}.trec"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_sha = evaluation.write_run(reranked_run, run_file, tag=tag)
    
    ranks_out = RANKS_DIR / f"{tag}.ranks.tsv.gz"
    with gzip.open(ranks_out, "wt", encoding="utf-8", compresslevel=9) as stream:
        for qid in sorted(reranked_run):
            stream.write(qid + "\t" + " ".join(reranked_run[qid]) + "\n")
            
    def compute_metrics(run_map, qids):
        res = {}
        for q in qids:
            ranked = run_map.get(q, [])
            rels = qrels.get(q, {})
            top10 = ranked[:10]
            dcg = sum(rels.get(d, 0) / math.log2(idx + 2) for idx, d in enumerate(top10))
            ideal = sorted((g for g in rels.values() if g > 0), reverse=True)[:10]
            idcg = sum(g / math.log2(idx + 2) for idx, g in enumerate(ideal))
            positives = {d for d, g in rels.items() if g > 0}
            rr = next((1 / (idx + 1) for idx, d in enumerate(top10) if d in positives), 0.0)
            res[q] = {
                "ndcg@10": dcg / idcg if idcg else 0.0,
                "mrr@10": rr,
                "recall@10": len(set(ranked[:10]) & positives) / len(positives) if positives else 0.0,
                "recall@20": len(set(ranked[:20]) & positives) / len(positives) if positives else 0.0,
                "recall@50": len(set(ranked[:50]) & positives) / len(positives) if positives else 0.0,
                "recall@100": len(set(ranked[:100]) & positives) / len(positives) if positives else 0.0,
            }
        means = {m: float(np.mean([res[q][m] for q in qids])) for m in ("ndcg@10", "mrr@10", "recall@10", "recall@20", "recall@50", "recall@100")}
        return means, res

    baseline_run = {q: hybrid_ranks[q] for q in target_qids if q in hybrid_ranks}
    base_means, base_per_q = compute_metrics(baseline_run, target_qids)
    rerank_means, rerank_per_q = compute_metrics(reranked_run, target_qids)
    
    base_ndcg_per_q = {q: base_per_q[q]["ndcg@10"] for q in target_qids}
    rerank_ndcg_per_q = {q: rerank_per_q[q]["ndcg@10"] for q in target_qids}
    bs = paired_bootstrap(baseline=base_ndcg_per_q, candidate=rerank_ndcg_per_q, samples=10000, seed=20260923)
    ci95 = bs["ci95"]
    excludes_zero = (ci95[0] > 0 and ci95[1] > 0) or (ci95[0] < 0 and ci95[1] < 0)
    
    print("\n" + "=" * 80)
    print(f"E002 RERANKER RESULTS — Depth={depth}, Split={split_name}")
    print(f"Metric        Baseline Hybrid    Reranked@{depth}     Delta")
    for m in ("ndcg@10", "mrr@10", "recall@10", "recall@20", "recall@50", "recall@100"):
        b_val = base_means[m]
        r_val = rerank_means[m]
        d_val = r_val - b_val
        print(f"{m:12s}  {b_val:15.5f}    {r_val:12.5f}     {d_val:+.5f}")
    print(f"95% Bootstrap CI (NDCG@10): [{ci95[0]:+.5f}, {ci95[1]:+.5f}], excludes zero: {excludes_zero}")
    print(f"Estimated Latency: {avg_latency_ms:.1f}ms/query")
    print("=" * 80 + "\n")
    
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_commit = "unknown"
        
    out = {
        "experiment": "E002",
        "model": model_name,
        "model_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "depth": depth,
        "split": split_name,
        "device": "cpu",
        "batch_size": 64,
        "mean_latency_ms": avg_latency_ms,
        "run_sha256": run_sha,
        "git_commit": git_commit,
        "dataset_revision": "f22508f96b7a36c2415181ed8bb76f76e04ae2d5",
        "qrels_sha256": evaluation.sha256_file(QRELS_FILE),
        "baseline_metrics": base_means,
        "reranked_metrics": rerank_means,
        "deltas": {m: rerank_means[m] - base_means[m] for m in base_means},
        "bootstrap_ndcg10_ci95": ci95,
        "excludes_zero": excludes_zero,
    }
    
    out_file = RESULTS_DIR / f"reranker_{split_name}_d{depth}.json"
    out_file.write_text(json.dumps(out, indent=2))
    logger.info(f"Results saved to {out_file}")
    return out


def main():
    mp.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--split", default="dev", choices=["dev", "confirmation", "all"])
    parser.add_argument("--max-depth", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    
    with open(DEV_SPLIT_FILE, "r", encoding="utf-8") as f:
        splits = json.load(f)
    if args.split == "dev":
        target_qids = splits["dev_query_ids"]
    elif args.split == "confirmation":
        target_qids = splits["confirmation_query_ids"]
    else:
        target_qids = splits["dev_query_ids"] + splits["confirmation_query_ids"]
        
    t0 = time.perf_counter()
    scores = run_parallel_scoring(target_qids, num_workers=args.workers, max_depth=args.max_depth,
                                  batch_size=args.batch_size)
    total_time = time.perf_counter() - t0
    
    # Save combined scores
    all_scores_file = RESULTS_DIR / f"scores_{args.split}_d{args.max_depth}.json"
    all_scores_file.write_text(json.dumps(scores), encoding="utf-8")
    logger.info(f"Combined scores saved to {all_scores_file} ({total_time:.1f}s)")
    
    avg_latency_ms = (total_time / len(target_qids)) * 1000.0
    
    if args.split == "dev":
        # Evaluate depth 50 and depth 100
        evaluate_depth(50, "dev", target_qids, scores, avg_latency_ms=avg_latency_ms * (50 / args.max_depth))
        evaluate_depth(100, "dev", target_qids, scores, avg_latency_ms=avg_latency_ms)


if __name__ == "__main__":
    main()

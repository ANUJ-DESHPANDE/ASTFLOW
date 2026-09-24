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
    from benchmark.mteb_appretrieval import load_export
    directory = ROOT / ".astflow/datasets/apps"
    corpus, queries, _ = load_export(directory, split="test")
    return corpus, queries


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
    chunk_size = 50
    for i in range(0, len(target_qids), chunk_size):
        chunk_qids = target_qids[i:i + chunk_size]
        chunk_pairs = []
        chunk_lens = []
        for qid in chunk_qids:
            qtext = query_texts[qid]
            top_k = hybrid_ranks.get(qid, [])[:depth]
            chunk_pairs.extend([[qtext, doc_texts.get(did, "")] for did in top_k])
            chunk_lens.append(len(top_k))
        
        t0 = time.perf_counter()
        if chunk_pairs:
            chunk_scores = reranker.predict(chunk_pairs, batch_size=batch_size, show_progress_bar=False)
        else:
            chunk_scores = []
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        
        offset = 0
        for qid, qlen in zip(chunk_qids, chunk_lens):
            scores = chunk_scores[offset:offset + qlen]
            offset += qlen
            top_k = hybrid_ranks.get(qid, [])[:depth]
            remaining = hybrid_ranks.get(qid, [])[depth:]
            scored = list(zip(top_k, scores))
            scored.sort(key=lambda x: (-x[1], x[0]))
            reordered = [did for did, _ in scored]
            reranked_run[qid] = reordered + remaining
            latencies.append(elapsed_ms / len(chunk_qids))
            
        done = min(i + chunk_size, len(target_qids))
        if done % 200 == 0 or done == len(target_qids) or i == 0:
            logger.info(f"Progress: {done}/{len(target_qids)} queries (avg {elapsed_ms / len(chunk_qids):.1f} ms/query)")
            
    total_time = time.perf_counter() - t_bench_start
    median_latency = float(np.median(latencies))
    mean_latency = float(np.mean(latencies))
    logger.info(f"Reranking finished in {total_time:.1f}s. Median latency: {median_latency:.1f}ms, Mean: {mean_latency:.1f}ms.")
    
    # 6. Evaluate and compare against baseline
    run_file = VERIFICATION / "runs" / f"{tag}.trec"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_sha = evaluation.write_run(reranked_run, run_file, tag=tag)
    
    # Compress rankings to ranks/<tag>.ranks.tsv.gz
    ranks_out = RANKS_DIR / f"{tag}.ranks.tsv.gz"
    ranks_out.parent.mkdir(parents=True, exist_ok=True)
    import gzip
    with gzip.open(ranks_out, "wt", encoding="utf-8", compresslevel=9) as stream:
        for qid in sorted(reranked_run):
            stream.write(qid + "\t" + " ".join(reranked_run[qid]) + "\n")
    logger.info(f"Saved compressed ranks to {ranks_out}")

    # Compute detailed metrics on target_qids
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
    
    delta_ndcg = rerank_means["ndcg@10"] - base_means["ndcg@10"]
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
    print(f"Latency: Median {median_latency:.1f}ms/query, Mean {mean_latency:.1f}ms/query")
    print("=" * 80 + "\n")
    
    # Provenance
    import subprocess
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_commit = "unknown"
        
    return {
        "experiment": "E002",
        "model": model_name,
        "model_revision": getattr(reranker.model.config, "_commit_hash", None) or "default",
        "depth": depth,
        "split": split_name,
        "device": device,
        "batch_size": batch_size,
        "runtime_s": total_time,
        "load_time_s": load_time_s,
        "median_latency_ms": median_latency,
        "mean_latency_ms": mean_latency,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--depth", type=int, default=100, choices=[20, 50, 100])
    parser.add_argument("--split", default="dev", choices=["dev", "confirmation", "all"])
    parser.add_argument("--batch-size", type=int, default=64)
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
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(res, indent=2))
    logger.info(f"Results saved to {out_file}")
    logger.info(f"Results saved to {out_file}")


if __name__ == "__main__":
    main()

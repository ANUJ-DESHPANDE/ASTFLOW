"""Comprehensive controlled RRF fusion sweep over dev queries from frozen baseline-v1 runs."""
import gzip
import json
import math
import sys
import time
from pathlib import Path
from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks
from benchmark.trust.forensics import paired_bootstrap

# Paths
VERIFICATION = ROOT / "benchmark" / "verification"
RANKS_DIR = VERIFICATION / "ranks"
QRELS_FILE = VERIFICATION / "apps.qrels"
DEV_SPLIT_FILE = ROOT / "benchmark" / "dev_split.json"
RESULTS_DIR = ROOT / "benchmark" / "results"

def load_data():
    bm25 = load_ranks(RANKS_DIR / "baseline-v1-bm25.ranks.tsv.gz")
    dense = load_ranks(RANKS_DIR / "baseline-v1-dense.ranks.tsv.gz")
    hybrid = load_ranks(RANKS_DIR / "baseline-v1-hybrid.ranks.tsv.gz")
    
    with open(DEV_SPLIT_FILE, "r", encoding="utf-8") as f:
        split = json.load(f)
    dev_qids = split["dev_query_ids"]
    conf_qids = split["confirmation_query_ids"]
    
    qrels = {}
    with open(QRELS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                qid, _, did, grade = line.split()
                if int(grade) > 0:
                    qrels[qid] = did
                    
    return bm25, dense, hybrid, dev_qids, conf_qids, qrels

def rrf_for_queries(bm25, dense, qids, k=60, w_lex=1.0, w_sem=1.0, depth=1000):
    """Fused ranking for specified queries only, preserving exact tie-breaking."""
    fused = {}
    for qid in qids:
        b_list = bm25.get(qid, [])[:depth]
        d_list = dense.get(qid, [])[:depth]
        
        scores = {}
        if w_lex > 0:
            for rank, did in enumerate(b_list, 1):
                scores[did] = scores.get(did, 0.0) + w_lex / (k + rank)
        if w_sem > 0:
            for rank, did in enumerate(d_list, 1):
                scores[did] = scores.get(did, 0.0) + w_sem / (k + rank)
                
        # Sorted by (-score, doc_id) as in ASTFLOW search.py
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        fused[qid] = [did for did, _ in ranked][:1000]
    return fused

def evaluate_rankings(rankings, qids, qrels):
    n = len(qids)
    ndcg10_sum = 0.0
    mrr10_sum = 0.0
    recalls = {10: 0, 20: 0, 50: 0, 100: 0, 500: 0, 1000: 0}
    per_query_ndcg = {}
    per_query_rank = {}
    
    for qid in qids:
        rel_doc = qrels[qid]
        ranked = rankings.get(qid, [])
        try:
            rank = ranked.index(rel_doc) + 1
        except ValueError:
            rank = None
            
        per_query_rank[qid] = rank
        
        if rank is not None and rank <= 10:
            ndcg = 1.0 / math.log2(rank + 1)
            mrr = 1.0 / rank
        else:
            ndcg = 0.0
            mrr = 0.0
            
        per_query_ndcg[qid] = ndcg
        ndcg10_sum += ndcg
        mrr10_sum += mrr
        
        if rank is not None:
            for cutoff in recalls:
                if rank <= cutoff:
                    recalls[cutoff] += 1
                    
    res = {
        "ndcg@10": ndcg10_sum / n,
        "mrr@10": mrr10_sum / n,
        "per_query_ndcg": per_query_ndcg,
        "per_query_rank": per_query_rank,
    }
    for cutoff in recalls:
        res[f"recall@{cutoff}"] = recalls[cutoff] / n
        res[f"hits@{cutoff}"] = recalls[cutoff]
        
    return res

def analyze_candidates(fused_ranks, bm25, dense, qids, qrels):
    n = len(qids)
    bm25_top100 = {}
    dense_top100 = {}
    fused_top100 = {}
    fused_top10 = {}
    
    for qid in qids:
        rel = qrels[qid]
        b_r100 = bm25.get(qid, [])[:100]
        d_r100 = dense.get(qid, [])[:100]
        f_r = fused_ranks.get(qid, [])
        f_r100 = f_r[:100]
        f_r10 = f_r[:10]
        
        bm25_top100[qid] = rel in b_r100
        dense_top100[qid] = rel in d_r100
        fused_top100[qid] = rel in f_r100
        fused_top10[qid] = rel in f_r10
        
    union_hits = sum(1 for qid in qids if bm25_top100[qid] or dense_top100[qid])
    fused_hits100 = sum(1 for qid in qids if fused_top100[qid])
    fused_hits10 = sum(1 for qid in qids if fused_top10[qid])
    
    bm25_only_qids = [qid for qid in qids if bm25_top100[qid] and not dense_top100[qid]]
    dense_only_qids = [qid for qid in qids if dense_top100[qid] and not bm25_top100[qid]]
    both_qids = [qid for qid in qids if bm25_top100[qid] and dense_top100[qid]]
    
    bm25_only_survived = sum(1 for qid in bm25_only_qids if fused_top100[qid])
    dense_only_survived = sum(1 for qid in dense_only_qids if fused_top100[qid])
    lost_by_fusion = sum(1 for qid in qids if (bm25_top100[qid] or dense_top100[qid]) and not fused_top100[qid])
    
    return {
        "union_hit_rate": union_hits / n,
        "union_hits": union_hits,
        "fused_hits@100": fused_hits100,
        "fused_hit_rate@100": fused_hits100 / n,
        "fused_hits@10": fused_hits10,
        "fused_hit_rate@10": fused_hits10 / n,
        "bm25_only_total": len(bm25_only_qids),
        "bm25_only_survived": bm25_only_survived,
        "dense_only_total": len(dense_only_qids),
        "dense_only_survived": dense_only_survived,
        "both_total": len(both_qids),
        "lost_by_fusion": lost_by_fusion,
    }

def run_experiment():
    bm25, dense, hybrid, dev_qids, conf_qids, qrels = load_data()
    
    # 1. Baseline Evaluation
    dev_baseline = evaluate_rankings(hybrid, dev_qids, qrels)
    dev_baseline_cand = analyze_candidates(hybrid, bm25, dense, dev_qids, qrels)
    
    conf_baseline = evaluate_rankings(hybrid, conf_qids, qrels)
    conf_baseline_cand = analyze_candidates(hybrid, bm25, dense, conf_qids, qrels)
    
    print("=" * 80, flush=True)
    print("BASELINE-V1 ON SPLITS", flush=True)
    print(f"DEV (N={len(dev_qids)}): NDCG@10={dev_baseline['ndcg@10']:.5f}, R@10={dev_baseline['recall@10']:.5f}, R@100={dev_baseline['recall@100']:.5f}, Lost={dev_baseline_cand['lost_by_fusion']}", flush=True)
    print(f"CONF (N={len(conf_qids)}): NDCG@10={conf_baseline['ndcg@10']:.5f}, R@10={conf_baseline['recall@10']:.5f}, R@100={conf_baseline['recall@100']:.5f}, Lost={conf_baseline_cand['lost_by_fusion']}", flush=True)
    print("=" * 80, flush=True)
    
    # 2. Sweep Parameters
    k_values = [10, 20, 30, 60, 100]
    weight_ratios = [
        (1.0, 0.0, "1:0 (BM25 only)"),
        (0.0, 1.0, "0:1 (Dense only)"),
        (1.0, 3.0, "1:3"),
        (1.0, 2.0, "1:2"),
        (1.0, 1.5, "1:1.5"),
        (1.0, 1.0, "1:1 (equal)"),
        (1.5, 1.0, "1.5:1"),
        (2.0, 1.0, "2:1"),
        (3.0, 1.0, "3:1"),
    ]
    depths = [10, 20, 50, 100, 200, 500, 1000]
    
    results_list = []
    
    start_time = time.time()
    count = 0
    total_configs = len(k_values) * len(weight_ratios) * len(depths)
    print(f"Starting sweep of {total_configs} configurations on DEV queries...", flush=True)
    
    for d in depths:
        d_start = time.time()
        for k in k_values:
            for w_b, w_d, label in weight_ratios:
                count += 1
                t0 = time.time()
                fused = rrf_for_queries(bm25, dense, dev_qids, k=k, w_lex=w_b, w_sem=w_d, depth=d)
                eval_res = evaluate_rankings(fused, dev_qids, qrels)
                cand_res = analyze_candidates(fused, bm25, dense, dev_qids, qrels)
                elapsed_ms = (time.time() - t0) * 1000.0
                
                rec = {
                    "k": k,
                    "w_bm25": w_b,
                    "w_dense": w_d,
                    "ratio": label,
                    "depth": d,
                    "ndcg@10": eval_res["ndcg@10"],
                    "mrr@10": eval_res["mrr@10"],
                    "recall@10": eval_res["recall@10"],
                    "recall@20": eval_res["recall@20"],
                    "recall@50": eval_res["recall@50"],
                    "recall@100": eval_res["recall@100"],
                    "recall@500": eval_res["recall@500"],
                    "recall@1000": eval_res["recall@1000"],
                    "hits@10": eval_res["hits@10"],
                    "hits@100": eval_res["hits@100"],
                    "union_hit_rate": cand_res["union_hit_rate"],
                    "union_hits": cand_res["union_hits"],
                    "bm25_only_survived": cand_res["bm25_only_survived"],
                    "bm25_only_total": cand_res["bm25_only_total"],
                    "dense_only_survived": cand_res["dense_only_survived"],
                    "dense_only_total": cand_res["dense_only_total"],
                    "lost_by_fusion": cand_res["lost_by_fusion"],
                    "latency_ms": elapsed_ms,
                    "per_query_ndcg": eval_res["per_query_ndcg"],
                }
                results_list.append(rec)
        print(f"Depth {d} complete ({count}/{total_configs} configs in {time.time() - d_start:.1f}s)", flush=True)
                
    total_time = time.time() - start_time
    print(f"Sweep completed in {total_time:.2f} seconds ({total_time/total_configs*1000:.1f} ms/config).", flush=True)
    
    # Sort by NDCG@10 for Question B
    sorted_by_ndcg = sorted(results_list, key=lambda x: x["ndcg@10"], reverse=True)
    # Sort by Recall@100 for Question A
    sorted_by_recall100 = sorted(results_list, key=lambda x: x["recall@100"], reverse=True)
    
    best_ndcg_config = sorted_by_ndcg[0]
    best_recall_config = sorted_by_recall100[0]
    
    print("\n" + "=" * 80, flush=True)
    print("QUESTION B: BEST DEV NDCG@10 CONFIGURATION (Primary Winner)", flush=True)
    print(f"k={best_ndcg_config['k']}, ratio={best_ndcg_config['ratio']}, depth={best_ndcg_config['depth']}", flush=True)
    print(f"DEV NDCG@10: {best_ndcg_config['ndcg@10']:.5f} (Baseline: {dev_baseline['ndcg@10']:.5f}, Delta: {best_ndcg_config['ndcg@10'] - dev_baseline['ndcg@10']:+.5f})", flush=True)
    print(f"DEV Recall@10: {best_ndcg_config['recall@10']:.5f} ({best_ndcg_config['hits@10']}/{len(dev_qids)})", flush=True)
    print(f"DEV Recall@100: {best_ndcg_config['recall@100']:.5f} ({best_ndcg_config['hits@100']}/{len(dev_qids)})", flush=True)
    print(f"DEV Lost by fusion: {best_ndcg_config['lost_by_fusion']} (Baseline lost: {dev_baseline_cand['lost_by_fusion']})", flush=True)
    
    print("\n" + "=" * 80, flush=True)
    print("QUESTION A: BEST DEV TOP-100 CANDIDATE RECALL CONFIGURATION", flush=True)
    print(f"k={best_recall_config['k']}, ratio={best_recall_config['ratio']}, depth={best_recall_config['depth']}", flush=True)
    print(f"DEV Recall@100: {best_recall_config['recall@100']:.5f} ({best_recall_config['hits@100']}/{len(dev_qids)}) (Baseline: {dev_baseline['recall@100']:.5f})", flush=True)
    print(f"DEV NDCG@10: {best_recall_config['ndcg@10']:.5f} (Baseline: {dev_baseline['ndcg@10']:.5f})", flush=True)
    print(f"DEV Lost by fusion: {best_recall_config['lost_by_fusion']} (Baseline lost: {dev_baseline_cand['lost_by_fusion']})", flush=True)
    
    # 3. Confirmation Evaluation of the Primary Winner (best_ndcg_config)
    print("\n" + "=" * 80, flush=True)
    print("EVALUATING DEV WINNER ON CONFIRMATION SET (N=1906)...", flush=True)
    winner_k = best_ndcg_config["k"]
    winner_wb = best_ndcg_config["w_bm25"]
    winner_wd = best_ndcg_config["w_dense"]
    winner_depth = best_ndcg_config["depth"]
    
    conf_winner_fused = rrf_for_queries(bm25, dense, conf_qids, k=winner_k, w_lex=winner_wb, w_sem=winner_wd, depth=winner_depth)
    conf_winner_eval = evaluate_rankings(conf_winner_fused, conf_qids, qrels)
    conf_winner_cand = analyze_candidates(conf_winner_fused, bm25, dense, conf_qids, qrels)
    
    conf_baseline_ndcg = conf_baseline["ndcg@10"]
    conf_winner_ndcg = conf_winner_eval["ndcg@10"]
    conf_delta = conf_winner_ndcg - conf_baseline_ndcg
    dev_delta = best_ndcg_config["ndcg@10"] - dev_baseline["ndcg@10"]
    
    # Paired Bootstrap intervals (samples=10000, seed=20260923)
    dev_bs = paired_bootstrap(baseline=dev_baseline["per_query_ndcg"], candidate=best_ndcg_config["per_query_ndcg"], samples=10000, seed=20260923)
    conf_bs = paired_bootstrap(baseline=conf_baseline["per_query_ndcg"], candidate=conf_winner_eval["per_query_ndcg"], samples=10000, seed=20260923)
    
    dev_ci = dev_bs["ci95"]
    conf_ci = conf_bs["ci95"]
    dev_excludes_zero = (dev_ci[0] > 0 and dev_ci[1] > 0) or (dev_ci[0] < 0 and dev_ci[1] < 0)
    conf_excludes_zero = (conf_ci[0] > 0 and conf_ci[1] > 0) or (conf_ci[0] < 0 and conf_ci[1] < 0)
    
    print(f"CONF Baseline NDCG@10: {conf_baseline_ndcg:.5f}", flush=True)
    print(f"CONF Winner NDCG@10:   {conf_winner_ndcg:.5f}", flush=True)
    print(f"CONF Delta:            {conf_delta:+.5f}", flush=True)
    print(f"DEV 95% Bootstrap CI:  [{dev_ci[0]:+.5f}, {dev_ci[1]:+.5f}], excludes zero: {dev_excludes_zero}", flush=True)
    print(f"CONF 95% Bootstrap CI: [{conf_ci[0]:+.5f}, {conf_ci[1]:+.5f}], excludes zero: {conf_excludes_zero}", flush=True)
    
    # Full test evaluation for completeness
    all_qids = dev_qids + conf_qids
    all_winner_fused = rrf_for_queries(bm25, dense, all_qids, k=winner_k, w_lex=winner_wb, w_sem=winner_wd, depth=winner_depth)
    all_winner_eval = evaluate_rankings(all_winner_fused, all_qids, qrels)
    all_winner_cand = analyze_candidates(all_winner_fused, bm25, dense, all_qids, qrels)
    all_baseline = evaluate_rankings(hybrid, all_qids, qrels)
    all_baseline_cand = analyze_candidates(hybrid, bm25, dense, all_qids, qrels)
    
    keep = dev_excludes_zero and conf_excludes_zero and dev_delta > 0 and conf_delta > 0
    decision = "KEEP" if keep else "REJECT"
    print(f"\nDECISION: {decision}", flush=True)
    
    clean_results = []
    for r in results_list:
        clean_r = {k: v for k, v in r.items() if k != "per_query_ndcg"}
        clean_results.append(clean_r)
        
    out_data = {
        "experiment_id": "E001-fusion",
        "description": "Controlled RRF fusion sweep over dev queries",
        "total_configs": total_configs,
        "decision": decision,
        "dev_winner": {
            "k": winner_k,
            "w_bm25": winner_wb,
            "w_dense": winner_wd,
            "ratio": best_ndcg_config["ratio"],
            "depth": winner_depth,
            "dev_baseline_ndcg10": dev_baseline["ndcg@10"],
            "dev_winner_ndcg10": best_ndcg_config["ndcg@10"],
            "dev_delta": dev_delta,
            "dev_bootstrap_95ci": dev_ci,
            "dev_ci_excludes_zero": dev_excludes_zero,
            "conf_baseline_ndcg10": conf_baseline_ndcg,
            "conf_winner_ndcg10": conf_winner_ndcg,
            "conf_delta": conf_delta,
            "conf_bootstrap_95ci": conf_ci,
            "conf_ci_excludes_zero": conf_excludes_zero,
            "all_baseline_ndcg10": all_baseline["ndcg@10"],
            "all_winner_ndcg10": all_winner_eval["ndcg@10"],
            "all_delta": all_winner_eval["ndcg@10"] - all_baseline["ndcg@10"],
            "all_baseline_recall100": all_baseline["recall@100"],
            "all_winner_recall100": all_winner_eval["recall@100"],
            "all_baseline_lost": all_baseline_cand["lost_by_fusion"],
            "all_winner_lost": all_winner_cand["lost_by_fusion"],
            "dev_metrics": {
                "ndcg@10": best_ndcg_config["ndcg@10"],
                "mrr@10": best_ndcg_config["mrr@10"],
                "recall@10": best_ndcg_config["recall@10"],
                "recall@20": best_ndcg_config["recall@20"],
                "recall@50": best_ndcg_config["recall@50"],
                "recall@100": best_ndcg_config["recall@100"],
                "recall@500": best_ndcg_config["recall@500"],
                "recall@1000": best_ndcg_config["recall@1000"],
            },
            "conf_metrics": {
                "ndcg@10": conf_winner_eval["ndcg@10"],
                "mrr@10": conf_winner_eval["mrr@10"],
                "recall@10": conf_winner_eval["recall@10"],
                "recall@20": conf_winner_eval["recall@20"],
                "recall@50": conf_winner_eval["recall@50"],
                "recall@100": conf_winner_eval["recall@100"],
                "recall@500": conf_winner_eval["recall@500"],
                "recall@1000": conf_winner_eval["recall@1000"],
            },
            "dev_candidates": {
                "hits@10": best_ndcg_config["hits@10"],
                "hits@100": best_ndcg_config["hits@100"],
                "bm25_only_survived": best_ndcg_config["bm25_only_survived"],
                "bm25_only_total": best_ndcg_config["bm25_only_total"],
                "dense_only_survived": best_ndcg_config["dense_only_survived"],
                "dense_only_total": best_ndcg_config["dense_only_total"],
                "lost_by_fusion": best_ndcg_config["lost_by_fusion"],
            },
            "conf_candidates": {
                "hits@10": conf_winner_cand["fused_hits@10"],
                "hits@100": conf_winner_cand["fused_hits@100"],
                "bm25_only_survived": conf_winner_cand["bm25_only_survived"],
                "bm25_only_total": conf_winner_cand["bm25_only_total"],
                "dense_only_survived": conf_winner_cand["dense_only_survived"],
                "dense_only_total": conf_winner_cand["dense_only_total"],
                "lost_by_fusion": conf_winner_cand["lost_by_fusion"],
            }
        },
        "best_top100_recall_config": {
            "k": best_recall_config["k"],
            "ratio": best_recall_config["ratio"],
            "depth": best_recall_config["depth"],
            "dev_recall100": best_recall_config["recall@100"],
            "dev_ndcg10": best_recall_config["ndcg@10"],
            "dev_lost": best_recall_config["lost_by_fusion"],
        },
        "configs": clean_results,
    }
    
    (RESULTS_DIR / "fusion_sweep_e001.json").write_text(json.dumps(out_data, indent=2))
    print(f"Results saved to {RESULTS_DIR / 'fusion_sweep_e001.json'}", flush=True)

if __name__ == "__main__":
    run_experiment()

import json
from benchmark.run_fusion_sweep import load_data, rrf_for_queries, evaluate_rankings, analyze_candidates

bm25, dense, hybrid, dev_qids, conf_qids, qrels = load_data()
all_qids = dev_qids + conf_qids

# Baseline (k=60, 1:1, 1000)
b_eval = evaluate_rankings(hybrid, all_qids, qrels)
b_cand = analyze_candidates(hybrid, bm25, dense, all_qids, qrels)

# Winner (k=30, 1:1, 1000)
w_fused = rrf_for_queries(bm25, dense, all_qids, k=30, w_lex=1.0, w_sem=1.0, depth=1000)
w_eval = evaluate_rankings(w_fused, all_qids, qrels)
w_cand = analyze_candidates(w_fused, bm25, dense, all_qids, qrels)

# Best Recall (k=100, 1:1, 500)
r_fused = rrf_for_queries(bm25, dense, all_qids, k=100, w_lex=1.0, w_sem=1.0, depth=500)
r_eval = evaluate_rankings(r_fused, all_qids, qrels)
r_cand = analyze_candidates(r_fused, bm25, dense, all_qids, qrels)

print("=== ALL 3765 QUERIES COMPARISON ===")
for name, ev, cd in [("Baseline (k=60, 1:1, d=1000)", b_eval, b_cand),
                     ("Winner NDCG (k=30, 1:1, d=1000)", w_eval, w_cand),
                     ("Best Recall@100 (k=100, 1:1, d=500)", r_eval, r_cand)]:
    print(f"-- {name} --")
    print(f"  NDCG@10: {ev['ndcg@10']:.5f}")
    print(f"  MRR@10:  {ev['mrr@10']:.5f}")
    print(f"  R@10:    {ev['recall@10']:.5f} ({ev['hits@10']}/3765)")
    print(f"  R@20:    {ev['recall@20']:.5f} ({ev['hits@20']}/3765)")
    print(f"  R@50:    {ev['recall@50']:.5f} ({ev['hits@50']}/3765)")
    print(f"  R@100:   {ev['recall@100']:.5f} ({ev['hits@100']}/3765)")
    print(f"  R@500:   {ev['recall@500']:.5f} ({ev['hits@500']}/3765)")
    print(f"  R@1000:  {ev['recall@1000']:.5f} ({ev['hits@1000']}/3765)")
    print(f"  Candidate Union top 100: {cd['union_hits']}/3765 ({cd['union_hit_rate']*100:.2f}%)")
    print(f"  Surviving in top 100:   {cd['fused_hits@100']}/3765 ({cd['fused_hit_rate@100']*100:.2f}%)")
    print(f"  BM25-only survived:     {cd['bm25_only_survived']}/{cd['bm25_only_total']}")
    print(f"  Dense-only survived:    {cd['dense_only_survived']}/{cd['dense_only_total']}")
    print(f"  Lost by fusion:         {cd['lost_by_fusion']}/3765")

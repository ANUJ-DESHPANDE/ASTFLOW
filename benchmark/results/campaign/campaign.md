# Retrieval campaign — diagnostics, E004, E009 (train dev / confirmation; GTE vectors from the frozen run)

Baseline reproduction on TEST (GTE dense, 3,765 q): NDCG@10 0.5511, MRR@10 0.5053, R@100 0.8943 (official MTEB: 0.5511 / 0.5053 / 0.8943)

pytrec_eval check (dev, dense): {"ours_ndcg@10": 0.6977336494947775, "pytrec_ndcg@10": 0.6977336494947775, "ours_mrr_top1000": 0.6688833859330588, "pytrec_recip_rank": 0.6688833859330588, "queries_found": 297}

## dev (n=300; 5.3 s)

| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | R@200 | R@500 | R@1000 | ΔNDCG vs dense [95% CI] | W/L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.6977 | 0.6633 | 0.8067 | 0.9133 | 0.9333 | 0.9567 | 0.9767 | 0.9900 | +0.0000 [+0.0000, +0.0000] | 0/0 |
| bm25_code | 0.3789 | 0.3543 | 0.4567 | 0.5900 | 0.6300 | 0.7033 | 0.7667 | 0.8400 | -0.3188 [-0.3674, -0.2695] | 17/149 |
| bm25_generic | 0.1785 | 0.1615 | 0.2333 | 0.3300 | 0.4067 | 0.4900 | 0.6000 | 0.6867 | -0.5193 [-0.5688, -0.4696] | 5/201 |
| hybrid_rrf_equal_k60 | 0.6130 | 0.5667 | 0.7633 | 0.8867 | 0.9333 | 0.9567 | 0.9833 | 0.9833 | -0.0848 [-0.1176, -0.0526] | 33/83 |
| e004_lin_generic_l0.05 | 0.7146 | 0.6844 | 0.8100 | 0.9200 | 0.9367 | 0.9567 | 0.9767 | 0.9900 | +0.0169 [+0.0045, +0.0302] | 27/15 |

Best E00x on dev: `e004_lin_generic_l0.05`
Overlap dense vs BM25(code): {"top10": {"both": 133, "dense_only": 109, "bm25_only": 4, "neither": 54}, "top100": {"both": 185, "dense_only": 95, "bm25_only": 4, "neither": 16}, "top1000": {"both": 252, "dense_only": 45, "bm25_only": 0, "neither": 3}}
Oracle (dense candidates, perfect rerank): {"oracle_ndcg@10_depth20": 0.8533333333333334, "oracle_ndcg@10_depth50": 0.9133333333333333, "oracle_ndcg@10_depth100": 0.9333333333333333, "oracle_ndcg@10_depth200": 0.9566666666666667}

## confirmation (n=300; 2.3 s)

| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | R@200 | R@500 | R@1000 | ΔNDCG vs dense [95% CI] | W/L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.7080 | 0.6710 | 0.8233 | 0.8967 | 0.9133 | 0.9467 | 0.9667 | 0.9800 | +0.0000 [+0.0000, +0.0000] | 0/0 |
| bm25_code | 0.4183 | 0.3919 | 0.5000 | 0.6067 | 0.6300 | 0.6767 | 0.7733 | 0.8367 | -0.2896 [-0.3383, -0.2448] | 15/141 |
| bm25_generic | 0.1621 | 0.1486 | 0.2067 | 0.3000 | 0.4067 | 0.5033 | 0.6133 | 0.6967 | -0.5459 [-0.5940, -0.4953] | 6/206 |
| hybrid_rrf_equal_k60 | 0.6284 | 0.5831 | 0.7767 | 0.8767 | 0.9067 | 0.9233 | 0.9667 | 0.9833 | -0.0795 [-0.1148, -0.0463] | 34/83 |
| e009_lin_l0.05 | 0.7350 | 0.7047 | 0.8300 | 0.8933 | 0.9133 | 0.9500 | 0.9667 | 0.9867 | +0.0271 [+0.0134, +0.0417] | 30/15 |

Best E00x on confirmation: `e009_lin_l0.05`
Overlap dense vs BM25(code): {"top10": {"both": 146, "dense_only": 101, "bm25_only": 4, "neither": 49}, "top100": {"both": 186, "dense_only": 88, "bm25_only": 3, "neither": 23}, "top1000": {"both": 246, "dense_only": 48, "bm25_only": 5, "neither": 1}}
Oracle (dense candidates, perfect rerank): {"oracle_ndcg@10_depth20": 0.8533333333333334, "oracle_ndcg@10_depth50": 0.8966666666666666, "oracle_ndcg@10_depth100": 0.9133333333333333, "oracle_ndcg@10_depth200": 0.9466666666666667}


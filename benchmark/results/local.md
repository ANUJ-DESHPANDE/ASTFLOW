# ASTFLOW local benchmark

Small handcrafted fixture; not a held-out or official MTEB/CoIR result. MRR is over at most 50 candidates.

16 queries · 24 source chunks · model: sentence-transformers/all-MiniLM-L6-v2

| System | NDCG@10 | MRR | Recall@10 | Median ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 only | 0.8546 | 0.9688 | 0.8646 | 0.60 | 5.01 |
| Dense only | 0.9204 | 0.9271 | 1.0000 | 13.53 | 17.02 |
| Hybrid | 0.9124 | 0.9688 | 1.0000 | 13.10 | 14.41 |
| Hybrid + structure | 0.9002 | 0.9062 | 1.0000 | 13.29 | 14.59 |
| ASTFLOW full | 0.9220 | 0.9688 | 1.0000 | 15.33 | 31.68 |

Generated from an executed evaluation. Full per-query rankings are in `local.json`.

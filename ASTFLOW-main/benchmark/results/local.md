# ASTFLOW local benchmark

Small handcrafted fixture; not a held-out or official MTEB/CoIR result. MRR is over at most 50 candidates.

16 queries · 21 source chunks · model: unavailable

| System | NDCG@10 | MRR | Recall@10 | Median ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 only | 0.8205 | 0.8802 | 0.8646 | 1.04 | 5.97 |
| Dense only | unavailable | — | — | — | — |
| Hybrid | 0.8205 | 0.8802 | 0.8646 | 0.94 | 1.49 |
| Hybrid + structure | 0.8695 | 0.9115 | 0.9792 | 1.25 | 2.16 |
| ASTFLOW full | 0.8516 | 0.9115 | 0.9792 | 1.45 | 3.00 |

Generated from an executed evaluation. Full per-query rankings are in `local.json`.

Semantic model unavailable: hybrid/full rows used lexical fallback, not dense retrieval.

Category metrics are included in each baseline's `categories` object in `local.json`.

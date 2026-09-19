# CoIR AppsRetrieval adapter run

32 queries / 8765 documents · query subset against full corpus

No JavaScript structural evidence; standalone Python documents. MRR uses at most 50 candidates. This direct adapter is not the official MTEB harness.

| Baseline | NDCG@10 | MRR (top 50) | Recall@10 | Median ms |
| --- | ---: | ---: | ---: | ---: |
| bm25 | 0.0904 | 0.0781 | 0.1250 | 454.22 |
| dense | 0.0625 | 0.0707 | 0.0625 | 562.07 |
| hybrid | 0.0916 | 0.0825 | 0.1250 | 495.23 |

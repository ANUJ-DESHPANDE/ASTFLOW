> **Historical document. Do not use for current retrieval status. See [/RETRIEVAL-PROGRESS.md](../../RETRIEVAL-PROGRESS.md).** This file claims 3,765 queries, but its companion `apps.json` holds a different 32-query run; there is no machine-readable record of the numbers below. Dense/Hybrid below were produced with the document/vector alignment bug; "reranked" is Hybrid.

# CoIR AppsRetrieval adapter run

3765 queries / 8765 documents · all split queries against full corpus

No JavaScript structural evidence; standalone Python documents. MRR uses at most 50 candidates. This direct adapter is not the official MTEB harness.

| Baseline | NDCG@10 | MRR (top 50) | Recall@10 | Median ms |
| --- | ---: | ---: | ---: | ---: |
| bm25 | 0.0631 | 0.0593 | 0.0922 | 181.81 |
| dense | 0.0010 | 0.0011 | 0.0021 | 539.18 |
| hybrid | 0.0322 | 0.0251 | 0.0696 | 399.25 |
| reranked | 0.0322 | 0.0251 | 0.0696 | 427.59 |

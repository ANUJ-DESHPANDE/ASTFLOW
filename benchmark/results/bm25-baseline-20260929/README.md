# BM25 baseline on the full TEST split (2026-09-29)

ASTFLOW's own BM25 ranking scores **NDCG@10 0.0631** on CoIR AppsRetrieval TEST (3,765 queries × 8,765 documents).
The frozen GTE dense system scores 0.5509 on the same run protocol. The run used the official runner on `main` at
`fec272f` with a clean tree, and reproduces the Sep 25 audit artifact (`../mteb-current-bm25/`) exactly.

| Metric | BM25 (this run) | GTE dense, frozen system ([final validation](../final-validation-20260928/)) |
|---|---:|---:|
| NDCG@10 | **0.0631** | 0.5509 |
| MRR@10 | **0.0542** | 0.5050 |
| R@10 | **0.0922** | 0.6964 |
| R@50 | **0.1687** | 0.8489 |
| R@100 | **0.2260** | 0.8946 |
| R@500 | **0.4552** | 0.9615 |
| R@1000 | **0.5995** | 0.9782 |

BM25 configuration (`backend/app/retrieval/search.py`, unchanged):
- **Model:** `rank_bm25` BM25Okapi with k1 1.6, b 0.75, and positive IDF, log(1 + (N − df + 0.5) / (df + 0.5)).
- **Tokenisation:** camelCase and snake_case splitting, with English and code stopwords.
- **Title field:** weighted 2.0, but titles are empty on this corpus.
- **Model use:** no embedding model is loaded.

Checks (`validation.json`) all pass:
- 3,765 / 3,765 queries predicted, with no missing, duplicate or TRAIN queries.
- 1,000 distinct valid documents per query; scores finite and strictly decreasing; split `test` at revision `f22508f9`.
- MTEB, pytrec_eval and the repo's metric code agree.

The relevant document is ranked first for 152 queries and appears in the top 1,000 for 2,257.

Runtime (i7-14650HX, CPU): the index builds in 9.8 s, the whole benchmark takes 191 s, and query latency is
P50 36 ms / P95 49 ms. Predictions are gzipped: SHA-256 gz `fc3e773e…34ddbd`, uncompressed `fad6cbf0…bffa5b`.

The campaign's "BM25 alone" diagnostic (NDCG@10 0.379) was measured on 300 DEV queries drawn from the TRAIN split,
not on TEST, so it is not comparable with this number.

Reproduce:

```bash
python -m benchmark.run_mteb --mode bm25 --diagnostics --output benchmark/results/bm25-baseline-20260929/mteb
```

```bash
python benchmark/results/bm25-baseline-20260929/validate_run.py
```

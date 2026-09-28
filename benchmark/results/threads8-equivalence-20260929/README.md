# Equivalence check: embedding model on 8 CPU threads instead of 4 (2026-09-29)

Commit `1325390` raises the embedding model's CPU thread cap from 4 to 8, never more than the physical core count
and overridable with `ASTFLOW_THREADS`. It is meant to change speed only. To check that, the official runner was
run again on the full AppsRetrieval TEST split with that commit (`git_dirty_files: []`). Every document and query
was re-encoded; the 4-thread corpus vector cache was moved aside so it could not be reused. The result was compared
with the committed 4-thread run in `../final-validation-20260928/`. Nothing was selected or tuned on this output.

## Accuracy: unchanged

| | 4 threads (committed) | 8 threads |
|---|---:|---:|
| NDCG@10 | 0.5509 | 0.5509 |
| MRR@10 | 0.5050 | 0.5050 |
| R@10 / R@50 / R@100 | 0.6964 / 0.8489 / 0.8946 | 0.6964 / 0.8489 / 0.8946 |
| R@500 / R@1000 | 0.9615 / 0.9782 | 0.9615 / 0.9782 |

- The top 10 is identical for 3,765 / 3,765 queries, and the top 100 for 3,715.
- The relevant document's rank changed for 1 query (`q6096`: 569 → 568, outside every cutoff).
- The largest metric difference is 8e-10 (full-depth MRR).
- Corpus vectors differ by at most 2.0e-6 (min cosine 0.9999996), which is float32 summation-order noise.

## Speed

| | 4 threads | 8 threads |
|---|---:|---:|
| Corpus indexing, 8,765 docs (full runs) | 6,474 s (1 h 48 min) | **3,968 s (1 h 06 min)** |
| Whole benchmark (full runs) | 10,146 s | **8,049 s** |
| Single-query encoding, controlled A/B (150 queries, same process, alternating) | p50 343 ms | **p50 230 ms** (faster on 149 / 150) |

The two full runs were hours apart under different machine conditions. Their per-query latency distributions
disagree: median 480 → 1,167 ms, but P95 3,045 → 2,095 ms. For that reason, query speed is judged by the controlled
A/B in `latency_ab.py` / `latency_ab.json`, which encodes each query under both settings back to back.

Hardware: Intel i7-14650HX (8 performance + 8 efficiency cores), 15.7 GB RAM, Windows 11, CPU only, float32.

## Files

| File | Content |
|---|---|
| `mteb/appsretrieval_results.json`, `mteb/run_metadata.json` | MTEB scores and runner provenance of the 8-thread run |
| `mteb/predictions/AppsRetrieval_predictions.json.gz` | raw rankings (SHA-256 gz `99f11d5a…ff220`, uncompressed `7261f2e4…87340`) |
| `compare.py` → `equivalence.json` | per-query and metric comparison against the 4-thread run |
| `latency_ab.py` → `latency_ab.json` | controlled single-query latency A/B |
| `run.log`, `start_time_utc.txt`, `end_time_utc.txt` | runner log and wall-clock bounds (18:29:11Z → 20:43:58Z) |

Reproduce: `python -m benchmark.run_mteb --mode dense --model Alibaba-NLP/gte-modernbert-base --diagnostics --output benchmark/results/threads8-equivalence-20260929/mteb`,
then `compare.py` and `latency_ab.py`.

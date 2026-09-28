# Final TEST validation run (2026-09-28)

A clean re-measurement of the **frozen** ASTFLOW retrieval system on the full CoIR AppsRetrieval TEST split
(3,765 queries × 8,765 documents). Nothing was tuned, and no retrieval or evaluation code was changed. Every
document and query was re-encoded from scratch; no cached or precomputed vectors were used.

## System measured

| Setting | Value |
|---|---|
| Embedding model | `Alibaba-NLP/gte-modernbert-base` (HF rev `e7f32e3c`, safetensors SHA-256 `3e85899d…a724ba`) |
| Similarity | cosine (dot product of L2-normalised vectors), exact over the full corpus |
| Candidate / ranking depth | all 8,765 documents scored; top 1,000 returned |
| BM25 | DISABLED |
| MMR | DISABLED |
| Reranker | DISABLED |
| Max sequence length | 512 tokens (queries and documents) |
| Precision / device | float32 on CPU (4 torch threads) |

## Results

| Metric | Historical baseline (official run) | This run | Δ |
|---|---:|---:|---:|
| NDCG@10 | 0.5511 | **0.5509** | −0.0002 |
| MRR@10 | 0.5053 | **0.5050** | −0.0003 |
| R@10 | 0.6967 | **0.6964** | −0.0003 (1 query) |
| R@50 | 0.8483 | **0.8489** | +0.0005 (2 queries) |
| R@100 | 0.8943 | **0.8946** | +0.0003 (1 query) |
| R@500 | 0.9612 | **0.9615** | +0.0003 (1 query) |
| R@1000 | 0.9782 | 0.9782 | 0 |

MTEB 2.21.0, pytrec_eval and the repo's own metric code (`benchmark.campaign.metrics`) agree to the reported
precision (`metrics.json`). R@50 and R@500 are not reported by MTEB. They are computed from the exact rankings MTEB
scored, using the repo's definition (one relevant document per query, so Recall@k = Hit@k).

**Why the numbers differ slightly from 0.5511.** The official run (commit `036060e`) encoded with the checkpoint's
native float16. Since `db57806`, the product casts the model to float32 on CPU. That cast is the only change in the
retrieval path; `search.py` and `run_mteb.py` are byte-identical. The repo measured float16 vs float32 vectors at
cosine ≥ 0.9995. That is enough to swap a few near-tied ranks, and it shows here as ±1–2 queries per recall cut-off.
The historical per-query GTE run is not in the repository, so a paired per-query comparison is not possible. The
differences are at the single-query level and far inside the campaign's bootstrap CI widths (about ±0.003 NDCG@10
on TEST).

## Integrity checks (`validation.json`)

3,765 / 3,765 TEST queries predicted; none missing, duplicated or unexpected; 0 TRAIN queries in the run; every
ranking has exactly 1,000 distinct valid document IDs; all scores finite and strictly decreasing; split scored
= `test`; MTEB loaded dataset revision `f22508f9…`; the runner reports the model `loaded on CPU (float32)`,
`max_seq` 512, dense mode, no precomputed vectors. There are no TEST/TRAIN overlaps (`data_check.json`), all
corpus titles are empty, and no query text contains its relevant document ID.

## Reproduce

```bash
python -m venv .eval-venv && .eval-venv/Scripts/python -m pip install -e . -r benchmark/requirements-mteb.txt
.eval-venv/Scripts/python benchmark/results/final-validation-20260928/check_data.py
.eval-venv/Scripts/python -m benchmark.run_mteb --mode dense --model Alibaba-NLP/gte-modernbert-base --download-model --diagnostics --output benchmark/results/final-validation-20260928/mteb
.eval-venv/Scripts/python benchmark/results/final-validation-20260928/validate_run.py
```

Runtime on an i7-14650HX laptop: 2 h 52 min in total (corpus encoding 1 h 48 min, query encoding plus retrieval
1 h 01 min, scoring 3 s). Query latency P50 480 ms / P95 3,045 ms. Full provenance is in `provenance.json`.

## Files

| File | Content |
|---|---|
| `mteb/appsretrieval_results.json` | MTEB's official TEST scores (the evaluation artifact) |
| `mteb/predictions/AppsRetrieval_predictions.json.gz` | raw rankings, top 1,000 per query (gzip of MTEB's file; both SHA-256s in `provenance.json`) |
| `mteb/run_metadata.json` | runner provenance and per-query latencies |
| `metrics.json`, `validation.json` | final metrics and integrity checks |
| `data_check.json` | pre-run dataset verification |
| `provenance.json` | environment, configuration, command, timing and hashes |
| `run.log`, `start_time_utc.txt`, `end_time_utc.txt` | runner log and wall-clock bounds |

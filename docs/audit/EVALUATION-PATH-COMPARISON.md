> **Historical document. Do not use for current retrieval status. See [/RETRIEVAL-PROGRESS.md](../../RETRIEVAL-PROGRESS.md).**

# Direct adapter vs. official MTEB harness

Companion to `DENSE-REGRESSION-INVESTIGATION.md`. These are two genuinely different
evaluation paths that must not be compared as if interchangeable.

| Property | Direct adapter (`benchmark/mteb_appretrieval.py`) | Official MTEB harness (`benchmark/run_mteb.py`) |
|---|---|---|
| Dataset | `CoIR-Retrieval/apps` (local JSONL export via `download_export`) | `CoIR-Retrieval/apps` via `mteb.get_task('AppsRetrieval')` |
| Revision | Recorded per-export in `metadata.json` at download time; not pinned in code | Pinned and asserted in code: `f22508f96b7a36c2415181ed8bb76f76e04ae2d5` (`run_mteb.py` `DATASET_REVISION`) |
| Queries | Configurable (`--max-queries`, default 32; 0 = all 3,765) | All split queries, driven by `mteb.evaluate` |
| Documents | 8,765 | 8,765 |
| Qrels | Loaded manually from `qrels/test.tsv` | Loaded by the `mteb` library itself |
| Query preprocessing | None beyond raw `row["text"]` | Prepends `row["instruction"]` when present, else raw text |
| Corpus preprocessing | `title + "\n" + text`, stripped | `title + "\n" + text` via `"\n".join([title, text]).strip()` — equivalent |
| Chunk id order | `sorted(corpus.items())` (lexicographic by id) | `chunks.sort(key=lambda c: c.chunk_id)` — **also lexicographic**; the two adapters' own internal ordering is actually consistent with each other, the bug was Path B's *cross-script* cache, not a Path A/B mismatch |
| Candidate depth | `Settings.candidates` = 500 (shared default) | Same `Settings.candidates` = 500 |
| MRR cutoff | Capped at top 50 (`benchmark/metrics.py`) | Whatever `mteb`'s own MRR implementation uses (not capped the same way — see below) |
| Dense representation | **Windowed** (256/64, max-pool) when `apps_fixed.npy` present; otherwise plain single-vector MiniLM encode (no `use_windows=True` in the inline fallback branch either) | **Always plain single-vector MiniLM encode** — `ASTFLOWSearch.index()` never passes `use_windows=True` |
| Fusion | `Retriever.rank(mode=...)`, RRF k=60, same `search.py` | Identical `Retriever.rank`, same `search.py` — both paths share the exact same retrieval engine |
| Reranker | `"reranked"` mode literally calls `mode="hybrid"` (no distinct path) | Not exposed as a mode at all (`--mode` choices are `bm25/dense/hybrid` only) |
| Evaluator | `benchmark/metrics.py::metrics()` — custom, direct implementation | `mteb.evaluate(...)` — the library's own official scorer, serialized via `TaskResult.to_disk` |
| NDCG implementation | Custom (`benchmark/metrics.py`) | `mteb`'s own (via `pytrec_eval`) |

## Why the two paths' numbers are not comparable even when both are "healthy"

1. **Different NDCG/MRR implementations.** The direct adapter's `metrics.py` is a from-scratch implementation with an explicit top-50 MRR cap documented in its own output ("MRR uses at most 50 candidates"); MTEB's scorer uses `pytrec_eval`, the standard TREC evaluation tool. Small numeric differences between the two on the *same* ranking are expected and not a bug in either.
2. **Different dense representations by construction, not by accident.** Path A (official) never requests windowing; Path B (direct adapter) only gets windowing when someone has separately run `precompute_embeddings.py` and left `apps_fixed.npy` in place. A "Path A BM25/Hybrid vs. Path B BM25/Hybrid" comparison is really a "non-windowed vs. windowed dense, evaluated by two different scorers" comparison unless both explicitly hold the dense representation constant.
3. **The direct adapter is explicitly documented as not being the official harness** — its own generated report says so verbatim ("This direct adapter is not the official MTEB harness"), which the task's own §0 quotes.

## Historical numbers, and which path they belong to

- `Historical BM25 NDCG@10 = 0.061040` / `Tuned BM25 = 0.06312` / `Historical Hybrid = 0.088150` / `Tuned Hybrid = 0.08900` (`RETRIEVAL-EXPERIMENTS.md`, EXP-6/EXP-7) were all produced on **Path A**, the official MTEB harness, over the full 3,765-query official test split, with **non-windowed** dense embeddings.
- The regression numbers under investigation (`BM25 0.0631 / Dense 0.0010 / Hybrid 0.0322 / Reranked 0.0322`) were produced on **Path B**, the direct adapter, also over 3,765 queries, but with the **windowed** dense representation loaded through the broken `apps_fixed.npy` cache.

So: BM25 (lexical-only, unaffected by dense at all) tracks closely across both paths and both scorers (0.0631 direct-adapter vs. 0.06312 official — a ~0.002 gap fully explainable by scorer/MRR-cap differences alone). Dense and Hybrid do **not** track, but not because the paths disagree about what "healthy" dense retrieval looks like — because Path B's dense input was corrupted by the alignment bug, independent of which path was doing the scoring.

## Reproducibility status of the historical 0.08900 figure

**REPRODUCED** in the sense that it is Path A's own recorded output, produced by the same code (`run_mteb.py` + `search.py`) that still exists, unmodified by this session's fix, and traceable to `benchmark/results/mteb/appsretrieval_results.json` / `run_metadata.json` committed alongside it. This session did not re-execute Path A (network-blocked, per `DENSE-REGRESSION-INVESTIGATION.md` §10), so it is **NOT independently re-verified in this session**, but there is no evidence of any kind that it is wrong, stale, or produced by different code than what is currently in the repository — it was never touched by the windowing/precompute work that introduced the Path B bug.

## Recommendation

Do not present the Path B collapse numbers next to the Path A 0.08900 figure as if they measure the same thing getting worse. Once Path B's fix can be verified at full scale (see §10 of the investigation doc), the right comparison is: Path B BM25/Dense/Hybrid *before* vs. *after* the alignment fix, on the same 3,765 queries, with the same scorer — not Path B vs. Path A.

## Update, 2026-09-22 post-fix verification session

Re-checked in a follow-up session: `huggingface.co` is still blocked (same 403), and no local copy of the model or dataset exists on this container. Neither Path A nor Path B could be re-executed against the real corpus. The classification above stands unchanged: Path A's 0.08900 is **REPRODUCED in the sense of "traceable to an existing, untouched artifact"**, not independently re-run in either session. A mechanism-level before/after proof of the Path B fix (not a re-run of Path A or Path B themselves) is in `docs/audit/POST-FIX-RETRIEVAL-VERIFICATION.md`.

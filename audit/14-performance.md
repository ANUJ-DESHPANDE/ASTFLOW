# 14 · Performance

Measured on the audit machine (i7-14650HX, 15.7 GB RAM, CPU inference; Windows 11). Tools:
`audit/tools/perf_probe.py` (warm HTTP latency, 50 repetitions), `audit/tools/scale_perf.py` (in-process indexing,
search and memory on real repositories), cProfile, and the trust harness manifests. Raw data: `evidence/perf-*.json`.

**Measurement correction.** A first run of `scale_perf.py` (and the earlier graph-statistics and express-probe
scripts) used a fresh cache folder; ASTFLOW looks for the embedding model inside its cache, so those runs silently
fell back to lexical-only search. Their latencies/index times are **not** used below (kept as
`perf-scale-lexical-only-invalid.json` in the scratch area only). The script now passes the model by path and
asserts that dense retrieval is active. Structural counts (edges, components) do not depend on embeddings and remain
valid; the 8-question express probe compared two parsers under the same lexical-only condition.

## Search latency (in-process, `investigate()`, 30 questions per repo, semantic model active)

| Repository | Chunks | Before F-037 + F-045 | After | Hybrid `rank()` median (before → after) |
|---|---|---|---|---|
| demo fixture | 21 | P50 5.9 · P95 13.1 ms | P50 5.9 · P95 13.4 ms | 5.4 → 5.6 ms |
| expressjs/express | 3,120 | P50 135 · P95 174 ms | **P50 42.8 · P95 50.1 · P99 51.1 ms** | 84.6 → 11.0 ms |
| lodash/lodash | 4,463 | P50 158 · P95 205 ms | **P50 54.4 · P95 76.0 · P99 77.0 ms** | 93.1 → 11.4 ms |

(`perf-scale-before-f045.json` is after F-037 only; the lexical-only `plan()` profile showed 319/498 ms per query in
`plan()` before F-037.) Root causes found by profiling and fixed with bit-identical outputs:

| Fix | Cause | Effect | Proof of equivalence |
|---|---|---|---|
| F-019 `4cac3a9` | title field re-tokenised every chunk per query | lexical scoring 91.2 → 1.9 ms/query on 8,765 docs | 300 × 8,765 score arrays `np.array_equal` |
| F-037 `fb3e982` | `plan()` compiled one regex per symbol per query | express 319 → 1.3 ms, lodash 498 → 2.2 ms | identical plans, 36 query/repo pairs |
| F-045 `be291ba` | `rank()` compiled one regex per candidate row | express rank 72 → 15 ms, lodash 79 → 16 ms | identical order/scores/flags, 270 calls |

## Warm HTTP latency on the demo (50 calls each after one warm-up; `perf-api-before.json` → `perf-api-after.json`)

| Endpoint | Before P50 / P95 | After P50 / P95 |
|---|---|---|
| search (locate, agentic) | 30.6 / 34.6 ms | 30.9 / 32.7 ms |
| search (path, 2 passes) | 43.8 / 55.4 ms | 30.6 / 39.6 ms |
| compare v1 → v2 | 37.0 / 50.6 ms | 30.6 / 34.3 ms |
| source / map / trace / checkpoint | 15 / 16–28 ms | 14–16 / 18–27 ms |
| versions (git) | 344.8 / 362.4 ms | 365.8 / 411.1 ms (F-035, open) |

On Windows every loopback request carried ≈ 14 ms of fixed overhead (even trivial routes), so demo HTTP numbers are
dominated by transport, not by ASTFLOW.

## Indexing and memory (semantic model active, TS corroboration on)

| Repository | Cold index | Cached re-index (snapshot reused) | Process RSS after index |
|---|---|---|---|
| demo (11 files) | 0.56 s (model already loaded; first model load 8.4 s) | 0.04 s | 946 MB |
| express (141 files, 3,120 chunks) | 38.6 s | 0.79 s | 1.21 GB |
| lodash (27 files, 4,463 chunks) | 97.5 s | 1.84 s | 1.26 GB |

Cold indexing is dominated by CPU embedding of every chunk (MiniLM, `torch.set_num_threads(min(4, …))`); the
content-hash embedding cache makes later snapshots cheap (demo v2 reused 13 of 21 vectors). Baseline RSS with torch
and the model loaded is ≈ 0.9 GB. AppsRetrieval (8,765 documents) in the trust harness: median per query bm25 86.7 ms,
dense 146.6 ms, hybrid 158.7 ms at depth 1,000 (before F-019/F-045; harness runs are not latency benchmarks).

## Frontend

Production build (`evidence/build-after.log`): entry `index.js` 259.5 kB (81.3 kB gzip), `TraceGraph` 187.1 kB
(61.5 kB gzip) and `SourceViewer` (Monaco) 3,689 kB (953 kB gzip) — both loaded on demand. Vite warns about the Monaco
chunk (> 3,500 kB); it is lazy-loaded and served locally, so it affects first source-view time only. Lighthouse
performance scores were not recorded (benchmark jobs shared the CPU).

## Open

- F-035: `/api/versions` spawns ~15 `git` processes per call (≈ 350 ms); cache by refs state.
- Cold indexing of large repositories is CPU-bound in embedding; batching/threads are the lever if needed.

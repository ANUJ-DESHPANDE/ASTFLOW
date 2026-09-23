# ASTFLOW Retrieval — Session Handoff

_Last updated 2026-09-23. Contains only verified information._

## TRUST STATUS
Measurement system: **PARTIALLY VERIFIED** (the evaluator is verified; no retrieval run is)
Current trusted baseline: **CURRENT TRUSTED SCORE = UNKNOWN**
Target: ~0.20 NDCG@10

## EXACT CODE STATE
Repository: https://github.com/ANUJ-DESHPANDE/ASTFLOW
Branch: `main`
HEAD: the commit that added this file — check with `git log -1 -- ASTFLOW-HANDOFF.md` (parent `fc98ab5`)
Trusted baseline tag: **none** (`retrieval-trusted-baseline-v1` intentionally not created)
Working tree: CLEAN after that commit

## VERIFIED RETRIEVAL CONFIG (read from code, not docs)
Dataset: CoIR-Retrieval/apps (MTEB AppsRetrieval), expected revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5` — **not re-downloaded; counts below are expected, not re-verified**
Documents: 8,765 · Queries: 3,765 · Qrels: 3,765 pairs, exactly 1 relevant doc per query — per MTEB's own published stats; our download not re-verified
Embedding model: `sentence-transformers/all-MiniLM-L6-v2` · revision: not recorded anywhere yet
Chunk/window: none on the official path (one vector per document, 256 word-piece limit); windows 256/64 only in the direct adapter
BM25: BM25Okapi k1 1.6, b 0.75, positive IDF, identifier splitting, English+code stopwords
Dense: normalized dot product, threshold 0.05
Hybrid: RRF k=60, weights 1/1
Reranker: **ALIAS** — no reranker executes (`CROSS_ENCODER_AVAILABLE = False` hardcoded)
Candidate depth: 500 (benchmark requests 1,000)

## TRUSTED METRICS
None. Do not use 0.0631, 0.0707, 0.089, 0.0894 or 0.1184 as current — see RETRIEVAL-PROGRESS.md claims table.

## WHY WE TRUST / DO NOT TRUST THEM
ASTFLOW evaluator: PASS · trec_eval: PASS · ir_measures: PASS · MTEB: NOT RUN (its engine, pytrec_eval, PASS)
Cross-evaluator agreement: YES (synthetic golden + 1,000 randomized queries)
Second-machine reproduction: NOT YET DONE
Why no score: this environment cannot reach huggingface.co (HTTP 403, 8 checks), so the real model and dataset were never available here.

## CURRENT BOTTLENECK
**MEASUREMENT** — no trusted run of current code exists. Hint only (older code): Recall@100 ≈ 0.30.

## RETRIEVAL FORENSICS
Not yet measured. `benchmark/verify_retrieval.py` computes rank buckets and oracle ceilings @20/50/100/500 on the first real run.

## EXPERIMENT SCOREBOARD
| ID | Change | Before | After | Delta | Decision |
|---|---|---|---|---|---|
| BASE | Trusted baseline | — | not established | — | PENDING |

## IMPORTANT DISCOVERIES
- `0.0894` appears nowhere in the repo; the only `0.0707` is a 32-query Dense **MRR**.
- The `0.089` Hybrid result was produced by never-committed code (between `589e712` and `39cfe20`).
- `benchmark/results/apps.md` (3,765 q) and `apps.json` (32 q) are from different runs.
- "Reranked" is Hybrid under another name.
- MTEB/trec_eval re-sort tied scores by doc id descending; ASTFLOW sorts ascending. The new export freezes ASTFLOW's order.
- MTEB only drops queries whose key is absent; `run_mteb.py` includes all, so old official runs were not inflated.
- ASTFLOW's metrics.py is correct on binary qrels; its "MRR" is uncapped, not MRR@10.
- The dataset downloader used to fetch the *latest* revision; it now defaults to the pinned one.
- Dev/confirmation split is genuine, but old "tuned" full-test scores include the dev half.

## FAILED / DO NOT REPEAT
- Windowed dense via `apps_fixed.npy` without id alignment → Dense 0.0010. Reason: vector/document mismatch (fixed). Windowing itself is **unmeasured**, not failed.
- Retrying huggingface.co downloads in the cloud sandbox. Reason: org policy denial, 8 identical 403s.

## CURRENT ACTIVE EXPERIMENT
ID: BASE · Hypothesis: n/a (measurement) · Branch: `main` · Status: NOT STARTED (blocked on assets)

## EXACT NEXT ACTION
On the team laptop that can reach huggingface.co, run `python -m benchmark.mteb_appretrieval --download --download-only`, then `python -m benchmark.verify_retrieval --self-test` and `python -m benchmark.verify_retrieval --split all --tag baseline-v1`, and commit `benchmark/verification/`.

## FILES THE NEXT AGENT SHOULD READ
1. /ASTFLOW-HANDOFF.md
2. /RETRIEVAL-PROGRESS.md
3. /benchmark/EXPERIMENTS.md
4. /benchmark/VERIFICATION-MANIFEST.json
5. /benchmark/verify_retrieval.py and /benchmark/trust/

---

## COPY THIS INTO THE NEXT AI SESSION

You are continuing ASTFLOW (https://github.com/ANUJ-DESHPANDE/ASTFLOW, branch `main`), a code-search system evaluated on MTEB AppsRetrieval (CoIR-Retrieval/apps, revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`, expected 8,765 documents and 3,765 judged queries). Primary metric: NDCG@10. Long-term target: about 0.20.

**Trust status: the evaluator is verified; there is NO trusted retrieval score.** Do not treat 0.0631, 0.0707, 0.089, 0.0894, or 0.1184 as current. Older official MTEB runs (BM25 0.06104, Hybrid 0.08815, Hybrid 0.089) are real but were produced by older or uncommitted code. No `retrieval-trusted-baseline-v1` tag exists.

**Current pipeline (from code):** BM25 (rank_bm25, k1 1.6, b 0.75, identifier splitting, code stopwords) + Dense (all-MiniLM-L6-v2, one normalized vector per document, threshold 0.05) merged by Reciprocal Rank Fusion (k 60, weights 1/1). There is no reranker: `CROSS_ENCODER_AVAILABLE = False` is hardcoded and "reranked" aliases hybrid.

**Measurement system (built 2026-09-23):** `benchmark/verify_retrieval.py` ranks every judged query with the unchanged production `Retriever`, writes a frozen TREC run (SHA-256 recorded, canonical scores encode ASTFLOW's exact order), and scores the same file with ASTFLOW's metrics.py, pytrec_eval, ir_measures, a reference implementation, and NIST trec_eval (if built). It checks dataset integrity (duplicate/missing ids, pinned revision), vector integrity (finite, normalized, 20-document alignment probe against the real model), and writes forensics (first-relevant-rank buckets, BM25/Dense/Hybrid wins, oracle reranking ceilings @20/50/100/500) plus a manifest. Golden and randomized tests: `benchmark/test_trust_evaluation.py`, `benchmark/test_verify_retrieval.py`.

**Dominant bottleneck: MEASUREMENT.** The previous environment could not reach huggingface.co, so the current code has never been measured under this protocol.

**Do not repeat:** retrying huggingface.co from a sandbox that returns HTTP 403; using `apps_fixed.npy` windowed vectors without id alignment; reporting "Reranked" as a separate system; changing the evaluator during an algorithm experiment; tuning on confirmation or full-test queries.

**Exact next action:** on a machine with Hugging Face access, run
`python -m benchmark.mteb_appretrieval --download --download-only`,
`python -m benchmark.verify_retrieval --self-test` (must print PASS), then
`python -m benchmark.verify_retrieval --split all --tag baseline-v1`. Commit `benchmark/verification/`. If all evaluators agree and the corpus hash matches `ce25930a…`, record Trusted Baseline V1 in RETRIEVAL-PROGRESS.md, CURRENT_STATE.json and EXPERIMENTS.md, and create tag `retrieval-trusted-baseline-v1`. Then use the oracle ceilings to choose ONE first experiment: if Oracle@100 is far above the actual score, a real reranker; if not, candidate retrieval (e.g. an embedding comparison). Run it on an `exp/E001-...` branch, tune on dev queries only, and keep or reject by paired-bootstrap delta.

Before doing anything, read in order: ASTFLOW-HANDOFF.md, RETRIEVAL-PROGRESS.md, benchmark/EXPERIMENTS.md, benchmark/VERIFICATION-MANIFEST.json. Keep the discipline: frozen data, frozen evaluator, one change per experiment, independent scoring, KEEP/REJECT, document. When finished, update ASTFLOW-HANDOFF.md, RETRIEVAL-PROGRESS.md and benchmark/CURRENT_STATE.json.

Do not trust this summary blindly. First verify that HEAD, Git status, and the referenced files still match this handoff. If they do, continue from the EXACT NEXT ACTION above rather than restarting the audit.

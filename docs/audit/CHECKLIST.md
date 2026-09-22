# Master checklist

Checked = demonstrated within the report's stated limits. Unchecked rows retain the exact gap; they are not implied completed by related features.

## P0 / retrieval

- [x] Natural-language ranked snippet retrieval: actual API/source and full dataset runs.
- [x] Official AppsRetrieval/MTEB integration and full test split.
- [x] NDCG@10 and cutoff-specific MRR measured, artifacts generated.
- [x] BM25 baseline verified against its reference formula.
- [x] Real CPU embeddings, normalization and persistence verified.
- [x] Hybrid retrieval verified; official NDCG@10 .08815 versus BM25 .06104.
- [x] Agent refinement observed and benefit measured in controlled local ablations.
- [ ] Competitive retrieval quality: low absolute official scores; no external threshold/baseline comparison establishes competitiveness.
- [ ] Agent improvement generalises: local gain only .001691 NDCG, zero MRR; no held-out evidence.
- [x] Held-out dev/confirmation split methodology and BM25 tuning tooling built and unit-tested (`benchmark/build_dev_split.py`, `benchmark/analyze_corpus.py`, `benchmark/tune_bm25.py`); see `docs/audit/THEME1-LIVE-GAP-MATRIX.md`.
- [ ] Any of that tooling actually run against the real dataset: BLOCKED this session (huggingface.co unreachable from this sandbox); no BM25 k1/b tuning, stopword ablation, or token-truncation evidence exists yet. Do not treat the tooling's existence as a quality improvement — the retrieval scores above are unchanged.

## P1

- [x] Multiple Git versions supported, including explicit indexed revision aliases.
- [x] Version indexes isolated and source bytes immutable after indexing.
- [x] Re-indexing and cache reload measured.
- [x] Retrieval/source changes correctly across tested real commits.
- [x] Chunk-level content-hash embedding reuse implemented and unit-verified (unchanged chunks are never re-encoded across versions).
- [ ] Incremental update efficiency on a realistic large repository: reuse mechanism is unit-verified only; no real-corpus timing re-run performed. Unbounded in-memory snapshot retention and unbounded on-disk embedding-cache growth remain OPEN (see BUGS.md R02).

## Bonus

- [ ] Search across all versions simultaneously: NOT IMPLEMENTED.
- [ ] Global ranking: NOT IMPLEMENTED.
- [ ] Near-duplicate version handling: NOT IMPLEMENTED.
- [x] Version provenance in separate searches/comparisons; this alone does not complete bonus.

## Website

- [x] Main search, ranking details and exact source navigation.
- [x] Read-only source viewer, tabs, zoom, copy and fullscreen.
- [x] Graph and stable directional layout.
- [x] Version selector and real source comparison.
- [x] Agent trace returned and rendered; operational policy, not hidden reasoning.
- [x] Error, loading and lexical no-result states.
- [x] Mobile drawers, focus trap, Escape and reduced-motion mode.
- [x] Desktop Escape no longer hides the companion panel (B16, fixed and verified this session; was previously untested and broken).
- [ ] Double-click file-node drill-in in the map: tested this session and found BROKEN (B17, OPEN); the single-click + "Explore file" button path works.
- [ ] Every control's every failure state: see UI-INVENTORY for untested branches.
- [ ] First-time user comprehension/usability study: NOT RUN.

## Graph

- [x] Deterministic layout under reversed node/edge traversal.
- [x] Non-overlapping node placements on small, medium, large, dense and disconnected fixtures.
- [x] Clear call direction and relationship legend.
- [x] Search/center a loaded node, selected details and source opening.
- [x] Neighborhood highlighting, direction and depth controls.
- [x] Fit/reset and progressive cross-file call expansion.
- [ ] Large production graph usability: bounded rendering verified, user study and worst-case hubs not established.
- [ ] Complete containment/import/inheritance hierarchy: NOT IMPLEMENTED; only calls claimed.

## Engineering

- [x] Backend unit/integration suites pass, optional semantic run separately passes.
- [x] Browser E2E and layout checks pass in Edge/Chromium.
- [x] API edge cases and security guards tested; 40 status/JSON probes pass.
- [x] Security source review plus known-advisory dependency scans.
- [x] Performance measured with explicit synthetic and timing limitations.
- [x] Dead/unused surface identified; runtime placeholder and request field do not activate a feature.
- [x] Errors made actionable; source corruption recovery and network failures tested.
- [ ] Concurrent load, extreme filesystem conditions, peak RAM and full evaluation-environment dependency scan: NOT VERIFIED.
- [ ] Full response-contract generation/type validation: NOT IMPLEMENTED.

## Submission

- [x] Required official framework result JSON produced.
- [x] README commands for app, tests, official evaluation and Docker provided.
- [x] Fresh source archive, new venv, npm ci/build, demo/source/search/version smoke pass with semantic off.
- [x] Demo Git history reproducibly recreated from tracked JS files.
- [x] Real CPU semantic functionality separately verified; no fallback relabelled as dense.
- [x] No fabricated benchmark claims; old limited results distinguished from full MTEB.
- [ ] Fresh semantic installation end-to-end on another machine: NOT VERIFIED.
- [ ] Container build/run: daemon unavailable; Docker files provided, execution UNVERIFIED.
- [ ] Structurally audited real OSS repository frozen to exact commit: still required.
- [ ] PPT claims correspond to verified implementation: no final PPT supplied/created for review.
- [ ] ≤5-minute demo video and final presentation named as required: outstanding.
- [ ] Final public/shared GitHub release/tag/assets and organiser submission: outstanding; no publication performed.
- [ ] Organiser clarification of CSV/JSON, JS/Python and conflicting bonus wording: outstanding.

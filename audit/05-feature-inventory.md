# 05 · Feature inventory

Evidence sources: runtime control crawl before/after (`evidence/ui-crawl-before.json`, `evidence/ui-crawl.json`),
API probe (`evidence/api-probe.json`), Playwright suites (`evidence/playwright-before.log`, `-after.log`), backend tests,
and measurements on real repositories (`12-graph-audit.md`). "Before" = start of audit (`f0f2fc9`); "After" = this branch.

| # | Feature | UI | Backend | Connected | Before | After | Tested by | Recommendation |
|---|---|---|---|---|---|---|---|---|
| 1 | Setup + demo startup (`npm run setup`, `npm run demo`) | — | CLI | — | **BROKEN** (fixture was a dangling gitlink; setup and demo fail) | WORKING | clean clone, 08-runtime-startup | KEEP (fixed `b2ea145`) |
| 2 | Explorer file tree, filter, open in tabs, close tabs, zoom, copy, fullscreen | yes | `/api/source` | yes | WORKING | WORKING | studio/audit specs, crawl | KEEP |
| 3 | Natural-language search in the companion (ranked snippets with file:line) | yes | `/api/search` | yes | WORKING, but **misleading** for no-evidence queries ("Here's the relevant code" for dense-only neighbours) | WORKING, honest `match_basis` heading | journeys, audit specs, `test_api_contract` | KEEP (fixed) |
| 4 | Agentic second pass (plan / observe / refine) + investigation log | yes (details) | `investigate()` | yes | WORKING (log said "rerank") | WORKING ("rank") | journeys (path question), `test_core` | KEEP |
| 5 | Retrieval modes (BM25 / dense / hybrid) | **no UI selector** | `Retriever.rank` | n/a (hybrid only in product; modes used by benchmark) | WORKING | WORKING; unknown modes now rejected | `test_retrieval_modes` | KEEP |
| 6 | "Reranked" mode / cross-encoder reranker | none | env-flag `ASTFLOW_RERANKER_ENABLED`, `reranker.py` | hidden | **MISLEADING / HARMFUL** (E002: −0.019 NDCG@10) | REMOVED from product | `test_retrieval_modes` | REMOVED (`aa14805`) |
| 7 | Exact source view with highlighted lines (Monaco) | yes | `/api/source` | yes | WORKING (uncaught `Canceled` on tab switch) | WORKING | journeys, studio | KEEP (fixed F-034) |
| 8 | Map: file overview, file focus, node select, neighbourhood depth/direction, hide unrelated, explore calls, search nodes, fit/reset | yes | `/api/map` | yes | WORKING on the fixture; **near-empty on real repos** (99% isolated nodes) | WORKING; real repos 20–65× more edges (TS-confirmed); CommonJS still unresolved | audit/studio specs, 12-graph-audit | KEEP; COMPLETE CommonJS resolution (F-029) |
| 9 | Trace a path between symbols; edge → call-site evidence | yes | `/api/trace` | yes | WORKING | WORKING (also on phone viewport) | studio, journeys | KEEP |
| 10 | Sequence (lexical order) evidence | yes | resolver `sequences` | yes | WORKING (conservative; abstains for >2 named symbols) | WORKING | audit spec | KEEP |
| 11 | Compare two snapshots: summary, changed-symbol picker, Monaco diff, before/after snippets, copy | yes | `/api/compare` | yes | WORKING, but **uncaught page error** when leaving the diff; drawer covered the diff on tablet/phone | WORKING | studio, audit specs, crawl | KEEP (fixed F-032/F-033) |
| 12 | Snapshot selector (working tree, HEAD, tags, commits) + passive change notice + "Update snapshot" | yes | `/api/versions`, `/api/checkpoint`, `/api/index` | yes | WORKING (`/api/versions` 345 ms per call) | WORKING | journeys (v1 source), studio | KEEP; cache versions (F-035) |
| 13 | Repository dialog (open any local path / revision, focus trap, Escape) | yes | `/api/index` | yes | WORKING | WORKING | studio, journeys | KEEP |
| 14 | Unresolved-calls list in the companion | yes | `/api/map` `unresolved` | yes | WORKING | WORKING | crawl, diag | KEEP |
| 15 | "Explain" button / "Explain this code" chip | yes | — (toggles panel / runs a templated search) | yes | **MISLEADING NAME** (no explanation is generated; generation is out of S1 scope) | Renamed "Ask" / "Find related code" | studio, journeys | KEEP (renamed) |
| 16 | Keyboard: Ctrl+K focuses composer, Escape closes dialog/drawers, dialog focus trap | yes | — | — | WORKING | WORKING | audit, studio specs | KEEP |
| 17 | Mobile/tablet drawers (explorer, companion) | yes | — | — | PARTIAL (drawer auto-opened over the diff; results opened under the drawer) | WORKING | studio mobile, journeys phone, a11y mobile | KEEP (fixed F-033) |
| 18 | API docs pages `/docs`, `/redoc` | — | FastAPI default | — | **BROKEN** (blank: CDN blocked by CSP) | REMOVED (404); `/openapi.json` kept | `test_api_contract` | REMOVED |
| 19 | CLI: `index`, `search`, `compare`, `serve`, `model-download`, `demo`, `benchmark` | — | `cli.py` | — | WORKING (demo broken by #1) | WORKING | CI, runs in this audit | KEEP |
| 20 | Local 16-query benchmark (`benchmark.evaluate`, `ablate`) | — | benchmark | — | WORKING; committed table produced **without** the model | WORKING (re-run with model: `evidence/local-bench`) | — | KEEP; label clearly (not a quality claim) |
| 21 | Frozen trust harness (`verify_retrieval`, evaluators, forensics) | — | benchmark | — | WORKING with gaps (undeclared evaluator deps; git state recorded at end; E003 regression) | WORKING | harness tests, reproduction | KEEP (fixed F-002, F-022, F-024) |
| 22 | Official MTEB runner | — | `run_mteb.py` | — | PARTIAL (scored tie-broken order, no commit provenance, artifacts from old code) | WORKING; artifacts for current code match the harness | eval-venv tests, artifacts | KEEP (fixed F-020/F-036) |
| 23 | TypeScript language-service corroboration | — | `tools/ts_enrich.mjs` | — | WORKING (corroborates only, `edges_added` always 0 — stated honestly) | WORKING; used as precision oracle for F-023 | `test_enrichment` | KEEP |
| 24 | Version-aware embedding reuse (content-hash cache) | — | `embedding_cache.py` | — | WORKING (v2 reused 13/21 vectors) | WORKING | manifests | KEEP |
| 25 | Runtime tracing (`runtime_trace_id`) | — | rejected with 400 | — | STUB, honestly rejected | STUB, honestly rejected | probe | KEEP as explicit "not enabled" |
| 26 | `backend/app/runtime/` package | — | empty | — | STUB (documented "reserved") | unchanged | — | KEEP (documented) |
| 27 | Evolutionary (all-version) retrieval — S1 bonus | none | none | — | MISSING | MISSING | — | BUILD later (out of this remediation) |
| 28 | Docker image | — | `Dockerfile` | — | UNKNOWN (fixture missing would have broken the demo inside the image) | UNVERIFIED (Docker not installed here); fixture now present | — | INVESTIGATE on a Docker host |

**Summary (after):** working 22 (incl. #15, renamed) · partial 0 · broken 0 · removed 2 (#6 reranker path, #18 blank docs
pages) · missing 1 (#27, bonus) · unverified 1 (#28) · stubs honestly reported 2 (#25, #26).
**Before:** broken 2 (#1, #18) · misleading/harmful 3 (#3, #6, #15) · partial 5 (#8 on real repos, #11, #17, #21, #22).

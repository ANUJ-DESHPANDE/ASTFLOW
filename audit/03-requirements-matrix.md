# 03 · Requirements traceability

## Sources inspected

| ID | Source | Notes |
|---|---|---|
| **S1** | `C:\Users\aarus\Downloads\Samsung_PRISM_Theme1_Agentic_Code_Intelligence.pdf` (3 pages) | "Clean reference copy compiled from the official Theme 1 guideline PDF and hackathon brief". The original `theme1_guidelines.pdf` and hackathon brochure cited by `docs/audit/REQUIREMENTS.md` are **not present on this machine**; S1 is the primary source used. |
| S2 | `README.md` | Product claims (treated as claims to verify, not requirements). |
| S3 | `docs/audit/REQUIREMENTS.md` (20 Sep audit) | Earlier matrix; cites G (guideline, 4 pp) and B (brochure, 15 pp) and records conflicts between them (CSV vs JSON; JS vs Python dataset). Used only where S1 is silent. |
| S4 | `benchmark/EXPERIMENTS.md`, `RETRIEVAL-PROGRESS.md` | Engineering/experiment protocol requirements. |
| — | Hackathon PPT, mockups, issue tracker | **Not found** (no PPT in the repo or in the checked user folders; GitHub issues not inspected — no credentials used). The two `.docx` files in Downloads are prompt documents, not requirements. |

Status legend: VERIFIED · PARTIAL · MISSING · CONTRADICTED · UNCLEAR · NOT APPLICABLE. "Evidence" points to files under `audit/`.

## 1. Competition requirements (S1)

| # | Requirement | Source | Required? | Implementation | Test / evidence | Status |
|---|---|---|---|---|---|---|
| C1 | Rank code snippets for a natural-language query | S1 p1, P0 | Yes (P0) | `retrieval/search.py`, `agent/investigate.py`; `POST /api/search` | `backend/tests/test_core.py`, `api-probe.json` ("search valid" → openBluetoothSettings #1) | VERIFIED (functional) |
| C2 | Retrieval accuracy on CoIR AppsRetrieval test split, NDCG@10 and MRR | S1 p2 | Yes (screening) | trust harness `benchmark/verify_retrieval.py`; `benchmark/run_mteb.py` | baseline-v1: Hybrid NDCG@10 0.08840, MRR@10 0.07257 (4 evaluators agree); re-reproduced in this audit, see `02-retrieval-baseline.md` | VERIFIED (measured) — quality is low in absolute terms |
| C3 | Use MTEB to run AppsRetrieval and produce the evaluation artifact | S1 p2–3 | Recommended / submission | `benchmark/run_mteb.py` (MTEB 2.21.0) | Committed MTEB JSONs are from older code states (0.06104 / 0.08815 / 0.089); **no MTEB artifact for the current code** | PARTIAL → regenerated in this audit (see 02) |
| C4 | CPU operation; small/fast models; minimal GPU | S1 p1, p3 | Yes | MiniLM on CPU (`Embedder` hard-codes `device="cpu"`), BM25 in SciPy | demo runs on CPU; E003/E004 CPU timings | VERIFIED |
| C5 | Query categorisation / pre-processing / multiple retrieval passes | S1 p1 ("what the solution looks like") | Suggested approach | `agent/investigate.py` `plan()` (regex intents), conditional second pass | `test_agent_refines_from_observed_symbols`; `docs/audit/ablations.json` (negligible measured gain) | PARTIAL (exists; rule-based; no measured benefit on AppsRetrieval — the benchmark path runs with `boosts=False` and no agent) |
| C6 | P1: retrieval on different versions; rebuild indexes/caches in reasonable time | S1 p2 | Yes (P1) | content-addressed snapshots (`indexing/service.py`), `embedding_cache.sqlite` reuse, `/api/versions`, `/api/compare` | `test_api_versions.py`, `test_audit_reliability.py`; demo manifests: v2 index 682 ms reusing 13/21 embeddings | VERIFIED on the demo; scale evidence limited (see 16-feasibility) |
| C7 | Bonus: evolutionary retrieval across all versions | S1 p2 | Bonus | none — compare runs two independent searches | `versions/compare.py` | MISSING |
| C8 | Submission: PPT, demo video, GitHub repo with instructions, generated evaluation artifact | S1 p3 | Yes | README; no PPT/video in repo | repository inventory | PARTIAL (repo + instructions + artifact; PPT/video out of scope of code) |
| C9 | Plain-English question → snippets with file and line locations | S1 p3 | Yes | results carry `file_path`, `start_line`, `end_line`, snippet; Monaco highlights lines | `api-probe.json`; E2E `studio.spec.ts` "live question shows … exact source" | VERIFIED |
| C10 | Structural queries ("which files call X before Y") | S1 p3 | Yes | resolver `sequences`, `SequenceEvidence`, `/api/trace` | `test_core.py` sequence tests; `audit.spec.ts` "positive sequence evidence" | PARTIAL (conservative envelope; abstains on control flow) |
| C11 | Usage queries ("where is the Bluetooth-settings deeplink used") | S1 p3 | Yes | USAGE intent → caller expansion | demo query in README | VERIFIED on demo (see 11-e2e) |
| C12 | Agentic: plan, search, read, refine over a codebase larger than the context window | S1 p3 | Yes | `investigate()` PLAN→SEARCH→OBSERVE→REFINE→SEARCH→STOP | agent trace in every response | PARTIAL (bounded rule policy, ≤2 passes; no LLM) |
| C13 | Single language: JavaScript | S1 p3 | Yes | `.js/.mjs/.cjs/.jsx` discovery; tree-sitter-javascript | parser tests | VERIFIED (JS only; the benchmark dataset is Python text — S3 records this conflict) |
| C14 | Code-aware embeddings / vector search + AST or call-graph indexing | S1 p3 | Yes | MiniLM (general text model, not code-aware) + tree-sitter AST + NetworkX call graph | manifests | PARTIAL (embeddings are not code-specific) |
| C15 | Report precision@k, recall, latency, indexing cost | S1 p3 | Yes | `benchmark/evaluate.py` (local), trust harness (recall), manifests (latency, index time) | `benchmark/results/local.md`, manifests; `14-performance.md` | PARTIAL → reported in 14-performance and the final report |
| C16 | Generation/explanation after retrieval is out of core scope | S1 p1 | Constraint | "Explain" button only toggles the companion; no generative model | source inspection | VERIFIED (no generation) — naming implies explanation, see F-015 |

## 2. Product requirements (S2 claims turned into testable requirements)

| # | Claim | Implementation | Evidence | Status |
|---|---|---|---|---|
| P1 | `npm run setup` + `npm run demo` works from a clone | `scripts/setup.mjs`, `scripts/start.mjs`, `scripts/setup_demo.py` | clean clone FAILED at setup_demo (fixture missing) → fixed in `b2ea145`; re-verified in 08 | CONTRADICTED at start → fixed |
| P2 | Lexical fallback when the model is unavailable | `Embedder.load` fallback, `ASTFLOW_SEMANTIC=off` | `test_regressions.py`; 11-e2e | see 11 |
| P3 | Loopback-only, Host/Origin validation, traversal-safe source API | `main.py` middleware + `/api/source` checks | `api-probe.json` 66/66 | VERIFIED |
| P4 | Map, Trace, Compare, Code views; companion with investigation log | `App.tsx`, `TraceGraph.tsx` | `ui-crawl.json`, 09/11/12 | see 09 |
| P5 | "Reranked" / reranker | UI has no mode selector; backend `ASTFLOW_RERANKER_ENABLED` routes through the E002 cross-encoder (rejected: −0.0187 NDCG@10) | `search.py`, `config.py`, E002 | CONTRADICTED (hidden, quality-reducing option) → F-014 |
| P6 | Docker image builds and runs | `Dockerfile`, `scripts/container_start.py` | Docker not installed here | UNCLEAR (unverifiable here; README already says UNVERIFIED) |
| P7 | API docs at `/openapi.json` (README says docs scripts intentionally not loaded) | FastAPI default `/docs` still served | `/docs` HTML references cdn.jsdelivr.net, blocked by the app's own CSP | PARTIAL (openapi.json works; `/docs` is a broken page) → F-016 |

## 3. Engineering requirements (S4)

| # | Requirement | Evidence | Status |
|---|---|---|---|
| E1 | Frozen, checksummed baseline; evaluator cross-check | `manifest-baseline-v1.json` (4 evaluators, not 5 as some docs say; generated from an unpublished dirty commit `7df804f8`) | PARTIAL → reproduced in this audit (02) |
| E2 | Pre-registration, dev → confirmation once, bootstrap CI | `EXPERIMENTS.md` E001–E004 | VERIFIED |
| E3 | Tests pass on a clean checkout | 6 failed + 7 errors at start (fixture, E003 regression) → 89 passed / 1 skipped after fixes | CONTRADICTED at start → fixed |
| E4 | CI | none | MISSING → added (35) |

## 4. Nice-to-have

| # | Item | Status |
|---|---|---|
| N1 | Evolutionary (all-version) retrieval | MISSING (bonus; not attempted in this remediation) |
| N2 | Code optimisation suggestions (S3 brochure bonus; conflicts with S1's retrieval focus) | NOT APPLICABLE |
| N3 | TypeScript-source indexing | MISSING (out of S1 scope: single language JavaScript) |

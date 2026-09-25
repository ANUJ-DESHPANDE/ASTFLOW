# 18 · Remediation plan (ordered) and execution record

Order: P0 → architectural blockers → broken core workflows → misleading/stub features → P1 → retrieval → UX →
performance → P2 → P3. "Done" items were implemented in this audit, each as its own commit on
`audit/master-remediation`, with the listed test.

## Done

| Order | ID | Why | Files | Implementation | Test / acceptance | Regression risk | Commit |
|---|---|---|---|---|---|---|---|
| 1 | F-001 P0 | Setup/demo broken on every clone | `examples/demo-repo/**`, `.gitattributes` | restore fixture sources; LF pin | clean clone → `npm run setup` → demo healthy (08); v2 == `31b94fc` | low | `b2ea145` |
| 2 | F-002 P1 | Harness tests broken by E003 | `benchmark/verify_retrieval.py` | `getattr` default | 7 harness tests pass | none | `41fcee0` |
| 3 | F-014 P1 | Harmful rejected reranker reachable; misleading flag | `retrieval/search.py`, `config.py`, `reranker.py` (deleted) | remove; reject unknown modes | `test_retrieval_modes` | low (fingerprint changes → indexes rebuild once) | `aa14805` |
| 4 | F-019 P2 | 91 ms/query title scan | `retrieval/search.py` | precompute title tokens | bit-identical scores (300×8,765) | none | `4cac3a9` |
| 5 | F-023 P1 | Graph empty on real repos | `structure/resolver.py` | nested-scope identifier calls | 6 resolver tests; 1,820 added edges all TS-confirmed | low (precision verified) | `52063cf` |
| 6 | F-022 P2 | Evaluators undeclared | `pyproject.toml`, `requirements-mteb.txt` | pin versions | eval-venv tests 7/7 | none | `8b6713c` |
| 7 | F-024 P3 | Wrong provenance on long runs | `verify_retrieval.py` | git state at start | harness tests | none | `4e9622d` |
| 8 | F-042 P2 | MTEB runs without provenance | `run_mteb.py` | record commit/dirty files | metadata fields present | none | `3d47567` |
| 9 | F-011 P1 | Nonsense results called relevant | `investigate.py`, `App.tsx`, types | `match_basis` + honest heading | `test_api_contract`, `journeys` | low | `c992b87`, `4746151` |
| 10 | F-016/F-017 P3 | Blank docs pages; "rerank" label | `main.py`, `investigate.py` | disable docs; RANK | `test_api_contract` | none | `dc0365a` |
| 11 | F-036 P1 | Official artifact scored a non-product order | `run_mteb.py` | rank-preserving scores | MTEB == harness (0.0884 / 0.07257) | none (lowers the number) | `f0a88b3` |
| 12 | F-020 P1 | No MTEB artifact for current code | `benchmark/results/mteb-current-*` | regenerate | NDCG/MRR match harness to 4–5 dp | none | `c42b78a` |
| 13 | F-037 P2 | 319–498 ms `plan()` on real repos | `investigate.py` | substring pre-filter | identical plans on 36 query/repo pairs | none | `fb3e982` |
| 14 | F-025/026/027 | a11y critical/serious; favicon | `App.tsx`, `studio.css`, `SourceViewer.tsx`, `index.html` | semantics, contrast, labels | axe gate 0 serious/critical; Lighthouse 1.00 | low | `4746151` |
| 15 | F-032/F-034 | Uncaught page errors | `SourceViewer.tsx` | keep diff models; swallow Monaco cancellations only | crawl (09), studio test | low | `4746151` |
| 16 | F-033 P2 | Drawer covers results on narrow screens | `App.tsx` | narrow-screen behaviour | `journeys` phone trace; diag | low | `4746151` |
| 17 | F-015 P2 | Misleading "Explain" | `App.tsx`, README | rename | studio/journeys | low | `4746151` |
| 18 | F-010/F-012 | Stale/obsolete E2E | `frontend/e2e/*` | replace/fix | 28/28 | none | `46a3d28` |
| 19 | F-040 P2 | No CI | `.github/workflows/*` | PR validation + manual benchmark | YAML parses; all commands run locally | none | `275fe27` |
| 20 | F-039 P2 | README contradicted by evidence | `README.md`, status docs | correct | review | none | docs commit |

## Rejected during implementation (with evidence)

- Parser heuristics for test directories and property-path names: made an 8-question express probe worse
  (MRR@10 0.446 → 0.365). Reverted; `evidence/rejected-parser-heuristics.md`.

## Remaining (ordered)

| Order | ID | Why | Files | Implementation | Test / acceptance | Regression risk |
|---|---|---|---|---|---|---|
| 1 | F-044 P1 | Retrieval accuracy is the S1 P0 criterion and is low (0.0884) | benchmark, retrieval | E004 is pre-registered but cancelled for now by the owner; resume it or E005 (offline NL descriptions; needs a model/licensing decision) | Ledger rule: Hybrid NDCG@10 CI excludes 0 on dev and confirmation | experiment-gated |
| 2 | F-029 P2 | No cross-file edges for CommonJS | `structure/resolver.py`, `parsing/javascript.py` | `require('./x')` + `module.exports`/`exports.y` bindings; member calls on those bindings only | TS corroboration ≥ 99% on express/lodash + a hand-judged sample; demo unchanged | medium |
| 3 | F-038 P2 | Tests crowd real-repo results | parser, `search.py` | test-directory detection without test descriptions in the title field | judged set of ≥ 30 questions on 2 repos; no regression on the demo benchmark | medium |
| 4 | F-030 P2 | Overview unreadable at scale | `TraceGraph.tsx`, `/api/map` | directory clusters; connected files first | E2E on a generated 150-file fixture | low |
| 5 | F-021 P2 | Unreviewable one-line frontend | `frontend/src/*` | formatter-only commit | build + 28 E2E unchanged | low |
| 6 | F-035 P3 | `/api/versions` 345 ms | `discovery.py` | cache keyed by refs/HEAD | API probe + perf | low |
| 7 | F-031 P3 | `anonymous@` labels | parser/UI | display-only names | graph E2E | low |
| 8 | F-018 P3 | Duplicate app instance | `main.py`, `cli.py` | lazy module-level app | startup test | low |
| 9 | F-041 P3 | Docker unverified | `Dockerfile` | build + run on a Docker host | health + demo journeys | external |

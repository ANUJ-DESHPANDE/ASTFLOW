# ASTFLOW — SUBMISSION READY

- **Commit:** product code frozen at `db57806` (float32 inference); documentation at `db97770` and this dashboard;
  merged into `main` by merge commit.
- **Release:** [`v1.0-submission`](https://github.com/ANUJ-DESHPANDE/ASTFLOW/releases/tag/v1.0-submission). It
  carries `appsretrieval_results.json` (SHA-256 `dc9a984f…6fa6`, identical to the committed file) and the published
  corpus vectors `apps-corpus-vectors-gte-modernbert-base.npz`.
- **CI:** `ci` green on the final code: #34 (`db57806`) and #35 (`ca023da`): lint, 110 Python tests, build, audits,
  28/28 browser tests, Docker. `main` was green before the merge (#21, `009f3e3`).

## Official retrieval

- **Model:** `Alibaba-NLP/gte-modernbert-base` (149M, Apache-2.0)
- **Mode:** dense (cosine), 512-token cap, no fusion, CPU
- **Scores:** MTEB 2.21.0 AppsRetrieval, 3,765 queries × 8,765 documents, commit `036060e`, clean tree

| Metric | Value |
|---|---:|
| NDCG@10 | **0.5511** |
| MRR@10 | **0.5053** |
| R@10 | 0.6967 |
| R@50 | 0.8483 |
| R@100 | 0.8943 |

## Product integration

- **Default model:** `Alibaba-NLP/gte-modernbert-base`, verified at runtime on a clean clone (`/api/health`, start-up
  line, UI).
- **Default retrieval mode:** dense first stage (the frozen scoring). On top of it, the agent adds exact-symbol
  evidence, at most one refinement pass and call-graph expansion.
- **Precision:** float32 on CPU. The evaluation used the checkpoint's float16, which ran 6× slower on common CPUs.
  Vectors agree at cosine ≥ 0.9995. Disclosed in the freeze record.
- **Clean clone:** PASS. 0 manual steps; setup 101 s, demo ready 12 s, `.venv` 1.6 GB.
- **Silent fallback possible:** No. A missing model gives an actionable error (API 503, CLI exit 2); lexical-only
  mode must be chosen explicitly (`ASTFLOW_SEMANTIC=off`) and is labelled everywhere.

## P0

- **Plain-English retrieval:** PASS. "where is the redirect location URL encoded" puts `location` #1 on all three
  express versions (semantic #1). T1 is PARTIAL: the answer is #2, below the related `req.accepts`.
- **File/location output:** PASS. Every result has `file:start–end` plus the exact snippet; 100% of checked snippets
  match the selected version's source.

## P1

- **Version retrieval:** PASS. Express 4.18.2 / 4.19.2 / 4.21.2 (real Git tags) through the API and UI; snippets
  equal `git show <tag>`; the selector, source and results always refer to one snapshot.
- **Incremental indexing:** PASS. 4.19.2 reused 2,955 of 3,262 vectors (79 s on AMD, 46 s on Intel); 4.21.2 reused
  2,888 (93 s / 52 s).

## Structural intelligence

- **Usage queries:** PASS. "Where is compileQueryParser used?" returns the caller `app.set` via the call graph (1
  hop); the demo usage question returns its only caller.
- **Call graph:** PASS. `IntentRouter.route` callers and callees exact; the trace path is SUPPORTED; call-order
  evidence is correct (fixed in this pass).
- **Large-repo graph:** PARTIAL. The express map is bounded (150 of 152 files) and readable, but most express calls
  are member or dynamic calls and stay unresolved (shown as such).

## Judge walkthrough

- **Tasks attempted:** 13 (API) + 2 browser journeys
- **Results:** 9 PASS, 3 PARTIAL, 1 FAIL
- **FAIL:** T5, "Where is view template rendering implemented?", render methods at #9
- **Biggest confusion:** English words that are also symbol names get "Exact symbol" and a boost (T1, T5), and
  generated test-callback names clutter large-repository lists. Open finding J-1: ranking is frozen, so it is not
  tuned; the demo avoids it.

## Tests

| Suite | Result |
|---|---|
| Python | 110 passed, 2 skipped (optional TS/MTEB) |
| Browser | 28 / 28 (CI e2e, real backend with GTE) |
| API | covered in Python (`test_api_*`, `test_frozen_product.py`) + walkthrough API |
| E2E | journeys, studio, audit specs; plus the clean-clone walkthrough 2 / 2 |
| Accessibility | axe gate: 0 serious/critical at desktop and phone sizes |

## Performance (4 vCPU CPU runners)

| Step | Time |
|---|---|
| Initial indexing, express (3,226 chunks) | 712 s (AMD EPYC 7763) · 375 s (Intel Xeon 8573C) |
| Incremental indexing, next release | 79–93 s (AMD) · 46–52 s (Intel) |
| Short query | P50 266 ms |
| Long query (1,880 characters) | P50 1.66 s; official harness full 512-token statements P50 4.27 s (float16) |
| Ranking | P50 27.7 ms |
| Memory | peak RSS 1.96 GB |

## Hackathon rubric evidence

- **Working prototype:** clean clone, 0 manual steps, walkthrough 9/3/1, 28/28 browser tests, dataset-style queries
  via published vectors.
- **Technical depth:** code-retrieval embedder chosen by a pre-registered protocol; AST and call graph;
  content-addressed versions; CPU diagnosis (float16 vs float32).
- **Innovation:** evidence-carrying answers (spans on results and edges), honest match labels, version-aware reuse.
- **Theme relevance:** every Theme 01 capability is mapped to a feature (`audit/HACKATHON-RUBRIC-EVIDENCE.md`).
- **Presentation and docs:** README, technical story, demo script and queries, evidence pack. No PPT or video yet.

## Demo

- **Primary query:** "where is the redirect location URL encoded" (express 4.21.2)
- **Structural query:** "Where is compileQueryParser used?" (express), plus the call-order question on the demo
- **Version query:** the primary query on 4.18.2 → 4.19.2 → 4.21.2
- **Fallback:** "Where is openBluetoothSettings used?" (demo repository, cached)
- **Estimated duration:** 5:00 (`submission/DEMO-SCRIPT.md`)

## Submission

| Item | Location |
|---|---|
| GitHub repo | https://github.com/ANUJ-DESHPANDE/ASTFLOW (`main`) |
| Release | `v1.0-submission` |
| MTEB JSON | `benchmark/results/mteb-final-gte/appsretrieval_results.json` (and the release asset) |
| README | updated: frozen defaults, costs, limitations |
| PPT evidence | `submission/PRESENTATION-EVIDENCE.md` |
| Demo script | `submission/DEMO-SCRIPT.md`, `submission/DEMO-QUERIES.md` |

## Remaining blockers

1. Organiser confirmation of the submission window: the slide says 11–25 Sep, and this work is dated 26 Sep.
2. The demo video and PPT have not been recorded or produced. They are the team's to make from the script and
   evidence pack.
3. None in the product. Open non-blocking findings: J-1 (exact-name boost on English words), J-2 (test-callback
   names), J-3 (long version list), J-4 (precision not shown in the UI line).

## PRODUCT STATUS

**FROZEN** (26 Sep 2026). No architecture, retrieval or dependency changes; only submission-artifact corrections or
genuine blockers.

## NEXT EXACT ACTION

Record the ≤ 5-minute demo video following `submission/DEMO-SCRIPT.md` on a machine prepared the day before.

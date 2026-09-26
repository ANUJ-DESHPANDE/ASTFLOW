# ASTFLOW — Final submission readiness (2026-09-26)

Branch `claude/vibrant-goodall-tof53x` (builds on the 25 Sep engineering audit, `FINAL-ASTFLOW-ENGINEERING-REPORT.md`).
Every claim below was re-run or measured today unless marked *carried over*; numbers carried over were checked
against committed artifacts, not re-derived.

> **Deadline check.** The submission slide gives the build window as **11–25 Sep**; this report is dated 26 Sep. If the
> screening upload closed on 25 Sep, the remaining value of this work is the hands-on round (top 15 announced 9 Oct:
> PPT, demo video, running the code on dataset-like queries, P1 and bonus). Confirm with the organisers.

## Official requirements (source of truth: the Agentic Code Intelligence PDF + the two slides)

| # | Requirement | Where it comes from | Status |
|---|---|---|---|
| R1 | Rank code snippets for a natural-language query (P0) | PDF p1 | **Met** — repository search (UI/API/CLI) and snippet-corpus search (`astflow snippets`) |
| R2 | Screening: CoIR AppsRetrieval **test**, MTEB, NDCG@10 and MRR, JSON from MTEB | PDF p2–3 | **Met** for the committed system (MTEB 2.21.0 JSON in `benchmark/results/mteb-current-hybrid/`); see Retrieval |
| R3 | JSON uploaded as a **GitHub Release** asset | PDF p3 | **Not done — no release exists** (checked via API). Needs the owner's authorisation. |
| R4 | P1: retrieval on different versions; rebuild indexes in reasonable time | PDF p2 | **Met** — see P1 |
| R5 | Bonus: evolutionary retrieval across versions (near-duplicate snippets) | PDF p2 | **Partial** — cross-version snippet search folds identical snippets; no learned near-duplicate ranking |
| R6 | CPU operation, minimal GPU | PDF p1 | **Met** — all measurements on 4-vCPU CPU |
| R7 | Hands-on: runs on "queries similar to the dataset" | PDF p3 | **Met after today's fixes** — 32k-character queries (was rejected over 2,000 with HTTP 422); `astflow snippets` runs full problem statements against the CoIR corpus |
| R8 | Demo shows responses to queries and speed, not just numbers | PDF p4 | **Met** — script in `docs/DEMO-SCRIPT.md`; UI now prints "ranked in N ms on CPU" |
| R9 | PPT with approach details and a tough query | PDF p4 | Evidence pack below; deck not produced (not requested) |
| R10 | Repo with run instructions; Docker & other requirements (slide) | slide | README verified; Docker now built and queried in CI (F-041) |
| R11 | Structural and usage queries; agentic plan/search/read/refine; JavaScript (Theme slide) | slide | **Met** within a conservative static envelope; CommonJS now resolved |
| — | Generation/explanation after retrieval | PDF p1 | Out of scope; ASTFLOW generates nothing |

Conflict recorded: the Theme slide says *single language: JavaScript*; the screening dataset is Python (APPS). ASTFLOW
does JS repository intelligence and language-agnostic snippet retrieval; both are exercised below.

## Hackathon rubric evidence

| Criterion | Weight | Evidence now | Weakness | Action taken today |
|---|---:|---|---|---|
| Working prototype & functionality | 30% | Demo journeys pass (CI e2e green with the model); judge walkthrough below; dataset-length queries work; snippet CLI | Absolute AppsRetrieval accuracy is low | Fixed 422 on long queries; added `astflow snippets`; visible latency |
| Technical depth & feasibility | 25% | BM25+dense+RRF, tree-sitter AST, static call graph with TS corroboration, content-addressed Git snapshots, frozen 4-evaluator benchmark harness | Dense model is a general 22M sentence model | CommonJS resolver; E005 model screen with train-split protocol; Docker in CI |
| Innovation & originality | 20% | Evidence-carrying results (every edge has its call-site span); snapshot-exact sources; cross-version folding of identical snippets; honest match-basis labelling | Agent is a bounded rule policy, not learned | — (not manufactured) |
| Relevance to theme | 15% | Every headline feature answers "where is X / who calls X / what changed" with file:line | — | Removed nothing; demo script is retrieval-only |
| Presentation & documentation | 10% | README, demo script, experiment log incl. rejected ideas, this report | No PPT/video yet | Demo script + evidence pack |

## Retrieval (P0) — PASS · FROZEN

**Final configuration (frozen 2026-09-26):** `Alibaba-NLP/gte-modernbert-base`, Dense only, 512-token cap, no fusion,
no reranker. Official MTEB 2.21.0 AppsRetrieval, test split, all 3,765 queries × 8,765 documents, pinned revision
`f22508f9…`, run once at commit `036060e` (clean tree): `benchmark/results/mteb-final-gte/appsretrieval_results.json`.

| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | Status |
|---|---:|---:|---:|---:|---:|---|
| BM25 | 0.06312 | 0.05421 | 0.09216 | 0.16866 | 0.22603 | official (25 Sep) |
| Dense MiniLM | 0.06596 | 0.05581 | 0.09907 | 0.19389 | 0.25259 | frozen harness |
| Hybrid MiniLM (previous submission) | 0.08840 | 0.07257 | 0.13971 | 0.23400 | 0.29774 | official (25 Sep) |
| E004 long-query Hybrid | — | — | — | — | — | ACCEPT on train dev/confirmation (+0.018 / +0.014); **not officially evaluated** (not selected) |
| **GTE Dense (FINAL)** | **0.5511** | **0.5053** | **0.6967** | **0.8483** | **0.8943** | **official, today** |

Change vs 0.0884: **+0.4627 NDCG@10 (+523%)**, MRR@10 +0.4327. Selection was mechanical and pre-registered: GTE Dense
passed its full-corpus train-split gate (dev +0.229 [+0.185, +0.274], confirmation +0.218 [+0.172, +0.265]); E004 also
passed but is not selected when GTE passes. DEV performance was not assumed to predict the official score (large
train/test gap for the old system). Integrity: shard vectors re-encoded live before scoring (probe cos 0.99954 for
documents and queries). Caveat: gte-modernbert-base is an off-the-shelf retrieval model whose training data may overlap
CoIR-style data; the score is the official MTEB number for this configuration, not a claim about ASTFLOW's own training.

Experiment history and freeze record: `benchmark/EXPERIMENTS.md`, `benchmark/experiments/EXPERIMENTS.md` (RETRIEVAL FREEZE).

## P1 — retrieval across versions

Measured today on express 4.18.2 / 4.19.2 / 4.21.2 (npm releases committed as three tagged Git versions), lexical mode:

| Version | Index (cold) | Top result for "where is the redirect location URL encoded" |
|---|---:|---|
| v4.18.2 | 837 ms | `lib/response.js` `location` L906–916 (`var loc = url;`) |
| v4.19.2 | 844 ms | `location` L907–925 (`var loc;` — the 4.19 open-redirect fix) |
| v4.21.2 | 895 ms | `location` L914–926 |
| v4.18.2 again | 47 ms | cached snapshot reopened |

Correct version, file, line range and snippet per version; query 1–2 ms. Automated: `backend/tests/test_api_versions.py`
(added/removed/modified symbols and edges, indexed-bytes isolation). *Carried over* with the model: express cold index
38.6 s (embedding-bound), cached ≤ 1.9 s; unchanged chunks reuse vectors.

**With the frozen model** (`gte-modernbert-base`, CI run 36241962291 on a 4-vCPU runner; `benchmark/final_p1.py`,
report `benchmark/results/p1-final-gte/p1.json`) — **PASS**: every top-3 snippet lies within exactly the reported
lines of that version's file (`git show <tag>:<file>`).

| Version | Index | Embeddings reused / computed (156 chunks) | Query | Top result | Changed vs previous version |
|---|---:|---|---:|---|---|
| v4.18.2 | 292.9 s (cold) | 0 / 156 | 101 ms | `lib/response.js` `location` L906–916 | — |
| v4.19.2 | 148.6 s | 126 / 30 | 95 ms | `location` L907–925 | yes |
| v4.21.2 | 88.4 s | 138 / 18 | 95 ms | `location` L914–926 | yes |

Snippet corpora (new): each `-c` is a version; vectors are cached by content hash, so a new version embeds only
changed snippets (`test_new_version_embeds_only_changed_snippets`).

## Bonus — evolutionary retrieval

`astflow snippets -c v1=… -c v2=…` ranks every distinct snippet once and folds byte-identical copies into one result
listing all versions; changed variants are separate, labelled results (`test_identical_snippets_fold_across_versions…`).
Not done: ranking *near*-duplicates (e.g. preferring the latest variant). Status: partial.

## CPU feasibility

Everything runs on CPU (no GPU anywhere). Final model, measured on GitHub-hosted 4-vCPU runners:

| Item | Measured |
|---|---|
| Full corpus index (8,765 docs) | 242 runner-minutes (0.60 docs/s per runner; per-doc P50 1.26 s, P95 4.48 s) — built offline once, ≈ 15 min wall-clock across 20 runners; ≈ 4 h on one runner |
| Stored index | 8,765 × 768 float32 = 26.9 MB; reusable (content-hash keyed) |
| Query encoding, full problem statement (512 tokens) | P50 4.27 s, P95 4.49 s per query on a runner |
| Ranking after encoding (MTEB adapter, incl. BM25 bookkeeping) | P50 27.7 ms, P95 29.9 ms |
| Short repository question (P1, product path) | ≈ 96 ms end to end |
| Model weights | ≈ 0.6 GB (149M parameters, fp32); RAM not separately measured |

Unchanged snippets are never re-embedded (content-hash caches in both the repository index and `astflow snippets`).
Repository search with the product default (MiniLM Hybrid) stays at the carried-over P50/P95: demo 6/13 ms, express
43/50 ms, lodash 54/76 ms.

## Demo-critical functionality — judge walkthrough (no source reading)

| Task | Expected | What happened | Latency | Judge-readable? |
|---|---|---|---:|---|
| "How is the input preprocessed before going to the main function?" (brief's example) | `normalizeInput` first | `voice/normalizeInput.js:2` #1, then `VoiceHandler.handle` | 5 ms | Yes |
| "Where is the Bluetooth settings deeplink used?" | caller + deeplink | `BluetoothAgent.execute` #1 (the caller), `openBluetoothSettings` #3; lines open highlighted | 90 ms in UI | Yes |
| "Which files call normalizeInput before IntentRouter?" | sequence | both + `VoiceHandler.handle` in top 4, intent SEQUENCE | 5 ms | Yes |
| "Where is input validated?" | `validateCredentials` | **miss** in lexical mode (no stemming: validated ≠ validate); relies on the dense model | 4 ms | Weak without the model |
| express: "Which functions call compileETag before compileTrust?" | `app.set` | both targets + the caller `set` in top 3; no SEQUENCE evidence (resolver abstains on `switch`) | 47 ms | Yes, with honest abstention |
| Version switch v1 → v2 "Where is the session restored?" | AuthService → SessionManager | v1 `auth/AuthService.js`, v2 `session/SessionManager.js` | 4–5 ms | Yes |
| APPS-style 11.5k-char problem statement | accepted and ranked | **was HTTP 422** (2,000-char cap) → fixed | 35 ms | Yes after fix |
| Map on lodash (1,046 files) | readable overview | **was** 60 illegible alphabetical boxes, 16 edges → now 24 most-connected hub files with their edges | — | Yes after fix |

## Tests

| Suite | Result |
|---|---|
| Python (backend + benchmark), this container, no model | **103 passed, 2 skipped** (skips need the embedding model) |
| Python in CI with the model | green (runs 7–12) |
| Browser (Playwright) in CI with the model | **28/28** (run 12, after fixing a fragile edge click that failed runs 8–10) |
| Docker (CI: build, start, query) | **green** (run 12, after fixing the startup crash) |
| Browser here, no model | 26/28: the 2 failures assert semantic-only behaviour ("Closest matches by meaning"), which needs the model this container cannot download |
| Accessibility gate (axe, desktop + mobile) | pass (after today's focusable-code-block fix) |
| New tests today | `test_corpus.py` (4), `test_commonjs.py` (3), dataset-length query regression (1) |

## Engineering findings closed today

| Finding | Before | After |
|---|---|---|
| (new) Long queries rejected | HTTP 422 over 2,000 chars | 32,000 chars, 128 KB body cap |
| F-029 CommonJS edges | express 0 cross-file edges; lodash 0 | express 11 (11/11 checked), lodash 868 |
| F-031 anonymous labels | express 36 `anonymous@` symbols | 12 |
| F-030 large-repo overview | first 150 files alphabetically, illegible | most connected files, 24-hub compact layout |
| F-041 Docker unverified | never built | the first CI build **found a real defect**: the image crashed at start (non-editable install put `ROOT` in site-packages → `PermissionError` creating `.astflow/`). Fixed (editable install); the CI job builds, starts and queries the image |
| (new) flaky e2e edge click | `studio.spec.ts:24` clicked a bent edge's bounding-box centre (missed the path in CI runs 8–10) | clicks the path's midpoint; 3/3 locally |
| F-035 `/api/versions` | ~350 ms (*carried over*, Windows) | 13–39 ms on the demo here; not re-measured at scale |
| (new) scrollable code blocks not focusable | axe serious in Compare | fixed |

Still open: F-038 (tests crowding real-repo results; the 0.82 test weight stays), F-021 (frontend formatter pass),
F-018 (duplicate app instance) — none judge-visible in the demo path.

## External "hackathon judge" tools (Part 4)

Not run. Each of the four listed repositories is outside this session's repository scope, and tools of this kind work by
sending a repository to a hosted LLM, which would upload ASTFLOW and competition material to a third party without
permission. Classification: **SKIP (not evaluated; would require explicit permission to upload source)**. The rubric
matrix above plays the same role using the official weights.

## Submission artifacts

| Artifact | State |
|---|---|
| GitHub repo + README | ready (this branch; merge to `main` pending review) |
| MTEB AppsRetrieval JSON | **`benchmark/results/mteb-final-gte/appsretrieval_results.json`** (NDCG@10 0.5511, MRR@10 0.5053; MTEB 2.21.0, commit `036060e`, frozen configuration). The earlier `mteb-current-hybrid` (0.0884) is superseded. |
| GitHub Release with the JSON | **missing — needs owner authorisation** |
| Demo video ≤ 5 min | not recorded; script in `docs/DEMO-SCRIPT.md` |
| PPT | not produced; evidence pack in this report |
| Docker | image builds, starts and answers a query in CI (run 12) |

## Recommended final actions

Superseded by the product-integration pass (26 Sep, later the same day). The final state is in
[`submission/FINAL-DASHBOARD.md`](../submission/FINAL-DASHBOARD.md).

1. ~~Create the GitHub Release~~: done, [`v1.0-submission`](https://github.com/ANUJ-DESHPANDE/ASTFLOW/releases/tag/v1.0-submission)
   (asset SHA-256 equals the committed result file).
2. Organiser confirmation required: the slide's build window ended 25 Sep.
3. ~~Product default~~: the product now runs the frozen configuration by default (GTE dense on CPU, no silent
   fallback), verified at runtime on a clean clone (`audit/JUDGE-WALKTHROUGH.md`).
4. Record the demo following `submission/DEMO-SCRIPT.md` with `submission/DEMO-QUERIES.md`. That script supersedes
   `docs/DEMO-SCRIPT.md`.

# Hackathon rubric evidence

Weights are from the supplied judging slide. The official Samsung material (Theme 01 PDF and slides) is the source of
truth; requirement IDs R1–R11 refer to `audit/FINAL-SUBMISSION-READINESS.md`. This file collects evidence and gaps.
It does not score the project.

## Working prototype & functionality (30%)

| Evidence | Where |
|---|---|
| Clean install from the README only (`npm run setup`, `npm run demo`) on a fresh clone and 4-vCPU AMD runner: setup 101 s, demo ready 12 s later, 0 manual steps, `.venv` 1.6 GB | `audit/walkthrough/hardware.txt`, `setup.log`, `demo.log` (workflow `walkthrough.yml`, run 36257173755) |
| The running product reports the frozen configuration at runtime (`Alibaba-NLP/gte-modernbert-base · dense · CPU (frozen submission configuration)`) | `audit/walkthrough/demo.log`, `health.json` |
| Judge walkthrough: 13 tasks, **9 PASS / 3 PARTIAL / 1 FAIL**; every returned snippet matched the selected version's source; 0 console errors | `audit/JUDGE-WALKTHROUGH.md`, `audit/walkthrough/results.json` |
| The same journeys in a browser, with 11 screenshots (2/2 passed) | `audit/walkthrough/ui.spec.ts`, `audit/walkthrough/screens/` |
| Dataset-like queries: `astflow snippets` runs a full CoIR problem statement against the 8,765-document corpus. From an empty cache it downloads the official run's vectors (spot-checked live, min cos 0.9997); the relevant document ranked #1 for test query q5001; search 3.4 s | workflow `apps-vectors.yml` run 36246445235 |
| CI on every push: 110 Python tests (incl. real GTE semantic test), frontend build, dependency audits, 28 browser tests with an axe accessibility gate (desktop and phone), and a Docker build that answers a query | `.github/workflows/ci.yml` |

**Remaining weakness.**

- The first index of a new repository takes minutes on CPU: express, 3,226 chunks, 6.2–11.9 min depending on the CPU.
- Relevance: English words that equal symbol names get the exact-symbol boost (walkthrough T1 partial, T5 fail). Open finding J-1; not fixed because ranking is frozen.
- The Docker image is lexical-only, not the frozen configuration. It says so.
- The graph overview for large repositories is bounded (150 files, 60 nodes, 250 edges shown).

## Technical depth & feasibility (25%)

| Evidence | Where |
|---|---|
| Code-retrieval embedding model selected by a pre-registered, train-split protocol; official test scored once | `benchmark/EXPERIMENTS.md` |
| Official AppsRetrieval: NDCG@10 0.5511, MRR@10 0.5053 (3,765 × 8,765) | `benchmark/results/mteb-final-gte/`, release `v1.0-submission` |
| Dense retrieval on CPU with exact cosine ranking; no vector database, no network at query time | `backend/app/retrieval/search.py` |
| Tree-sitter AST, conservative static call graph (ESM, CommonJS, nested scopes), call-site spans on every edge, TypeScript corroboration, lexical call-order evidence | `backend/app/structure/`, `backend/app/parsing/javascript.py` |
| Version-aware, content-addressed snapshots; incremental embedding by content hash (express 4.19.2: 2,955 of 3,262 vectors reused, 46–79 s depending on CPU) | `backend/app/indexing/service.py`, workflows `index-timing.yml`, `walkthrough.yml` |
| CPU operation measured everywhere (4-vCPU runners): short query 266 ms, 1,880-char query 1.66 s, peak RSS 1.96 GB; float16→float32 diagnosis (6× on common CPUs) | `audit/JUDGE-WALKTHROUGH.md` (performance), workflow `index-diagnose.yml` |
| Rejected experiments kept with numbers (E001–E003); an accepted but unselected one (E004); an invalid run recorded as invalid | `benchmark/experiments/EXPERIMENTS.md` |
| Reproducibility: pinned MTEB, dataset revision and lock file; sharded reproduction workflows; live re-verification of precomputed vectors | `README.md` (Frozen submission configuration) |

**Remaining weakness.**

- A single run on one CPU machine reproduces the benchmark in hours; the sharded workflow does it in about 25 min.
- The structural analysis is static and conservative, so many member or dynamic calls stay unresolved (shown as such).

## Innovation & originality (20%)

Only differentiators that exist in the code:

- **Evidence-carrying answers.** Every result has an exact `file:line` span from an immutable snapshot, and every
  call-graph edge carries its call-site span. Call order is "lexical order only", and the UI says so.
- **Honest ranking labels.** A list with no shared word or symbol is labelled "closest matches by meaning" and flagged
  as possibly unrelated, not presented as the answer.
- **Version-aware retrieval with vector reuse.** Any Git revision is its own index. The cost of a new release is
  proportional to the code that changed, and results from different snapshots cannot be mixed.
- **Semantic plus structural investigation.** The dense first stage finds candidates. The observable agent step
  (plan → search → observe → refine → rank) adds one evidence-driven refinement and call-graph expansion for usage
  and path questions.
- **Evidence-backed experimentation.** Selection was pre-registered, rejected ideas were published, and the official
  test split was scored once.

Not claimed: a learned planner (the agent is a bounded rule policy), generation, or near-duplicate evolutionary
ranking (bonus: identical snippets are folded; near-duplicates are not grouped).

## Relevance to theme (15%)

| Theme 01 asks for | ASTFLOW |
|---|---|
| Plain-English query → relevant code snippets | Repository search (UI, API, CLI); `astflow snippets` for dataset-style corpora |
| File and line locations | Every result; the UI opens the exact lines from the indexed snapshot |
| Structural queries ("which files call X before Y") | Call graph plus lexical call-order evidence (T3 in the walkthrough) |
| Usage queries ("where is X used") | Caller expansion from the retrieved definition (T2) |
| Repository scale beyond an LLM context window | Local index of all callable chunks; express 3,226 chunks; bounded graph views |
| Code-aware retrieval, AST / call graph | Code-retrieval embedder, Tree-sitter AST, static resolver |
| Iterative retrieval / refinement | At most one evidence-driven refinement pass, shown in the Investigation log |
| P1: retrieval across versions | Per-revision snapshots; express 4.18.2 / 4.19.2 / 4.21.2 (T4) |
| CPU, minimal GPU | CPU only; CPU PyTorch wheels |
| Generation is not the target | ASTFLOW generates nothing; it returns source |

## Presentation & documentation (10%)

| Artifact | Status |
|---|---|
| README | Final pass done: what, why, install, model and size, start, index, query, versions, tests, benchmark reproduction, result, release, limitations |
| Architecture | README diagram and module map; `submission/TECHNICAL-STORY.md` |
| Benchmark evidence | Result JSON, run metadata, release asset (same SHA-256), experiment ledger |
| Release | `v1.0-submission` with the MTEB JSON (plus the published corpus vectors) |
| Demo | `submission/DEMO-SCRIPT.md` (≤ 5 min), `submission/DEMO-QUERIES.md` |
| PPT | Not produced (not requested); slide-by-slide evidence in `submission/PRESENTATION-EVIDENCE.md` |

**Remaining weakness.** There is no recorded demo video and no deck yet. Both are the team's to produce from the
script and evidence pack.

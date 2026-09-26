# Presentation evidence pack

One section per slide-worthy topic. Every claim names the file (and commit or run) it comes from. The deck itself
was not requested and is not produced here.

## 1. Problem statement

- Samsung Theme 01, Agentic Code Intelligence: a plain-English query returns relevant code snippets with file and
  line locations. It must handle structural and usage queries at repository scale, beyond an LLM context window, on
  CPU. P1 adds retrieval across versions; the bonus is evolutionary retrieval.
- Requirement map with sources: `audit/FINAL-SUBMISSION-READINESS.md` (R1–R11) and
  `audit/HACKATHON-RUBRIC-EVIDENCE.md`.

## 2. Architecture

- Diagram: README, "Architecture" (Mermaid).
- Pipeline: Git snapshot → Tree-sitter AST → callable chunks + static call graph (ESM, CommonJS, nested scopes; each
  edge carries its call-site span) → GTE embeddings (CPU, content-hash cache) → dense first stage → agent (plan,
  search, observe, one refinement, graph expansion, rank) → exact source from the snapshot.
- Code: `backend/app/indexing/service.py`, `backend/app/retrieval/search.py`, `backend/app/agent/investigate.py`,
  `backend/app/structure/resolver.py`.

## 3. Retrieval experiment journey

| Step | Result | Evidence |
|---|---|---|
| Baseline MiniLM Hybrid | NDCG@10 0.0884, R@100 0.2977 | `benchmark/results/mteb-current-hybrid/` |
| Diagnosis | 59% of misses absent from both top-100s; 76% of misses truncated | `benchmark/experiments/EXPERIMENTS.md` (failure analysis) |
| E001 fusion / E002 reranker / E003 windows | Rejected (flat or worse) | `benchmark/EXPERIMENTS.md` |
| E004 long query | Accepted, not selected (+0.018 dev) | same |
| E005 gte-modernbert-base | Selected (+0.229 dev, +0.218 confirmation) | `benchmark/EXPERIMENTS.md` (GTE gate) |
| Protocol | Tuned on train-split dev/confirmation; test scored once | same, "Protocol change on 2026-09-26" |

## 4. Final benchmark

> On the official MTEB AppsRetrieval evaluation over 3,765 queries and 8,765 documents, ASTFLOW's frozen GTE dense
> retriever achieved NDCG@10 0.5511 and MRR@10 0.5053.

- Result file: `benchmark/results/mteb-final-gte/appsretrieval_results.json`. Task `AppsRetrieval`, MTEB 2.21.0,
  revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`, `ndcg_at_10` 0.5511, `mrr_at_10` 0.505268.
- Metadata: `run_metadata.json`. `git_commit` 036060e1…, `git_dirty_files` [], `query_count` 3765, `corpus_count`
  8765, live probe min cos 0.99954 (docs) and 0.99955 (queries).
- Release: [`v1.0-submission`](https://github.com/ANUJ-DESHPANDE/ASTFLOW/releases/tag/v1.0-submission). The asset's
  SHA-256 (`dc9a984f…6fa6`) equals the committed file's.
- Diagnostic only: R@10 0.6967, R@50 0.8483, R@100 0.8943.
- Do not put the 16-query demo fixture numbers on this slide. They are a regression fixture measured with the old
  model.

## 5. Version retrieval (P1)

- Express 4.18.2 → 4.19.2 → 4.21.2, same question, three different `res.location` implementations. 4.19.2 is the
  open-redirect fix. Each snippet was checked against `git show <tag>:<file>`.
- Frozen model, benchmark harness: `benchmark/results/p1-final-gte/p1.json`. Vectors reused 0/156, then 126/156,
  then 138/156.
- Through the product (API and browser, real Git tags of the full repository, 3,226–3,270 chunks): #1 `location` on
  all three versions, snippets equal to `git show`, UI selector and source always on the same snapshot.
  `audit/JUDGE-WALKTHROUGH.md`, T4, and `audit/walkthrough/screens/02-express-*.png`.

## 6. CPU feasibility

- All measurements are on GitHub-hosted 4-vCPU runners. No GPU is used anywhere.
- Initial index vs incremental update vs query, express on 4 vCPUs: first index 6.2–11.9 min; next release 46–93 s
  (about 90% of vectors reused); query 266 ms short and 1.66 s for a 1,880-character statement; peak RSS 1.96 GB.
  Source: `audit/JUDGE-WALKTHROUGH.md` (performance).
- float32 vs float16 on CPU: 6× faster on CPUs without half-precision hardware, same speed elsewhere, vectors
  cos ≥ 0.9995 (`index-diagnose`).
- Corpus scale: 8,765 documents in 242 runner-minutes, sharded to about 15 minutes of wall-clock time. The published
  vectors let `astflow snippets` skip that cost.

## 7. Engineering quality

- CI on every push (`.github/workflows/ci.yml`): lint, Python tests, frontend build, dependency audits, 28 browser
  tests including an axe accessibility gate at desktop and phone sizes, and a Docker build that answers a query.
- Clean-clone walkthrough on a CPU runner (`.github/workflows/walkthrough.yml`), with evidence in
  `audit/walkthrough/`.
- Frozen, reproducible benchmark: pinned MTEB, dataset revision and lock file; sharded reproduction workflows.
- No silent fallback: the product refuses to run a configuration other than the one it reports
  (`backend/tests/test_frozen_product.py`).

## 8. Demo workflow

- `submission/DEMO-SCRIPT.md` (5:00) and `submission/DEMO-QUERIES.md`.

## 9. Limitations (say them)

- The first index of a repository is slow on CPU: a 149M-parameter encoder embeds every chunk. See the walkthrough
  timings. Incremental versions and queries are fast.
- Long queries (full problem statements) take about 4 s to encode on 4 vCPUs.
- The call graph is conservative and static. Member calls, dynamic dispatch and packages mostly stay unresolved and
  are shown as such.
- The agent is a bounded rule policy (at most two retrieval passes), not a learned planner.
- The benchmark measures text retrieval on Python snippets. The JavaScript graph and agent are demonstrated, not
  benchmarked.
- The Docker image is lexical-only (no model inside) and says so.
- Evolutionary retrieval (bonus) folds identical snippets across versions; near-duplicate ranking is not done.

## 10. Future work

- Speed up the first index on CPU: quantised or smaller code encoders, measured under the same frozen protocol.
- Wider static resolution (member calls through types) with TypeScript corroboration.
- Near-duplicate grouping across versions (bonus).
- A learned or LLM-assisted planner kept within the same evidence and honesty constraints.

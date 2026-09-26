# ASTFLOW — technical story

Every number here is from a committed file. Paths are given so each claim can be checked.

## Problem

Large codebases do not fit in a developer's head or in one LLM context window. Finding *where* a behaviour lives,
*who* uses it and *how it changed* between releases costs hours of grep and file-hopping. The Samsung Theme 01
challenge (Agentic Code Intelligence) asks for retrieval: a plain-English question returns the relevant code snippets
with file and line locations, on CPU. Generating text afterwards is not what is judged.

## Requirements (official PDF and slides)

| Requirement | ASTFLOW |
|---|---|
| Plain-English query → ranked code snippets (P0) | Repository search (UI, API, CLI) and snippet-corpus search (`astflow snippets`) |
| File and line locations | Every result carries `file:start–end` plus the exact snippet, served from the indexed snapshot |
| Structural questions ("which files call X before Y") | Tree-sitter AST, conservative static call graph, lexical call-order evidence |
| Usage questions ("where is X used") | Caller expansion over the call graph, starting from the retrieved definition |
| Retrieval across versions (P1) | Every Git revision is its own content-addressed index; unchanged chunks reuse their vectors |
| CPU, minimal GPU | Everything runs and is measured on 4-vCPU CPU machines; no GPU anywhere |
| Screening metric | Official MTEB AppsRetrieval (CoIR Apps test split), NDCG@10 and MRR@10, result JSON as a GitHub release asset |

## Initial architecture

BM25 (code-aware tokens) plus `all-MiniLM-L6-v2` dense vectors, fused with reciprocal-rank fusion (RRF, k=60).
Official AppsRetrieval result: **NDCG@10 0.0884, MRR@10 0.0726** (`benchmark/results/mteb-current-hybrid/`).

## Diagnosis

The candidates were missing, not badly ordered. Recall@100 was only **0.2977**: for about 70% of queries the right
solution never reached the top 100, so no reranking could help. A failure analysis of 127 misses
(`benchmark/experiments/EXPERIMENTS.md`) found:

- 59% absent from both retrievers' top 100;
- 76% of missed queries truncated at MiniLM's 254 word-pieces;
- a median 5% vocabulary overlap between a story-style problem statement and terse solution code.

## Experiments (pre-registered, tuned off the test split)

Protocol: tuning moved to dev and confirmation sets drawn from the train split, 300 queries each. The test split was
scored once, for the final candidate. Details: `benchmark/EXPERIMENTS.md`.

| ID | Idea | Result | Decision |
|---|---|---|---|
| E001 | Re-weight RRF fusion | +0.0003 dev, CI includes 0; official 0.08845 | Rejected |
| E002 | Cross-encoder reranker | −0.021 dev; official 0.06972 | Rejected (off-domain) |
| E003 | Sliding-window document vectors | Hybrid flat; official 0.08932 | Rejected |
| E004 | Encode the whole query (mean of 254-piece chunks) | +0.018 dev, +0.014 confirmation, both significant | Accepted, not selected |
| E005 | Code-retrieval embedder `gte-modernbert-base` (149M, Apache-2.0), 512 tokens, Dense | +0.229 dev, +0.218 confirmation (95% CIs exclude 0) | **Selected** |

Things that did not work are recorded with the same care as the winner, including an invalid run (CodeRankEmbed
failed under the pinned transformers version).

## Final result (official, run once)

MTEB 2.21.0 AppsRetrieval, test split, **3,765 queries × 8,765 documents**, dataset revision `f22508f9…`, evaluated
code at commit `036060e` with a clean tree:

| Metric | Before (MiniLM Hybrid) | Final (GTE Dense) |
|---|---:|---:|
| NDCG@10 | 0.0884 | **0.5511** |
| MRR@10 | 0.0726 | **0.5053** |
| Recall@10 | 0.1397 | 0.6967 |
| Recall@50 | 0.2340 | 0.8483 |
| Recall@100 | 0.2977 | 0.8943 |

Result file: `benchmark/results/mteb-final-gte/appsretrieval_results.json`, also attached to release
[`v1.0-submission`](https://github.com/ANUJ-DESHPANDE/ASTFLOW/releases/tag/v1.0-submission).

## Product

The product runs the same frozen configuration: GTE on CPU, with dense ranking as the first stage. This is checked at
runtime, not assumed: `/api/health`, the startup log and the UI's "How this works" panel name the model and ranking
mode. If the model is missing, indexing stops with an actionable error instead of quietly using keyword search.

On top of retrieval, ASTFLOW adds what a code question needs and a text benchmark cannot measure:

- **Source locations.** Exact `file:line` spans, served from the indexed snapshot, so an edited working tree never
  changes an answer's source.
- **Structure.** A Tree-sitter AST and a conservative static call graph (ES modules, CommonJS `require`, nested
  scopes). Every edge carries its call-site span and can be corroborated by the TypeScript language service.
- **Agentic investigation.** A bounded plan → search → observe → refine → rank loop: one extra retrieval pass driven
  by the symbols found or missing, plus call-graph expansion for usage and path questions. Every step is shown.
- **Versions.** Any tag or commit is indexed as its own snapshot. Unchanged chunks reuse their vectors by content hash,
  so a new release embeds only what changed (express 4.18.2 → 4.19.2: 126 of 156 vectors reused;
  `benchmark/results/p1-final-gte/p1.json`).
- **Honesty.** A result list with no shared word or symbol is labelled "closest matches by meaning" and flagged as
  possibly unrelated, not presented as the answer.

## Costs and trade-offs (measured, not hidden)

- **Initial index is the expensive step.** GTE is 149M parameters on CPU. The official 8,765-document corpus took 242
  runner-minutes: about 15 minutes of wall-clock time sharded over 20 runners, about 4 hours on one 4-vCPU machine.
  Repository timings from the clean-clone walkthrough are in `audit/JUDGE-WALKTHROUGH.md`.
- **Incremental updates are cheap.** Only changed chunks are embedded.
- **Long queries cost seconds.** A full problem statement (512 tokens) encodes in about 4.3 s on a 4-vCPU runner;
  a one-line question in well under a second. Ranking after encoding takes about 28 ms.

## Engineering discipline

- A reproducible benchmark (pinned MTEB, dataset revision and dependencies) and a pre-registered selection rule.
- A single official run, then a frozen configuration.
- CI runs lint, Python tests, the frontend build, dependency audits, browser journeys with an accessibility gate, and
  a Docker build that answers a real query.
- A clean-clone walkthrough on a CPU runner, and the official result published as a release artifact.

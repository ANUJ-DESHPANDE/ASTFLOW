# 02 · Retrieval baseline — provenance and reproduction

## Where the numbers come from

| Figure | Source | Code state | Queries | Status |
|---|---|---|---|---|
| **BM25 0.06312 / Dense 0.06596 / Hybrid 0.08840** (NDCG@10) | `benchmark/verification/manifest-baseline-v1.json` (`verify_retrieval.py`, 2026-09-23T20:21Z) | commit `7df804f8` **+ uncommitted edits** to `search.py`, `embeddings.py`, `mteb_appretrieval.py`, `precompute_embeddings.py`; `7df804f8` does not exist in this repository (never pushed). The ledger attributes BASE to `827e02d`. | all 3,765 test queries, 8,765 documents, dataset `f22508f9…` | authoritative (frozen runs + SHA-256), code provenance incomplete → **re-established by reproduction below** |
| BM25 0.06104 / Hybrid 0.08815 | `benchmark/results/mteb-bm25`, `mteb-hybrid` (MTEB 2.21.0) | older code (H1, H2 in the ledger) | 3,765 | historical |
| Hybrid 0.089 | `benchmark/results/mteb` | "real, uncommitted code" (H4) | 3,765 | historical |
| BM25 dev 0.06347 (k1 1.6, b 0.75) | `benchmark/results/bm25-tuning-log.json` (2026-09-21) | pre-stopword code, `git_commit: unknown` | 1,859 dev | historical tuning |
| Local fixture 0.82–0.93 | `benchmark/results/local.md` | 16 hand-written demo queries | 16 | **not** comparable; committed table was produced with the model unavailable (dense row empty, "hybrid" = lexical) |

The "5 scoring tools" claim in `ASTFLOW-HANDOFF.md`/`CURRENT_STATE.json` is not what the manifest records: 4 evaluators
agree (reference, astflow, pytrec_eval, ir_measures); NIST `trec_eval` was not available (`trec_eval_binary: null`).

## Reproduction in this audit (current code, this machine)

Command (fresh output directory; committed qrels untouched):

```
python -m benchmark.verify_retrieval --split all --modes bm25,dense,hybrid --tag repro-baseline --out <scratch>
```

Run at commit `b2ea145` (fixture restored; retrieval code identical to `f0f2fc9`), CPU embeddings, cached MiniLM vectors
with identity `cc3d1f5b729fa376dc5f9aed` (the same identity recorded in the baseline-v1 manifest).

| Mode | NDCG@10 | MRR@10 | R@10 | R@100 | vs frozen baseline-v1 | evaluators agree |
|---|---|---|---|---|---|---|
| BM25 | 0.06312 | 0.05421 | 0.09216 | 0.22603 | identical to 5 dp | yes |
| Dense | 0.06596 | 0.05581 | 0.09907 | 0.25259 | identical to 5 dp | yes |
| Hybrid | 0.08840 | 0.07257 | 0.13971 | 0.29774 | identical to 5 dp | yes |

Per-query comparison with the frozen rank files (`evidence/repro-vs-frozen.json`, `audit/tools/compare_to_frozen.py`):

| Mode | Identical rankings (depth 1000) | Identical top 100 | Queries with any metric change |
|---|---|---|---|
| BM25 | 3,765 / 3,765 | 3,765 | 0 |
| Dense | 2,069 / 3,765 | 3,728 | 0 |
| Hybrid | 3,063 / 3,765 | 3,751 | 0 |

Dense/hybrid differences are deep-rank floating-point ordering noise between CPUs (same model weights, same vector
cache identity); no query's NDCG@10/MRR@10/Recall@10/50/100 changes. Wall time 1,637 s (CPU, while other audit jobs
ran); median latency bm25 86.7 ms, dense 146.6 ms, hybrid 158.7 ms per query.

Note (F-024): this run's manifest records commit `52063cf` because `verify_retrieval` captured git state when it
*finished*; the run's code was loaded at `b2ea145` (retrieval code identical to `f0f2fc9`). Fixed to capture git state
at start.

**Conclusion:** the trusted baseline is reproducible from today's committed code, even though the exact source state
that produced it was never committed.

## Retrieval audit — where the limit is (from existing artifacts; details in the post-E003 audit)

| Measure (all 3,765 queries) | Value | Source |
|---|---|---|
| Hybrid Recall@100 (= Oracle@100, one relevant doc per query) | 0.2977 | baseline-v1 |
| Answer in neither BM25 nor Dense top 100 | 65.0% | frozen ranks |
| Answer in neither top 1000 | 24.0% | frozen ranks |
| Hybrid NDCG@10 vs perfect reordering of its own top 100 | 0.0884 vs 0.2977 | baseline-v1 |
| Queries > 256 word-pieces (Dense sees only the first 254) | 89.0% | E004 pre-registration measurement |
| Query vocabulary present in the relevant document (median share of query token types) | 5.8% (IDF-weighted 1.2%) | measured in this audit on the dataset |

**Recall vs ranking:** Recall@100 is weak (0.30) → **candidate generation is the primary limit**, as the mission's
rule says to prioritise. Ranking inside the pool also has headroom (0.088 of a 0.298 ceiling), but E002 showed a
web-trained cross-encoder makes it worse.

## Experiments already run under the frozen protocol

| ID | Result | Evidence |
|---|---|---|
| BM25 k1/b grid (26 configs, dev) | best = current k1 1.6 / b 0.75; **confirmation split was used 3 times** (protocol breach recorded here) | `bm25-tuning-log.json` |
| E001 RRF sweep (315 configs) | REJECT | `EXPERIMENTS.md` |
| E002 cross-encoder (d 20/50/100) | REJECT (−0.0187 NDCG@10, significant) | `experiments/E002.json` |
| E003 dense windows | REJECT (Dense +0.0047 significant; Hybrid +0.0009 not) | `experiments/E003.json` |
| E004 long-query dense | pre-registered, **awaiting approval** — not run in this audit | `EXPERIMENTS.md` |

## Mission items 19–21

- **BM25 tuning:** already done on dev with the existing `benchmark/tune_bm25.py`; the current parameters are the dev
  optimum of that grid. Re-running an identical grid adds no evidence, so it was not repeated.
- **Document expansion:** the vocabulary-mismatch hypothesis is strongly supported (median 5.8% query-term overlap;
  3,704 / 3,765 queries share < 10% of IDF-weighted vocabulary with their answer). But AppsRetrieval documents are
  competitive-programming solutions with no docstrings and short identifiers (median 16 distinct tokens after
  stopwords), so deterministic expansion (identifier splitting — already done by the tokenizer — docstrings,
  signatures) has nothing to expand. Only generated natural-language descriptions could bridge the gap. That needs a
  model and privacy/licensing decision and a pre-registered experiment → recorded as a candidate (E005), **not built**.
- **Real reranker:** a real cross-encoder was evaluated (E002) and rejected; it has now been removed from the product
  path (`aa14805`). The UI never exposed a "Reranked" mode.

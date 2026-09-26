# Retrieval experiment log (summary)

One row per experiment. The pre-registrations, full tables and verification detail live in
[`../EXPERIMENTS.md`](../EXPERIMENTS.md); per-experiment records are the `E00X.json` files next to this one.
Primary metrics are the official ones (NDCG@10, MRR@10). Recall is diagnostic.

Protocol change on 2026-09-26: tuning moves off the test split. `dev` and `confirmation` are drawn from the
CoIR Apps **train** qrels (5,000 problems; same 8,765-document corpus); the test split is scored once, by MTEB,
for a final candidate. The historical test-split `dev`/`confirmation` halves were used for E001–E003 and the
confirmation half was consulted at least three times during BM25 tuning — recorded as historical contamination.

| ID | Hypothesis | Failure mode addressed | Micro | Dev | Confirmation | Full / official | Runtime | Decision | Why |
|---|---|---|---|---|---|---|---|---|---|
| E001-fusion | Re-weighting RRF recovers candidates one retriever found | Fusion loses 209 top-100 answers | — | +0.00032 (CI incl. 0) | −0.00022 (CI incl. 0) | 0.08845 | minutes, offline | **REJECT** | Rank-sum parameters cannot separate semantic matches from keyword noise |
| E002-reranker | A cross-encoder reading query+code ranks better than RRF | Relevant item in top 100 but ranked low | — | −0.02070 | −0.01672 | 0.06972 | hours (GPU) | **REJECT** | Web-passage cross-encoder is off-domain for problem→solution |
| E003-dense-windows | Embedding every part of long documents | 23.5% of documents truncated at 256 pieces | — | Hybrid +0.00093 (CI incl. 0) | +0.00091 (CI incl. 0) | 0.08932 | ~3× embedding | **REJECT** | Dense improved; max-pooling favoured long documents, Hybrid flat |
| E004-long-query | Represent the whole query, not the first 254 pieces (`longquery-mean254`) | 89% of queries truncated; 76% of misses | — | Hybrid +0.0184 [+0.0038, +0.0331] (train dev, 300) | +0.0144 [+0.0020, +0.0276] (train, 300) | not run (not selected) | 7 min 12 s; query encode P50/P95 56/58 → 73/187 ms; no re-index | **ACCEPT**, not selected | Pre-registered rule met; GTE passed its gate, and the selection rule prefers GTE |
| E005-code-embedder | A code-retrieval embedder with a ≥1,024-token window | Truncation + NL↔code domain mismatch (measured below) | 100 q × 600 docs: gte-modernbert-base Dense 0.8865 vs MiniLM Hybrid 0.6145, Δ +0.272 [+0.199, +0.345]; granite Dense 0.6877 (Δ +0.073) | — | — | — | 45-min cap hit at 1,024 tokens; ≥ 20 min for 700 texts at 512 | E005 screen: **REJECT** (CPU, pre-registered) · CodeRankEmbed **INVALID** · run 1 **STOPPED-TIME-LIMIT**; then, on owner instruction, full-corpus gate **PASS** (dev +0.229, confirmation +0.218) → **SELECTED**; official NDCG@10 **0.5511**, MRR@10 **0.5053** | 149M ModernBERT encoders: best measured 2.4 docs/s at 512 tokens on 4 CPUs (< 5 docs/s threshold; ≈ 1 h to index the corpus) |

## E005 failure analysis (control model, train split, full corpus)

300 train-split queries × 8,765 documents, MiniLM hybrid exactly as in the product (CI job `failure-analysis`,
runs 36230017131 and 36232451630, identical numbers). Measured, not estimated:

| Mode | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.3789 | 0.3543 | 0.4567 | 0.5900 | 0.6300 |
| Dense (MiniLM) | 0.4349 | 0.4067 | 0.5233 | 0.6367 | 0.6833 |
| Hybrid | 0.4684 | 0.4339 | 0.5767 | 0.6733 | 0.7233 |

The same system scores 0.0884 on the test split. BM25, which has no training, shows the same gap (0.379 vs 0.063), so
the train split is intrinsically easier, not only possibly memorised by pretrained models. **Why is not established.**
A first guess — LeetCode-style starter code whose method names mirror the statement (`class Solution: def
subarrayBitwiseORs`) — is measured and does not explain it: those are 45 of 300 train queries (Hybrid 0.655); the other
255 stdin programs still score Hybrid 0.436, five times the test figure. Consequence: absolute train numbers do not
predict test numbers; E005 compares models *paired on the same train queries*, and only the official test run decides.

Measured failure distribution (run 36232451630, 127 of 300 queries with the answer outside the top 10):

| Failure category | Count | Share | Likely intervention |
|---|---:|---:|---|
| Answer absent from both retrievers' top 100 | 75 | 59.1% | better first-stage representation (E005) |
| In top 100, ranked 11–100 | 44 | 34.6% | better representation; a *code-trained* reranker only after recall improves |
| One retriever had it in top 100, lost by fusion | 8 | 6.3% | fusion (E001 showed no safe gain) |
| (overlapping) query truncated at MiniLM's 254 pieces | 97 | 76.4% of misses | long-context model (E005) or E004 |

Vocabulary: median 5.1% of a missed query's terms occur in its answer (p90 8.9%); median query 394 word-pieces, answer
149. Story-framed statements ("Zookeeper … carrots … rabbits") against terse stdin code
(`n,k=map(int,input().split())`) are the typical miss. First-stage representation, not ranking, dominates, which is why
E005 changes the representation and the reranker family stays deferred.

# RETRIEVAL FREEZE

Frozen 2026-09-26 after the single official run (workflow `official-final`, run 36239945962).

| Setting | Value |
|---|---|
| Model | `Alibaba-NLP/gte-modernbert-base` (149M, Apache-2.0) |
| Mode | Dense only (cosine on L2-normalised vectors) |
| Chunking | one vector per corpus document (AppsRetrieval); callable chunks in repositories |
| Query preprocessing | none; model-card prefixes (none for this model); truncation at 512 tokens |
| Fusion | none (the gate showed BM25 fusion lowers this model's score) |
| Candidate depth | full corpus scored exactly; top 1,000 returned to MTEB |
| Index configuration | 512-token cap for documents; vectors float32, content-hash keyed, 26.9 MB for 8,765 documents |

**Official AppsRetrieval (MTEB 2.21.0, test, 3,765 queries × 8,765 documents):** NDCG@10 **0.5511** · MRR@10 **0.5053**.
Diagnostics: R@10 0.6967 · R@50 0.8483 · R@100 0.8943. Result file: `benchmark/results/mteb-final-gte/appsretrieval_results.json`.

**CPU (4-vCPU GitHub runners):** full index 242 runner-minutes (≈ 15 min on 20 runners; ≈ 4 h on one); incremental
update and version behaviour in `benchmark/results/p1-final-gte/p1.json`; query encoding P50 4.27 s / P95 4.49 s for full
problem statements; ranking P50 27.7 ms / P95 29.9 ms.

**Frozen at commit:** `036060e` (the evaluated code); freeze recorded on the branch that carries this file.

No additional retrieval experiments should be performed before submission unless a correctness bug invalidates these results.

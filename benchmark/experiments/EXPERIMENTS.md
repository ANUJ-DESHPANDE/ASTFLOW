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
| E004-long-query | Represent the whole query, not the first 254 pieces | 89% of queries truncated | — | — | — | — | — | **CANCELLED** (owner) | Not run |
| E005-code-embedder | A code-retrieval embedder with a ≥1,024-token window | Truncation + NL↔code domain mismatch of MiniLM (measured, see below) | see ledger | — | — | — | per model: see ledger | see ledger | — |

## E005 failure analysis (control model, train split, full corpus)

300 train-split queries × 8,765 documents, MiniLM hybrid exactly as in the product (CI job `failure-analysis`,
run 36230017131). Measured, not estimated:

| Mode | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.3789 | 0.3543 | 0.4567 | 0.5900 | 0.6300 |
| Dense (MiniLM) | 0.4349 | 0.4067 | 0.5233 | 0.6367 | 0.6833 |
| Hybrid | 0.4684 | 0.4339 | 0.5767 | 0.6733 | 0.7233 |

The same system scores 0.0884 on the test split. BM25, which has no training, shows the same gap (0.379 vs 0.063), so
the train split is intrinsically easier, not only possibly memorised by pretrained models. The failure dump shows why:
many train problems are LeetCode-style with starter code whose method name mirrors the statement
(`class Solution: def subarrayBitwiseORs`), while 13 of the 14 printed misses are stdin programs with terse identifiers
(`n,k=map(int,input().split())`) solving story-framed statements ("Zookeeper … carrots … rabbits"), where
neither word overlap nor a general sentence model connects narrative to algorithm. Consequence: absolute train
numbers do not predict test numbers, E005 results are also reported per stratum (`starter` vs `stdin`), and the
official test run decides.

Of the 14 misses printed in full, 8 had the answer outside both retrievers' top 100, 4 ranked it 11–100 and 2 lost it in
fusion — first-stage representation, not ranking, dominates, which is why E005 changes the representation and why the
reranker (E002 family) stays deferred.

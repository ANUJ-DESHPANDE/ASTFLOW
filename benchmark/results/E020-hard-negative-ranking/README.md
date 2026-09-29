# E020 hard-negative ranking — REJECT (2026-09-29)

Starting commit `d746b9a`; branch `exp/E020-hard-negative-ranking`.
The frozen 300-query TRAIN DEV IDs are identical to E018/E019. The accepted
production retrieval remains GTE ModernBERT dense cosine, with no reranker.
Frozen full TEST reference remains NDCG@10 0.5509, MRR@10 0.5050; TEST was
not read or scored during E020.

## Query-length gate

The local ModernBERT tokenizer counted 13/55 recoverable failures and 54/242
top-10 successes above 512 tokens. Their rates were 23.64% and 22.31%, an
enrichment of 1.059x. Condition A (at least 11 failures) passed; condition B
(at least 2x enrichment) failed. Query cleanup was rejected before implementation.
The gate artifact includes character counts, whitespace tokens, model tokens,
rank, and bucket for every DEV query.

## Hard-negative experiment

E018 found 32 answers at ranks 11–50. `hard_negative_pairs.jsonl` contains
all 809 pairs between each of these positives and every higher-ranked dense
false positive, including their dense/BM25 scores and ranks. The existing
E017 TRAIN-only top-20 mining supplied negatives for 300 disjoint TRAIN
queries. A fixed pairwise logistic model learned seven feature coefficients
from 3,000 TRAIN pairs. Its exact model JSON, feature order, IDF table, query
selection hash, pair selection hash, seed, and library are recorded. DEV labels
were never used to fit weights. The preregistration in commit `ec1925d`
pinned the algorithm and model hash before DEV scoring.

| DEV metric | Dense | E020 | Delta |
|---|---:|---:|---:|
| NDCG@10 | 0.696715 | 0.654902 | -0.041813 |
| MRR@10 | 0.662038 | 0.611914 | -0.050124 |
| Recall@10 | 0.806667 | 0.790000 | -0.016667 |
| Recall@20 | 0.853333 | 0.846667 | -0.006667 |
| Recall@50 | 0.913333 | 0.913333 | 0 |
| Recall@100 | 0.933333 | 0.933333 | 0 |
| Recall@500 | 0.976667 | 0.976667 | 0 |
| Recall@1000 | 0.990000 | 0.990000 | 0 |

Paired NDCG@10 95% interval: [-0.069786, -0.013075]; MRR@10 interval:
[-0.082930, -0.016528]. Across all queries, ranks improved for 48,
were unchanged for 179, and worsened for 73. Among the 32 original rank-11–50
failures, 10 moved into top 10, 11 improved but stayed outside, one was
unchanged, and 10 worsened. E019's rejected NDCG@10 was 0.699036 on the
same reconstructed baseline; E020 does not use its operator boost.

On E019's fixed 50-query sample, query p50 was 324.38 ms dense versus
363.27 ms E020 (+38.89 ms); p95 was 645.58 versus 700.04 ms (+54.46 ms).
These are same-run paired timings; E019's earlier wall timings are separate.

**Decision: REJECT.** The delta misses +0.005 and its interval is wholly
negative. MRR also materially regresses. No confirmation or TEST evaluation
was run, and production code is unchanged. The extra evidence recovered some
target queries but disrupted many initially correct rankings. The next
hypothesis is that evidence should affect only dense near-ties, with the
tie rule selected using TRAIN data before frozen DEV evaluation.

Focused tests: 4 pass. The available broader benchmark subset: 20 pass.
Full benchmark collection is blocked by the pre-existing missing `mteb`
package; after excluding that test, 11 failures and five setup errors all
trace to the pre-existing missing `pytrec_eval` package.

# E019 operator evidence — REJECT (2026-09-29)

Starting commit: `20c8c3a` (E018). Branch: `exp/E019-operator-evidence`.
The hypothesis, fixed depth 50, boost 0.02, feature list, and decision rule
were committed in `5da664f` before the DEV result was scored.

The run re-encoded the established 300 DEV and 300 confirmation TRAIN queries
once on CPU in 310.1 seconds, reusing the published 8,765-document GTE vector
asset. Only DEV was scored; confirmation and TEST were not evaluated because
DEV failed the pre-registered gate. The fresh float32 DEV baseline is
NDCG@10 0.696715 versus the historical frozen campaign's 0.697734; Recall@10
and Recall@1000 match exactly. The paired E019 comparison uses the same fresh
vectors on both sides.

| DEV metric | Dense baseline | E019 | Delta |
|---|---:|---:|---:|
| NDCG@10 | 0.696715 | 0.699036 | +0.002321 |
| MRR@10 | 0.662038 | 0.663933 | +0.001894 |
| Recall@10 | 0.806667 | 0.810000 | +0.003333 |
| Recall@20 | 0.853333 | 0.850000 | -0.003333 |
| Recall@100 | 0.933333 | 0.933333 | 0 |
| Recall@1000 | 0.990000 | 0.990000 | 0 |

Paired NDCG@10 95% bootstrap interval: [0, +0.005615]. Five queries gained
NDCG, one lost; four additional rank changes did not move NDCG@10. Dense
score p50 was 2.30 ms and the operator rerank added 0.48 ms p50, 3.11 ms p95.
No new index or model weights are needed. Query encoding is unchanged; the
existing 8-thread measurement is about 230 ms p50.

**Decision: REJECT.** The DEV gain is below +0.005 and its interval includes
zero. The experimental function remains available for reproduction but is
not called by the production Retriever. There was no confirmation or TEST run.

Reproduce with `python -m benchmark.e019_operator_rerank encode`, then
`python -m benchmark.e019_operator_rerank evaluate --set dev` in the project
environment. The published document vectors must be at the path recorded by
the evaluator's `--vectors` option. The vector cache is ignored by Git.

# E021 confidence-gated near-tie reranking — REJECT BEFORE DEV

Starting commit: `2ee9eb1`; branch: `exp/E021-confidence-gated-rerank`.
Accepted production remains the GTE ModernBERT dense retriever. Frozen TEST
reference remains NDCG@10 0.5509 and MRR@10 0.5050. Neither DEV nor TEST was
scored during E021.

The E020 secondary model and IDF artifact were hash-verified and reused
unchanged. E020 used the first 300 E017-ordered TRAIN IDs for fitting. E021
used the next 200 TRAIN IDs to choose a gate and the following 200 as an
independent validation set. All three sets are disjoint. The only candidates
were three inference-time dense score gaps (rank 1–2, rank 1–10, rank 10–11)
at five TRAIN-A quantiles (10, 20, 30, 40, 50). Top-50 rerank depth remained
fixed. A non-triggered query receives the exact stable dense order.

Across the 400 held-out TRAIN queries, broad E020-style reranking improved
62 ranks, worsened 104, and left 234 unchanged. The rank-1-to-10 margin
median was 0.052548 for helped queries, 0.065317 for harmed queries, and
0.111720 for unchanged queries. The rank-1-to-2 medians were 0.010069,
0.020333, and 0.059232. Helped and harmed queries overlap substantially;
rank-10-to-11 medians showed almost no useful separation.

TRAIN-A selected the rank-1-to-10 margin gate with threshold 0.0528913856
by the recorded highest-NDCG rule among candidates meeting both 50/50
requirements. It triggered for 60/200 queries, avoided 37/57 (64.91%)
harmful interventions, and retained 17/29 (58.62%) useful improvements.
TRAIN-A NDCG@10 was 0.674205 dense, 0.617614 broad, and 0.669097 gated.

The frozen gate triggered for 55/200 TRAIN-B queries. It avoided 30/47
(63.83%) harmful interventions but retained only 15/33 (45.45%) useful
improvements. TRAIN-B NDCG@10 was 0.679120 dense, 0.638407 broad, and
0.668470 gated. The held-out recovery requirement failed, and even the gated
quality point estimate remained below dense. No alternative gate was selected
after observing TRAIN-B.

**Decision: REJECT BEFORE DEV.** The independent TRAIN-B result missed the
prewritten requirement to retain at least half of E020's useful improvements.
No frozen DEV evaluation, confirmation, latency sample, or TEST run was
performed. Production remains unchanged. The next hypothesis is that a
stronger query-code pairwise relevance model trained on a broader set of
genuine TRAIN hard negatives can distinguish candidates more reliably than
E020's cheap lexical and structural features.

Focused gating and E020 compatibility tests: seven pass. Available broader
benchmark subset: 23 pass. The pre-existing full-suite collection is blocked
by missing `mteb`; `pytrec_eval` is also missing for related benchmark tests.

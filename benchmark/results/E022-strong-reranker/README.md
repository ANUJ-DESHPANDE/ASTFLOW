# E022 strong joint reranker — REJECT BEFORE DEV

Starting commit `c64cd10`; branch `exp/E022-strong-reranker`.
The accepted GTE ModernBERT dense production system remains unchanged. Frozen
TEST NDCG@10 0.5509 and MRR@10 0.5050 remain references only. E022 did not
score TEST, confirmation, or frozen DEV.

The one selected model was the locally cached pretrained
`Alibaba-NLP/gte-reranker-modernbert-base` at revision
`f7481e6055501a30fb19d090657df9ec1f79ab2c`. It is a 149,605,633-
parameter cross-encoder that jointly scores query/document pairs. Its
float32 weights and tokenizer hashes are in `feasibility.json`. It loaded
offline on CPU, scored batches of 50 finite pairs, and used 2.36 GB peak
process memory with batch size 8 and eight CPU threads. The model is suitable
for the E022 question, but the measured serving cost is not suitable for
ASTFLOW's CPU retrieval path.

| Fixed five-query TRAIN sample | p50 | p95 |
|---|---:|---:|
| Dense query encoding + scoring | 0.546 s | 0.672 s |
| Cross-encoder top-50 only | 29.564 s | 30.672 s |
| Dense plus cross-encoder | 30.149 s | 31.248 s |

This is about 55 times the paired dense p50. The sample is small, so it is
a feasibility measurement rather than a production latency estimate. The
multiple-second feasibility concern in the E022 plan is exceeded by a wide
margin. The model was not swapped or tuned after this measurement.

The project already had 4,400 TRAIN-only GTE top-20 candidate lists from
E017. E022 prepared 1,322 positive-versus-higher-ranked-negative pairs from
1,000 designated TRAIN-A queries; 431 of those queries had such negatives.
Two hundred disjoint TRAIN-B queries were reserved. The prepared pairs were
not used for E022 training because CPU feasibility failed. Consequently no
TRAIN-B NDCG, MRR, recall, or target-bucket result exists. No zero-shot
quality claim is inferred from the five-query timing sample. Earlier E011
zero-shot and E017 300-query fine-tuned evaluations of this architecture
both scored below dense on DEV, but E022 did not rerun those experiments.

**Decision: REJECT BEFORE DEV.** This cached joint model can run but has no
credible CPU top-50 serving path at the measured 30-second latency. E022 did
not establish that a stronger joint model solves the ranking bottleneck; it
established that this available model does not justify further campaign
investment under the CPU constraint and existing negative E011/E017 quality
evidence. E023's sole objective is the final campaign decision around the
validated GTE dense system.

Focused E022 tests: three passed. The available broader benchmark subset:
26 passed. The pre-existing full-suite collection requires missing `mteb`;
related evaluation tests also require missing `pytrec_eval`.

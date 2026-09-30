# Retrieval campaign ledger — CLOSED at E023 (2026-09-29)

The [accepted production baseline](../../RETRIEVAL_BASELINE.md) is the
float32 GTE-ModernBERT dense system. Its full TEST result is NDCG@10 0.5509,
MRR@10 0.5050. The older 0.5511 official run and the MiniLM records below are
historical. No TEST benchmark was run during E023.

## Baseline, performance, and closure

| ID | Hypothesis / dataset | Result and decision | Commit | Artifact |
|---|---|---|---|---|
| VAL | Clean float32 GTE dense baseline; 3,765 TEST queries, 8,765 documents | **ACCEPT**: NDCG@10 0.5509, MRR@10 0.5050, Recall@100 0.8946; exact top 1,000. This is the accepted quality reference. | `db57806` (float32 product path) | [`final-validation-20260928`](../final-validation-20260928/README.md) |
| CPU8 | Raise CPU cap from four to eight physical-core-aware threads; full TEST equivalence plus controlled 150-query A/B | **ACCEPT**: all 3,765 top-10 lists identical; full indexing 6,474 to 3,968 s; controlled query-encoding p50 343 to 230 ms, faster on 149/150. The TEST equivalence run preceded E023. | `1325390` | [`threads8-equivalence-20260929`](../threads8-equivalence-20260929/README.md) |
| E023 | Freeze accepted production configuration, verify application wiring and preserve E018–E022 decisions; existing evidence and cheap repository tests only | **CLOSED**: GTE dense remains the default; rejected rerankers and BM25 fusion off; no new TEST run. Further product work: reliable incremental indexing. | `dc974ca` (production freeze), `3b487cf` (canonical state) | [`E023 closure`](../E023-retrieval-closure/README.md), [`RETRIEVAL_BASELINE.md`](../../RETRIEVAL_BASELINE.md) |

## 2026-09-29 continuation

| ID | Starting commit / branch | Hypothesis and change | DEV result | Decision | Evidence |
|---|---|---|---|---|---|
| E018 | `fec272f` / `exp/E018-ranking-diagnosis` | Saved candidate/qrels diagnosis: 55/300 correct at dense ranks 11–1000, only 3 absent; BM25 has 4 unique top-10 recoveries and zero unique top-1000 recoveries | Baseline NDCG@10 0.697734, MRR@10 0.663316 | DIAGNOSIS → E019 operator evidence | [`E018 artifacts`](../E018-ranking-diagnosis/README.md); commit `20c8c3a` |
| E019 | `20c8c3a` / `exp/E019-operator-evidence` | Fixed top-50 explicit operator boost +0.02, production off by default; preregistered in `5da664f` | Fresh float32 paired baseline 0.696715 → 0.699036, Δ +0.002321, 95% CI [0, +0.005615]; 310.1 s to encode 600 TRAIN queries; fixed-sample query p50 360.56 → 361.73 ms, p95 738.56 → 740.99 ms; extra index time 0, weights 0 | **REJECT**: below +0.005 gate; no confirmation or TEST | [`E019 artifacts`](../E019-operator-evidence/README.md) |
| E020 | `d746b9a` / `exp/E020-hard-negative-ranking` | Query cleanup gate failed enrichment (13/55 versus 54/242, 1.059x). Fixed train-only pairwise logistic reranker on dense top 50; 3,000 TRAIN pairs, 809 diagnostic DEV hard-negative pairs; preregistered in `ec1925d` | NDCG@10 0.696715 → 0.654902, Δ -0.041813, 95% CI [-0.069786, -0.013075]; MRR@10 0.662038 → 0.611914; 10/32 target failures enter top 10; query p50 324.38 → 363.27 ms | **REJECT**: quality and MRR regress; no confirmation or TEST | [`E020 artifacts`](../E020-hard-negative-ranking/README.md) |
| E021 | `2ee9eb1` / `exp/E021-confidence-gated-rerank` | E020 model behind a rank-1-to-10 dense-margin gate selected on 200 TRAIN-A queries; threshold 0.0528913856; independent 200-query TRAIN-B check | TRAIN-A avoided 37/57 harmful interventions and retained 17/29 useful improvements; TRAIN-B avoided 30/47 but retained only 15/33 (45.45%). TRAIN-B gated NDCG@10 0.668470 vs dense 0.679120. DEV not consumed. | **REJECT BEFORE DEV**: TRAIN-B recovery-retention gate failed; no confirmation or TEST | [`E021 artifacts`](../E021-confidence-gated-rerank/README.md) |
| E022 | `c64cd10` / `exp/E022-strong-reranker` | One cached joint relevance model (`Alibaba-NLP/gte-reranker-modernbert-base`, pinned revision); 1,322 genuine TRAIN hard-negative pairs prepared, not trained | CPU top-50 rerank p50 29.56 s, p95 30.67 s; end-to-end p50 30.15 s versus dense 0.55 s; 2.36 GB peak process RSS. TRAIN-B quality not scored because feasibility failed. DEV not consumed. | **REJECT BEFORE DEV**: operationally infeasible on the accepted CPU path; no confirmation or TEST | [`E022 artifacts`](../E022-strong-reranker/README.md) |

E018 used the established 300-query TRAIN DEV IDs (SHA-256
`5c61ce5eb1551e3897876ba5c34194bac0a54ed0f1a47149a349c9a3d0b78d53`),
the GTE model revision `e7f32e3c`, and the published document vectors.
The E018–E022 artifact directories contain full parameter, metric,
run-path, and SHA-256 records. E020 retired the long-query hypothesis, E021
rejected dense-margin gating on held-out TRAIN, and E022 found the cached joint
reranker operationally infeasible on CPU. E023 closed the campaign around the
validated GTE dense system. There is no active retrieval experiment.

## Historical E004–E016 campaign summary

The table below was generated from `benchmark/results/campaign/*.json` (no hand transcription). DEV/CONFIRMATION: frozen train-split sets (300 + 300, seed 20260926), full 8,765-document corpus, cached GTE vectors of the official run. Its TEST table records an earlier native-precision baseline and E004 confirmation, not the accepted clean float32 baseline.

| ID | Hypothesis | dev NDCG@10 | dev MRR@10 | dev R@100 | dev R@500 | dev Δ [95% CI] | conf Δ [95% CI] | Decision |
|---|---|---:|---:|---:|---:|---|---|---|
| BASE | GTE dense, frozen (official test 0.5511) | 0.6977 | 0.6633 | 0.9333 | 0.9767 | — | — | baseline |
| DIAG | BM25 alone, code-aware tokens (product) | 0.3789 | 0.3543 | 0.6300 | 0.7667 | -0.3188 [-0.3674, -0.2695] | -0.2896 [-0.3383, -0.2448] | diagnostic |
| DIAG | Hybrid, equal RRF k=60 | 0.6130 | 0.5667 | 0.9333 | 0.9833 | -0.0848 [-0.1176, -0.0526] | -0.0795 [-0.1148, -0.0463] | diagnostic: hurts |
| E004 | dense + 0.05 BM25, generic tokens (dev-selected fusion) | 0.7146 | 0.6844 | 0.9367 | 0.9767 | +0.0169 [+0.0045, +0.0302] | +0.0161 [+0.0045, +0.0291] | KEEP on dev/conf → REJECT on TEST |
| E009 | weighted RRF, best dev `e009_rrf_wd0.9_k30` | 0.7100 | 0.6786 | 0.9367 | 0.9767 | +0.0123 [+0.0014, +0.0232] | +0.0122 [+0.0011, +0.0239] | below E004 blend |
| E009 | linear fusion, code tokens, best dev `e009_lin_l0.05` | 0.7109 | 0.6814 | 0.9367 | 0.9767 | +0.0132 [-0.0002, +0.0274] | +0.0271 [+0.0134, +0.0417] | dev CI includes 0 |
| E011 | gte-reranker-modernbert-base, dense top-20, reranker 512 tok, pure | 0.6463 | 0.6117 | — | — | -0.0514 [-0.0882, -0.0133] | -0.0391 [-0.0735, -0.0060] | REJECT |
| E011b | gte-reranker-modernbert-base, dense top-20, reranker 1024 tok, pure | 0.6407 | 0.6067 | — | — | -0.0570 [-0.0947, -0.0196] | -0.0315 [-0.0642, +0.0020] | REJECT |
| E016 | query window 2048 tokens (docs 512), dense | 0.7020 | 0.6679 | 0.9333 | — | +0.0053 [-0.0040, +0.0156] vs q512 | +0.0129 [+0.0022, +0.0254] | REJECT (dev CI includes 0) |
| E005 | BM25 k1/b grid inside the blend, best dev `e005_k12.0_b0.9_l0.05` | 0.7149 | 0.6847 | 0.9367 | 0.9767 | +0.0002 [-0.0005, +0.0013] vs blend | +0.0043 [+0.0006, +0.0089] | REJECT |
| E015 | dense pseudo-relevance feedback, best dev `e015_prf_k10_b0.1` | 0.7106 | 0.6790 | 0.9367 | 0.9767 | -0.0040 [-0.0100, +0.0018] vs blend | -0.0036 [-0.0106, +0.0028] | REJECT |

## TEST (run once)

| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | R@500 |
|---|---:|---:|---:|---:|---:|---:|
| baseline GTE dense | 0.5511 | 0.5053 | 0.6967 | 0.8483 | 0.8943 | 0.9612 |
| E004 blend | 0.5517 | 0.5055 | 0.6988 | 0.8467 | 0.8932 | 0.9610 |

ΔNDCG@10 +0.0006 [-0.0020, +0.0032], wins/losses 199/279 → does not generalise; REJECT.

Metric check: harness reproduces the official MTEB test result exactly (0.5511 / 0.5053 / 0.8943); pytrec_eval agrees on dev (0.697734 = 0.697734).
Oracle (dense candidates, perfect rerank), dev: depth 20 0.853, depth 100 0.933 vs actual 0.698.

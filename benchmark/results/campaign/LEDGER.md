# Retrieval campaign ledger (2026-09-27)

Generated from `benchmark/results/campaign/*.json` (no hand transcription). DEV/CONFIRMATION: frozen train-split sets (300 + 300, seed 20260926), full 8,765-document corpus, cached GTE vectors of the official run. TEST: 3,765 queries, used only for the baseline reproduction and one confirmation.

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

# TEST confirmation (run once): 3765 queries x 8765 documents

| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | R@500 | R@1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline: GTE dense (official) | 0.5511 | 0.5053 | 0.6967 | 0.8483 | 0.8943 | 0.9612 | 0.9782 |
| kept: GTE dense + 0.05 * max-normalised BM25 (generic tokens, k1 1.6, b 0.75) | 0.5517 | 0.5055 | 0.6988 | 0.8467 | 0.8932 | 0.9610 | 0.9785 |

ΔNDCG@10 +0.0006 [-0.0020, +0.0032] · wins/losses 199/279

# E017 task-specific reranker — REJECT (2026-09-27)

The [pre-flight](E017-PREFLIGHT.md) passed on a 4 GB GTX 1650 Ti. This was one bounded 1:4 hard-negative training run, selected before examining DEV. Production retrieval and the release were not changed.

## Decision gate

| DEV, 300 frozen queries, dense top-20 | NDCG@10 | MRR@10 | R@10 |
|---|---:|---:|---:|
| GTE dense baseline | 0.6977 | 0.6633 | 0.8067 |
| Zero-shot reranker, 512 tokens ([E011](e011.md)) | 0.6463 | 0.6117 | 0.7567 |
| E017 fine-tuned reranker, 512 tokens | 0.6676 | 0.6345 | 0.7733 |

E017 minus dense is **−0.0302 NDCG@10**, with paired 95% bootstrap CI **[−0.0673, +0.0075]** (44 wins, 59 losses). Its NDCG is +0.0213 above the historical zero-shot E011 number, but E011 used CPU float32 whereas E017 used GPU fp16, so that difference is descriptive rather than a precision-matched training effect. E017 does not beat frozen dense. The pre-registered gate requires DEV ΔNDCG@10 ≥ +0.005 with CI above zero. **E017 is rejected.** CONFIRMATION and TEST were not scored, no TEST labels or metrics were used, and there was no product integration. The full machine-readable metrics are in [`e017/dev.json`](e017/dev.json).

## Run and provenance

- Eligible TRAIN pool: 4,400 queries after excluding the frozen 300 DEV and 300 CONFIRMATION IDs (seed 20260926). All 4,400 TRAIN queries were encoded once with `Alibaba-NLP/gte-modernbert-base`, max sequence 512, in four separate 1,100-query jobs. Each job took 349–351 seconds and used at most 0.39 GiB allocated VRAM. The corpus was never re-embedded.
- Document vectors: release `apps-corpus-vectors-gte-modernbert-base.npz`, SHA-256 `0debd8748b176b281fa27602f1a3e990d22598d7e09e719f7d5a5a346318bb71`; all 8,765 corpus IDs mapped to its 8,754 distinct text hashes. DEV candidates: saved `campaign-candidates` artifact from run 36318134381, ZIP SHA-256 `faf0c8d3c8fdd54bd6c66673f567dce19597aedaa08ff503594c1d669f0be3fa`. Its dense DEV baseline reproduced 0.69773365 NDCG@10 exactly.
- Training: first 300 randomly shuffled eligible TRAIN IDs, one positive plus the first four distinct-text nonrelevant GTE top-20 documents per query, 1,500 pairs total. `Alibaba-NLP/gte-reranker-modernbert-base`; built-in RankNet loss, Adafactor at 1e-5, max length 512, fp16 autocast, mini-batch 2, gradient checkpointing. One pass of 300 optimizer steps took 1,606.7 seconds (26.8 minutes), peak 1.463 GiB allocated VRAM. A halfway checkpoint was saved. Details: [`e017/train.json`](e017/train.json).
- DEV scoring: the same frozen 20 candidates per query, pure reranker order, batch 2, fp16. All 6,000 pairs took about 26.2 minutes across the saved first block and one resumed job; peak allocated VRAM 0.61 GiB. A batch-8 pilot on 20 queries did not improve speed and changed some near-tied fp16 orderings, so the final 300-query score file used batch 2 throughout. Scores and model checkpoints remain under ignored `.astflow/e017/` locally. The final `model.safetensors` SHA-256 is `b22b3713c80f85cf1af6a7cc084a7d640e79149ab96f77a0ce54387e9a7a5845`.

## Focused error inspection

The 20 largest gains typically promoted a relevant document from dense ranks 3–19 to rank 1–3. The 20 largest regressions mostly demoted a dense rank-1 relevant document to rank 4–20. Their queries averaged 323 versus 522 reranker tokens, respectively; 3/20 gain queries versus 7/20 regression queries exceeded 512 query tokens before adding any code. This suggests length sensitivity, although this comparison does not establish its cause. E011 at 1024 tokens also lost to dense, so sequence length alone is not a proven fix.

Top 20 gains (dense→E017 rank): `q3276` 13→1, `q3895` 19→1, `q4142` 17→1, `q3898` 10→1, `q608` 10→1, `q4662` 9→1, `q2552` 7→1, `q2993` 7→1, `q3857` 7→1, `q4002` 6→1, `q2811` 12→2, `q3029` 14→2, `q3019` 4→1, `q3184` 4→1, `q4553` 4→1, `q1022` 19→3, `q12` 3→1, `q135` 3→1, `q334` 3→1, `q3754` 3→1.

Top 20 regressions: `q1102` 1→13, `q1352` 1→11, `q1508` 1→20, `q1605` 1→16, `q2036` 1→17, `q2249` 1→18, `q2687` 1→13, `q589` 1→16, `q894` 1→12, `q800` 1→10, `q1576` 1→9, `q16` 1→8, `q1725` 1→8, `q1109` 1→7, `q3615` 1→7, `q116` 2→19, `q2214` 2→11, `q1307` 1→5, `q553` 1→5, `q1958` 1→4. No further parameter search was run.

## Reproduction

Use the separate CUDA environment described in the pre-flight. Download the published vectors and frozen candidate artifact; keep both out of Git. Then run `python -m benchmark.e017_train mine` for shards 0–3 with `--of 4`, `python -m benchmark.e017_train fit --queries 300 --of 4`, and `python -m benchmark.e017_score score --set dev --shard 0 --of 1 --batch 2`, followed by `python -m benchmark.e017_score evaluate --set dev --of 1`. The scripts require the `--vectors`, `--mined`, `--candidates`, `--checkpoint`, `--scores`, and `--output` paths shown by `--help`.

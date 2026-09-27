# E017 pre-flight — GO (2026-09-27)

Base commit: `9a29b27`. Branch: `codex/e017-preflight`. Product code and its CPU `.venv` were not changed. The user clarified that the 45-minute cap applies to compute jobs, not network downloads.

| Check | Measured result |
|---|---|
| GPU | NVIDIA GeForce GTX 1650 Ti, 4,096 MiB VRAM (3,643 MiB free before the rerun) |
| Driver | 581.83; `nvidia-smi` reports maximum CUDA 13.0 |
| Isolated stack | `.venv-gpu` (locally excluded from Git), Python 3.12.6, `torch 2.14.0+cu126`, pinned project libraries; `pip check` passes |
| PyTorch CUDA | `torch.cuda.is_available() == True`; GPU name confirmed by PyTorch |
| Reranker | `Alibaba-NLP/gte-reranker-modernbert-base` loads offline through `CrossEncoder` at 512 tokens |
| Checkpoint integrity | 598,436,708-byte `model.safetensors`; SHA-256 `13c533d902d6a48fa97375c6856c3e60854f9228ea760e3fc18ebde057e0cf31` matches Hugging Face's LFS file hash |
| TRAIN pool | 5,000 train qrels; excluded the frozen first 600 shuffled IDs (seed 20260926), leaving 4,400 eligible queries |
| Micro run | 50 pairs from 25 eligible TRAIN queries; 20 optimizer steps, batch 2, 512 tokens, fp16 autocast, gradient checkpointing, Adafactor |
| Peak allocated VRAM | 1.462 GiB training; 1.194 GiB inference |
| Throughput | 0.8995 training pairs/s (steps 3–20); 3.5654 inference pairs/s (50 pairs) |

The 50-pair micro run used one positive and one document relevant to another eligible TRAIN query per query. Those negatives measured throughput only; they are not the hard GTE negatives required for E017 training. The micro-run weights were not saved.

At the measured rate, one 4,400-query epoch with 1 positive + 4 hard negatives/query is about **6.79 GPU-hours**. Limit each training shard to roughly **350 queries / 1,750 pairs**, projected at **32.4 minutes** before startup and checkpoint overhead; measure each shard and keep it below 45 minutes. DEV and confirmation top-20 scoring are about **28.0 minutes each** at the measured inference rate, so they must be separate jobs. This is a plan from a small throughput sample, not a guarantee; remeasure on actual hard-negative lengths before launching a shard.

The project's `load_dataset_split('train')` returned only TRAIN qrels. The Hugging Face `datasets` builder also materialized a test cache while preparing its configuration; no test rows, labels, rankings, or metrics were read by E017 code. DEV and confirmation IDs were generated solely to exclude them from the micro-run. No DEV, confirmation, or TEST evaluation has run.

**Decision: GO for a bounded E017 experiment.** This pre-flight establishes CUDA operation, model availability, and headroom within 4 GB VRAM. Training must use frozen GTE hard negatives from eligible TRAIN queries and honor the 45-minute per-compute-job limit.

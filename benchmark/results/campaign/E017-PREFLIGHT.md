# E017 pre-flight — blocked (2026-09-27)

Base commit: `9a29b27`. Local branch: `codex/e017-preflight`.

| Check | Observation |
|---|---|
| GPU | NVIDIA GeForce GTX 1650 Ti, 4,096 MiB VRAM (about 3,838 MiB free at start) |
| Driver | 581.83; `nvidia-smi` reports CUDA 13.0 as the maximum supported version |
| Environment | Separate `.venv-gpu`, excluded through `.git/info/exclude`; product `.venv` unchanged |
| CUDA PyTorch | Official `torch==2.14.0+cu126` Windows/Python 3.12 wheel exists, but is not installed |
| Reranker checkpoint | Public model metadata and tokenizer cached; `model.safetensors` is not cached |
| TRAIN data | Existing local train qrels Arrow file verified: 5,000 rows; no evaluation split was loaded |
| Sequence length | Planned 512 tokens with fp16 autocast and gradient checkpointing; not tested |
| Tiny training test | Not started: CUDA PyTorch and the checkpoint are unavailable |

## Download measurements and stop reason

- The CUDA wheel is 2,602,771,598 bytes. A direct official download reached 1,889,468,416 bytes before transfer speed fell sharply. A fresh 10 MiB range request received 2,090,067 bytes in 20 seconds (about 0.10 MB/s). The remaining transfer would exceed the 45-minute job limit at that rate, so the download was stopped. The partial wheel remains in the ignored `.venv-gpu/wheels/` directory for a possible resume.
- The public reranker checkpoint is 598,436,708 bytes. Hugging Face returned HTTP 200 without a token, but a 10 MiB range request received only 331,355 bytes in 20 seconds (about 0.017 MB/s). The single `snapshot_download` attempt was stopped. Small model configuration and tokenizer files were cached.
- The required 20-step TRAIN-only memory and throughput check could not run. Peak VRAM, training pairs/s, inference pairs/s, and a defensible epoch runtime are therefore unknown.

**Decision: BLOCKED.** Resume only when the CUDA wheel and checkpoint can be obtained within the 45-minute per-job limit. Then verify CUDA, run the 20-step TRAIN-only test, and decide whether a 512-token training shard fits 4 GB VRAM and the time budget. No training code, reranker checkpoint, DEV/CONF/TEST evaluation, product code, or release artifact was created during this pre-flight.

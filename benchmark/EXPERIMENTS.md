# Retrieval Experiment Ledger

Every retrieval experiment is recorded here — kept, rejected, or abandoned. Nothing is
ever deleted. Current human-readable status lives in [/RETRIEVAL-PROGRESS.md](../RETRIEVAL-PROGRESS.md).

## Rules (from 2026-09-23)

1. An experiment starts from the trusted baseline tag and changes **one** variable.
2. The hypothesis is written in this file **before** code is written.
3. Rankings are generated, frozen to a TREC run file (SHA-256 recorded), and scored by
   `python -m benchmark.verify_retrieval` — never by the experiment's own code.
4. Tune on `dev` queries (`benchmark/dev_split.json`). Check `confirmation` once per
   candidate. The full 3,765-query set is for final confirmation only.
5. KEEP needs a measured improvement with a paired-bootstrap 95% interval that excludes 0
   (`benchmark/trust/forensics.py::paired_bootstrap`). "Cleaner" or "more robust" is not evidence.
6. Each experiment gets `benchmark/experiments/EXXX.json` and an `exp/EXXX-name` branch.

## Verified experiments (frozen protocol)

| ID | Hypothesis | Main change | Baseline NDCG@10 | New NDCG@10 | Delta (95% CI) | Result | Commit |
|---|---|---|---:|---:|---|---|---|
| BASE | Establish trustworthy baseline under frozen protocol | Trusted Baseline V1 (BM25: 0.06312, Dense: 0.06596, Hybrid: 0.08840) | — | **0.08840** | — | **VERIFIED** | `827e02d` |

Baseline-v1 was scored on the pinned 3,765-query MTEB AppsRetrieval dataset across reference, `pytrec_eval`, and `ir_measures` evaluators with 0 disagreements.

## Pre-registered queue (evaluated against baseline-v1 evidence)

Which experiment runs first is decided by `BOTTLENECK_RULES_V1` in
`benchmark/analyze_baseline.py`, applied to baseline-v1.

**Baseline-v1 Forensic Evidence:**
- Hybrid Oracle@100 = **0.2977** (≥ 0.20 target; candidate retrieval alone does not block reaching 0.20).
- BM25 + Dense Union Hit@100 = **0.3501** (1,318 queries).
- Hybrid Hit@100 = **0.2977** (1,121 queries).
- Union minus Hybrid = **+0.0523** (≥ 0.03 threshold).
- **Rule triggered: FUSION → E001-fusion is active and prioritized.**

| ID | Entry condition (from baseline-v1) | Status | Hypothesis | Exact change | Metric that should move | Cost | Needs Hugging Face? |
|---|---|---|---|---|---|---|---|
| **E001-fusion** | Verdict FUSION: union of BM25 and Dense Hit@100 ≥ Hybrid Hit@100 + 0.03 | **MET (Gain +0.0523 ≥ 0.03) — ACTIVE NEXT** | Equal-weight RRF over 1,000-deep lists buries documents that only one list ranks well (209 answers lost) | RRF `k` ∈ {10, 20, 30, 60, 100} × lexical:semantic weight ∈ {1:1, 1:1.5, 1.5:1} × per-list depth ∈ {100, 300, 1000} (45 settings), computed offline with `analyze_baseline.rrf` from frozen BM25 and Dense runs; winner set in `Settings` on `exp/E001-fusion` | NDCG@10, Hit@10, Hit@100 | Minutes, CPU | **No** — runs entirely on the analysis machine |
| **E002-reranker** | Verdict RANKING, or Hybrid Oracle@100 ≥ 0.20 with actual < half of it | Queued after E001 | Relevant documents sit in top 100 but below rank 10; a cross-encoder orders them better | Rerank Hybrid top-k (k ∈ {20, 50, 100}) with a real cross-encoder over frozen candidates; candidate retrieval unchanged | NDCG@10, MRR@10 (bounded above by Oracle@k) | Hours of CPU on benchmark machine | **Yes** |
| **E003-dense-windows** | Verdict CANDIDATE RETRIEVAL (Hybrid Oracle@100 < 0.20) | Queued for candidate expansion | 23.5% of documents are cut at 256 word-pieces; incomplete embeddings lose documents in candidate generation | Whole-document vector → id-aligned sliding windows (256/64, max over windows) | Dense and Hybrid Hit@100, then NDCG@10 | ~3× embedding time | **Yes** |

## Pre-protocol history (not verified — kept so nothing is lost)

| Label | Change | NDCG@10 | Scorer | Evidence | Status |
|---|---|---:|---|---|---|
| H1 | BM25 (k1 1.5) | 0.06104 | MTEB 2.21 | `results/mteb-bm25/` | real, older code, not reproduced |
| H2 | Hybrid RRF k=60 | 0.08815 | MTEB 2.21 | `results/mteb-hybrid/` | real, older code, not reproduced |
| H3 | BM25 k1 1.6 + code stopwords | 0.06312 (claimed) | MTEB 2.21 (claimed) | none | claim only |
| H4 | H3 inside Hybrid | 0.089 | MTEB 2.21 | `results/mteb/` | real, uncommitted code |
| H5 | Windowed dense (256/64, max-pool) via `apps_fixed.npy` | Dense 0.0010, Hybrid 0.0322 (claimed) | ASTFLOW direct adapter | `results/apps.md` prose only | **invalid** — alignment bug |
| H6 | Unspecified "BM25F + windows + reranker" config | 0.1184 on 100 queries (claimed) | unknown | none | claim only; reranker never executes |

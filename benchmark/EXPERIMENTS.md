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
| BASE | — | Trusted Baseline V1 | — | **not yet established** | — | PENDING | — |

No experiment has run under this protocol. The first one must wait for BASE.

## Pre-registered queue (written 2026-09-23, before any baseline-v1 data was seen)

Which experiment runs first is decided by `BOTTLENECK_RULES_V1` in
`benchmark/analyze_baseline.py`, applied to baseline-v1. Only the experiment whose
entry condition is met runs first; the others wait. Hypotheses are fixed now so the
data cannot shape them afterwards.

Useful identity for this benchmark: every query has exactly one relevant document, so a
perfect reranker over the top-k scores exactly Hit@k (= Recall@k), and
**NDCG@10 ≤ Hit@10**. Reaching 0.20 therefore needs the relevant document inside the
top 10 for at least 753 of 3,765 queries.

Common protocol for all three: baseline = `retrieval-trusted-baseline-v1`; tune on the
1,859 `dev` queries only; score the chosen setting once on the 1,906 `confirmation`
queries; KEEP only if the paired-bootstrap 95% interval of the NDCG@10 delta
(`forensics.paired_bootstrap`, seed 20260923) excludes zero on **both** dev and
confirmation; otherwise REJECT. Every run is frozen and scored by `benchmark/verify_retrieval.py`
or `benchmark/analyze_baseline.py`, never by the experiment's own code.

| ID | Entry condition (from baseline-v1) | Hypothesis | Exact change | Metric that should move | Expected failure mode | Cost | Needs Hugging Face? |
|---|---|---|---|---|---|---|---|
| E001-fusion | Verdict FUSION: union of BM25 and Dense Hit@100 ≥ Hybrid Hit@100 + 0.03 | Equal-weight RRF over 1,000-deep lists buries documents that only one list ranks well | RRF `k` ∈ {10, 20, 30, 60, 100} × lexical:semantic weight ∈ {1:1, 1:1.5, 1.5:1} × per-list depth ∈ {100, 300, 1000} (45 settings), computed offline with `analyze_baseline.rrf` from the frozen BM25 and Dense runs; winner then set in `Settings` on `exp/E001-fusion` and re-run through `verify_retrieval` to confirm the offline number exactly | NDCG@10, Hit@10 | Gains inside noise; 45 settings overfit dev | Minutes, CPU | **No** — runs on the analysis machine |
| E002-reranker | Verdict RANKING, or Hybrid Oracle@100 ≥ 0.20 with actual NDCG@10 < half of it | Relevant documents sit in the top 100 but below rank 10; a cross-encoder reading query and code together orders them better | New stage: rerank Hybrid top-k (k ∈ {20, 50, 100}) with a real cross-encoder over the frozen candidate lists; candidate retrieval unchanged; replace the dead `CROSS_ENCODER_AVAILABLE` block rather than aliasing | NDCG@10, MRR@10 (bounded above by Oracle@k) | A general web-QA cross-encoder may not understand Python; CPU latency (k × 3,765 pairs per run) | Hours of CPU on the benchmark machine | **Yes** |
| E003-dense-windows | Verdict CANDIDATE RETRIEVAL (Hybrid Oracle@100 < 0.20) | 23.5% of documents are cut at 256 word-pieces; relevant documents are being lost in candidate generation because their embedded text is incomplete | Official path only: whole-document vector → the existing id-aligned sliding windows (256/64, max over windows); model, BM25, fusion unchanged | Dense and Hybrid Hit@100, then NDCG@10 | Window noise lowers precision; no gain if relevant documents are mostly short (check: rank vs length on the frozen run first) | ~3× embedding time on the benchmark machine | **Yes** |

A stronger or code-specific embedding model is deliberately **not** in the queue yet: it
changes many variables at once and should follow E003 only if representation, not
truncation, turns out to be the problem.

## Pre-protocol history (not verified — kept so nothing is lost)

These were measured before the frozen protocol existed. Their code state and scorer are
listed as far as the evidence allows. None is a baseline. See the claims table in
[/RETRIEVAL-PROGRESS.md](../RETRIEVAL-PROGRESS.md#metric-claims-we-found).

| Label | Change | NDCG@10 | Scorer | Evidence | Status |
|---|---|---:|---|---|---|
| H1 | BM25 (k1 1.5) | 0.06104 | MTEB 2.21 | `results/mteb-bm25/` | real, older code, not reproduced |
| H2 | Hybrid RRF k=60 | 0.08815 | MTEB 2.21 | `results/mteb-hybrid/` | real, older code, not reproduced |
| H3 | BM25 k1 1.6 + code stopwords | 0.06312 (claimed) | MTEB 2.21 (claimed) | none | claim only |
| H4 | H3 inside Hybrid | 0.089 | MTEB 2.21 | `results/mteb/` | real, uncommitted code |
| H5 | Windowed dense (256/64, max-pool) via `apps_fixed.npy` | Dense 0.0010, Hybrid 0.0322 (claimed) | ASTFLOW direct adapter | `results/apps.md` prose only | **invalid** — document/vector alignment bug, since fixed; windowing itself never validly measured |
| H6 | Unspecified "BM25F + windows + reranker" config | 0.1184 on 100 queries (claimed) | unknown | none | claim only; the reranker in that config never executes |

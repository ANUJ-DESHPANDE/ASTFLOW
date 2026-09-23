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

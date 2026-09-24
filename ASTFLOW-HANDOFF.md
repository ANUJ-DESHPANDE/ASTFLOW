# ASTFLOW Retrieval — Session Handoff

_Last updated 2026-09-24 (baseline-v1 completed, analyzed, and verified). Contains only verified information._

## TRUST STATUS
Measurement system: **VERIFIED** (evaluators verified across 5 scoring tools).
Current trusted baseline: **VERIFIED BASELINE V1 (baseline-v1)**
- **Hybrid NDCG@10:** `0.08840` (MRR@10 `0.07257`, Recall@10 `0.13971`, Recall@100 `0.29774`)
- **Dense NDCG@10:** `0.06596` (MRR@10 `0.05581`, Recall@10 `0.09907`, Recall@100 `0.25259`)
- **BM25 NDCG@10:** `0.06312` (MRR@10 `0.05421`, Recall@10 `0.09216`, Recall@100 `0.22603`)
- **Target:** ~0.20 NDCG@10

## EXACT CODE STATE
Repository: https://github.com/ANUJ-DESHPANDE/ASTFLOW
Branch: `main`
HEAD: commit with baseline-v1 analysis and forensic documentation
Retrieval code (`backend/app/retrieval/`): Clean and unmodified relative to `fe1de96`.
Working tree: CLEAN (uncommitted retrieval modifications discarded; only analysis/documentation updated).

## TWO-MACHINE SETUP
- **Benchmark machine** (has Hugging Face): generated frozen runs (`verify_retrieval`).
- **Analysis machine** (no Hugging Face — never try to reach it): ran `analyze_baseline analyze --tag baseline-v1`. E001-fusion runs **entirely offline** on this machine!

## VERIFIED RETRIEVAL CONFIG (baseline-v1)
Dataset: CoIR-Retrieval/apps (MTEB AppsRetrieval), pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`
Documents: 8,765 · Queries: 3,765 · Qrels: 3,765 pairs, exactly 1 relevant doc per query
Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-d, normalized, threshold 0.05, single vector per doc)
BM25: BM25Okapi k1 1.6, b 0.75, positive IDF, identifier splitting, English+code stopwords
Hybrid: RRF k=60, weights 1/1, depth 1,000 — 100% reconstructible offline from BM25 and Dense runs
Reranker: NONE (disabled / alias)

## CURRENT BOTTLENECK
**FUSION** — Triggered by rule 3 of `BOTTLENECK_RULES_V1`:
- Hybrid Oracle@100 is 0.2977 (≥ 0.20, candidate pool sufficient).
- Union Recall@100 of BM25 and Dense is 0.3501 vs Hybrid Recall@100 of 0.2977.
- Union minus Hybrid is **+0.0523** (≥ 0.03 threshold).
- Current RRF (k=60) pushes **209 valid answers** completely out of the top 100.

## RETRIEVAL FORENSICS (baseline-v1)
- **Top 10 Hits:** BM25 = 347 (9.22%), Dense = 373 (9.91%), Hybrid = 526 (13.97%).
- **Top 100 Hits:** BM25 = 851 (22.60%), Dense = 951 (25.26%), Hybrid = 1,121 (29.77%).
- **Missed >1000:** BM25 = 1,508 (40.05%), Dense = 1,585 (42.10%), Hybrid = 1,327 (35.25%).
- **Oracle Ceilings (Hit@k):** @20: 0.1761 · @50: 0.2340 · @100: 0.2977 · @500: 0.5254 · @1000: 0.6475.
- **Complementarity:** BM25 unique in top 100 = 367; Dense unique in top 100 = 467.

## EXPERIMENT SCOREBOARD
| ID | Change | Baseline NDCG@10 | New NDCG@10 | Delta (95% CI) | Decision |
|---|---|:---:|:---:|---|---|
| BASE | Trusted baseline-v1 | — | **0.08840** | — | **VERIFIED** |
| E001-fusion | Offline RRF parameter optimization | 0.08840 | pending | — | QUEUED (NEXT) |

## NEXT ACTION
Execute **E001-fusion**:
- Tune RRF `k` ∈ {10, 20, 30, 60, 100}, weights, and depth offline with `analyze_baseline.rrf` on the 1,859 `dev` queries.
- Score winner on the 1,906 `confirmation` queries.
- Check paired-bootstrap 95% interval on dev and confirmation.
- Hugging Face required? **NO.** Entirely offline from existing frozen run files.

## FILES TO READ
1. `RETRIEVAL-PROGRESS.md`
2. `benchmark/results/retrieval_forensics.md`
3. `benchmark/EXPERIMENTS.md`
4. `benchmark/CURRENT_STATE.json`

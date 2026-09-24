# ASTFLOW Retrieval — Session Handoff

_Last updated 2026-09-24 (baseline-v1 verified; E001-fusion, E002-reranker and E003-dense-windows evaluated and rejected). Contains only verified information._

## TRUST STATUS
Measurement system: **VERIFIED** (evaluators verified across 5 scoring tools).
Current trusted baseline: **VERIFIED BASELINE V1 (baseline-v1)**
- **Hybrid NDCG@10:** `0.08840` (MRR@10 `0.07257`, Recall@10 `0.13971`, Recall@100 `0.29774`)
- **Dense NDCG@10:** `0.06596` (MRR@10 `0.05581`, Recall@10 `0.09907`, Recall@100 `0.25259`)
- **BM25 NDCG@10:** `0.06312` (MRR@10 `0.05421`, Recall@10 `0.09216`, Recall@100 `0.22603`)
- **Target:** ~0.20 NDCG@10

## EXACT CODE STATE
Repository: https://github.com/ANUJ-DESHPANDE/ASTFLOW
Branch: `exp/E003-dense-windows` (see `git log -1`)
Retrieval code (`backend/app/retrieval/`): baseline BM25 / Dense / Hybrid unchanged. `reranker.py` adds an
opt-in cross-encoder (`ASTFLOW_RERANKER_ENABLED`, default `false`); with it off, Hybrid ranking is bit-for-bit baseline.
E002 was rejected, so the reranker must stay off. E003's windowed Dense exists only as the benchmark option
`verify_retrieval --dense-windows`; production indexing still uses one vector per document.

## TWO-MACHINE SETUP
- **Benchmark machine** (has Hugging Face): generated frozen runs (`verify_retrieval`).
- **Analysis machine** (no Hugging Face — never try to reach it): ran `analyze_baseline analyze --tag baseline-v1`. E001-fusion runs **entirely offline** on this machine!
- **GPU machine** (Hugging Face + CUDA, RTX 4060): ran E002 dev d50/d100, confirmation d20, and the full d20 run, and all E003 runs (embeddings on CPU, as in baseline-v1). GPU and CPU rerank scores agree to 1.6e-5; the GPU full run reproduces the CPU dev d20 run on 1,859 / 1,859 queries.

## VERIFIED RETRIEVAL CONFIG (baseline-v1)
Dataset: CoIR-Retrieval/apps (MTEB AppsRetrieval), pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`
Documents: 8,765 · Queries: 3,765 · Qrels: 3,765 pairs, exactly 1 relevant doc per query
Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-d, normalized, threshold 0.05, single vector per doc)
BM25: BM25Okapi k1 1.6, b 0.75, positive IDF, identifier splitting, English+code stopwords
Hybrid: RRF k=60, weights 1/1, depth 1,000 — 100% reconstructible offline from BM25 and Dense runs
Reranker: NONE in the trusted config (E002 cross-encoder rejected; opt-in flag defaults to off)

## CURRENT BOTTLENECK
**RANKING** — the answer is in the Hybrid top 100 for 29.8% of queries but in the top 10 for only 14.0%.
- Baseline rule 3 of `BOTTLENECK_RULES_V1` first flagged FUSION (union − Hybrid Recall@100 = +0.0523, 209 answers lost by RRF k=60).
- E001-fusion showed RRF parameter changes cannot recover them without hurting top-10 precision.
- E002-reranker showed a general-domain cross-encoder reorders the top-k *worse* than RRF.
- E003-dense-windows made Dense significantly better (+0.0047 NDCG@10 on all queries) but RRF absorbed it (Hybrid +0.0009, CI includes 0).

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
| E001-fusion | Offline RRF parameter optimization (315 configs) | 0.08840 | 0.08845 | Conf: -0.00022 ([-0.00331, +0.00286]) | **REJECT** |
| E002-reranker | `ms-marco-MiniLM-L-6-v2` cross-encoder over Hybrid top-20 (dev winner of 20/50/100) | 0.08840 | 0.06972 | Conf: -0.01672 ([-0.02479, -0.00876]); All: -0.01869 ([-0.02467, -0.01271]) | **REJECT** |
| E003-dense-windows | Sliding-window Dense vectors (256/64, max over windows) | 0.08840 | 0.08932 | Conf: +0.00091 ([-0.00231, +0.00441]); All: +0.00092 ([-0.00145, +0.00333]) | **REJECT** |

## NEXT ACTION
The pre-registered queue (E001–E003) is exhausted. Pre-register **E004** in `benchmark/EXPERIMENTS.md` (hypothesis, one
variable, decision rule) before writing code, using the E001–E003 evidence: Dense improves when it sees whole documents,
RRF absorbs that gain, and a web-trained cross-encoder hurts.

## FILES TO READ
1. `RETRIEVAL-PROGRESS.md`
2. `benchmark/results/retrieval_forensics.md`
3. `benchmark/EXPERIMENTS.md`
4. `benchmark/CURRENT_STATE.json`
5. `benchmark/experiments/E002.json`, `benchmark/experiments/E003.json`

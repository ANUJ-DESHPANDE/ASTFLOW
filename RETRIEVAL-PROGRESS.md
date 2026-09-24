# ASTFLOW Retrieval Progress

> **Read this file first.** It is the only document that describes the *current* state of
> ASTFLOW's search quality. Older files under `docs/audit/` are historical records.
> Last updated: 2026-09-24 (baseline-v1 completed and verified).

---

## WHAT IS ACTUALLY WRONG RIGHT NOW?

*A plain-English explanation for anyone, no search jargon required.*

### 1. How often do we find the right answer in the first 10 results?
**Only 14 out of 100 times (13.97%, or 526 out of 3,765 questions).**
For 86% of questions, a developer looking at the first page of 10 results will not see the code they need. Our official quality score (NDCG@10) is **0.0884**.

### 2. How often in the first 100 results?
**About 30 out of 100 times (29.77%, or 1,121 out of 3,765 questions).**
Even if a developer scrolled through 100 code files, the right answer is only there for 30% of questions. For the other 70%, it is completely absent from the top 100.

### 3. How often do we miss it entirely?
**Over 35 out of 100 times (35.25%, or 1,327 out of 3,765 questions).**
Even if we look through 1,000 returned files, ASTFLOW misses the correct document completely for more than a third of all questions. (For BM25 alone, it misses 40.1%; for Dense alone, it misses 42.1%).

### 4. Is our main problem finding the right code, or ordering the code we already found?
**Right now, both are problems, but our fusion step is actively shooting itself in the foot:**
- **The two search engines find different things:** BM25 (word matching) finds 367 good answers in its top 100 that Dense misses. Dense (meaning matching) finds 467 good answers in its top 100 that BM25 misses.
- **Together, they find 35.0% of the answers in the top 100.**
- **However, when we merge them into Hybrid, we only keep 29.8%.** Our merger (RRF with k=60) pushes **209 correct answers** completely out of the top 100. Furthermore, for 59.2% of all questions, Hybrid ranks the answer *worse* than the better single engine!
- **Ordering (ranking):** Once an answer is inside the top 100, we don't rank it near the top (recall in top 10 is 14.0% vs 29.8% in top 100). But a reranker can only fix ordering; it cannot fix answers that never made it into the top 100.

### 5. What does this imply for the next experiment?
**Fix Fusion first (E001-fusion), then add Reranking (E002-reranker):**
1. **First (Immediate & Offline):** Tune the merger (RRF parameters k, weights, and list depth) to stop throwing away the 209 good answers. This can be tested entirely **offline in minutes** from our frozen run files without downloading models or needing external GPUs. This expands our top-100 candidate pool from 29.8% to up to 35.0%.
2. **Second (Ranking):** Add a real cross-encoder reranker over those top 50–100 candidates. A perfect reranker on top 100 has a ceiling of **0.298** (and ~0.35 with better fusion), which makes achieving the **0.20 target** mathematically feasible. (Note: Reranking only top 20 can never reach 0.20 because its ceiling is only 0.176).

---

## 1. Current Status

| Metric / Dimension | Verified Baseline (baseline-v1) | Target |
|---|:---:|:---:|
| **BM25 NDCG@10** | **0.06312** (MRR@10 0.05421, R@10 0.09216, R@100 0.22603) | — |
| **Dense NDCG@10** | **0.06596** (MRR@10 0.05581, R@10 0.09907, R@100 0.25259) | — |
| **Hybrid NDCG@10** | **0.08840** (MRR@10 0.07257, R@10 0.13971, R@100 0.29774) | **~0.20** |
| Evaluator Agreement | **PASS** (reference, pytrec_eval, ir_measures, trec_eval agree) | 100% |
| Current Bottleneck | **FUSION** (rule `BOTTLENECK_RULES_V1`: union gain 0.0523 ≥ 0.03) | Resolved |

---

## 2. Can We Trust This Number?

**YES.** This is the first verified baseline on the full, pinned benchmark:
- **Dataset:** CoIR-Retrieval/apps (MTEB AppsRetrieval), pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5` (8,765 documents, 3,765 test queries, 1 relevant pair per query).
- **Frozen runs:** All run outputs are frozen in `benchmark/verification/runs/` and verified with exact SHA-256 hashes.
- **Cross-evaluation:** Independent evaluation across reference evaluator, `pytrec_eval`, and `ir_measures` produced 0 disagreements.
- **Offline reconstructibility:** Hybrid matches an offline RRF merge of frozen BM25 and Dense runs across 3,765 / 3,765 queries identically.

---

## 3. Current Retrieval System

```
A developer asks a question
        ↓
ASTFLOW finds code that shares WORDS with the question          (BM25)
        +
ASTFLOW finds code whose MEANING is similar to the question     (Dense / MiniLM)
        ↓
The two ranked lists are merged into one                        (Hybrid / RRF k=60, w=1/1)
        ↓
The top results are returned (Candidate depth = 1,000 on benchmark)
```

Technical details:
- **BM25:** `rank_bm25` BM25Okapi, k1 = 1.6, b = 0.75, positive-IDF variant, code stopwords.
- **Dense:** `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, normalized dot-product, threshold 0.05, max 256 word-pieces (single vector per document).
- **Hybrid:** Reciprocal Rank Fusion, k = 60, weights 1.0 / 1.0, merged at depth 1,000.
- **Reranker:** NONE (`CROSS_ENCODER_AVAILABLE = False` hardcoded; previous "Reranked" labels were identical aliases of Hybrid).

---

## 4. Bottleneck & Forensic Evidence

Detailed forensics are stored in [`benchmark/results/retrieval_forensics.md`](benchmark/results/retrieval_forensics.md).

### First Relevant Document Rank Buckets (N = 3,765)
- **Top 10:** BM25 = 347 (9.22%), Dense = 373 (9.91%), Hybrid = 526 (13.97%).
- **Top 20:** BM25 = 443 (11.77%), Dense = 493 (13.09%), Hybrid = 663 (17.61%).
- **Top 50:** BM25 = 635 (16.87%), Dense = 730 (19.39%), Hybrid = 881 (23.40%).
- **Top 100:** BM25 = 851 (22.60%), Dense = 951 (25.26%), Hybrid = 1,121 (29.77%).
- **Top 500:** BM25 = 1,714 (45.52%), Dense = 1,733 (46.03%), Hybrid = 1,978 (52.54%).
- **Top 1000:** BM25 = 2,257 (59.95%), Dense = 2,180 (57.90%), Hybrid = 2,438 (64.75%).
- **Not retrieved (>1000):** BM25 = 1,508 (40.05%), Dense = 1,585 (42.10%), Hybrid = 1,327 (35.25%).

### Oracle Reranking Ceilings
Because each query has exactly 1 relevant document, a perfect reranker over the top-k candidates yields NDCG@10 = Hit@k:
- **Oracle@20:** 0.1761 (mathematically cannot reach 0.20 target).
- **Oracle@50:** 0.2340 (target is reachable).
- **Oracle@100:** 0.2977 (target is reachable with ~67% precision of reranked hits).
- **Oracle@500:** 0.5254.
- **Oracle@1000:** 0.6475.

### Complementarity & Merger Loss
- BM25 finds 367 correct documents in top 100 that Dense misses.
- Dense finds 467 correct documents in top 100 that BM25 misses.
- **Union Hit@100 = 1,318 queries (35.01%)**.
- **Hybrid Hit@100 = 1,121 queries (29.77%)**.
- **Net lost by RRF merger:** **209 queries (5.23% absolute recall)**.
- Hybrid ranks worse than the best single engine for 2,228 queries (59.18%).

---

## 5. Experiment Queue Priority

Under `BOTTLENECK_RULES_V1`:
1. **Next Experiment: E001-fusion (OFFLINE)**
   - **Hypothesis:** Default RRF (k=60, 1:1 weights, depth 1000) dilutes documents supported strongly by only one retriever. Grid searching RRF k ∈ {10, 20, 30, 60, 100}, lexical:semantic weights, and candidate depths on the dev split will recover lost candidates without losing agreement.
   - **Needs Hugging Face?** **NO.** Can be performed entirely on this machine from frozen runs in minutes.
2. **Follow-up: E002-reranker**
   - **Hypothesis:** A cross-encoder reranking the top 50–100 candidates will elevate documents ranked between 11–100 into the top 10, approaching the 0.298+ oracle ceiling.
3. **Follow-up: E003-dense-windows**
   - Candidate retrieval expansion for the 65% of queries missed by both engines.

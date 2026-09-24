# ASTFLOW Retrieval Progress

> **Read this file first.** It is the only document that describes the *current* state of
> ASTFLOW's search quality. Older files under `docs/audit/` are historical records.
> Last updated: 2026-09-24 (baseline-v1 completed; E001-fusion and E002-reranker evaluated and rejected).

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
**Right now, both are problems, but the combination method is a key factor:**
> "We discovered that BM25 and Dense each find different correct answers. The current system combines them in a way that sometimes throws those answers away. We are therefore testing the combination method before changing either search engine."

- **The two search engines find different things:** BM25 (word matching) finds 367 good answers in its top 100 that Dense misses. Dense (meaning matching) finds 467 good answers in its top 100 that BM25 misses.
- **Together, they find 35.0% of the answers in the top 100.**
- **However, when we merge them into Hybrid, we only keep 29.8%.** Our merger (RRF with k=60) pushes **209 correct answers** completely out of the top 100. Furthermore, for 59.2% of all questions, Hybrid ranks the answer *worse* than the better single engine!

### 5. What did the fusion experiment (E001) reveal, and what comes next?
**RRF parameter tuning cannot solve this on its own (E001: REJECT):**
- We tested 315 combinations of RRF $k$, weights, and depth on 1,859 development questions.
- A higher $k$ ($k=100$) recovers some lost answers into the top 100 (Recall@100 increased to 31.5%), but hurts top-10 ordering (NDCG@10 dropped to 0.0876).
- Tweaking $k=30$ gave a microscopic gain on dev (+0.0003), but lost ground on confirmation (-0.0002). Neither change was statistically significant.
- **Why?** RRF simply adds reciprocal ranks ($1/(k+rank)$); it has no understanding of what the words or code actually mean. Shifting ranks around dilutes precision.
- **What this implied:** move to **E002-reranker** (a true cross-encoder reranker).

### 6. Did the reranker experiment (E002) help?
**No — it made results worse (E002: REJECT):**
- We asked an off-the-shelf "reranker" model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to re-read the top 20, 50, or 100 candidates together with the question and re-order them.
- It hurt at every depth, and more so the deeper it read: dev NDCG@10 fell from 0.0935 to **0.0728** (top 20), **0.0581** (top 50), and **0.0515** (top 100).
- On the untouched confirmation questions (top 20, run once) it fell from 0.0834 to **0.0667**; across all 3,765 questions from 0.0884 to **0.0697**. The right answer now appears in the first 10 results 474 times instead of 526.
- **Why?** This model learned relevance from web search passages, not from programming problems paired with Python solutions. It rewards code that *looks* on-topic, and that is worse than the current merge.
- **What this implies:** a general-purpose reranker is not the fix. A reranker trained on code would be a new experiment. Next in the pre-registered queue is **E003-dense-windows** (recovering answers the dense engine never sees because long documents are cut off).

---

## 1. Current Status

| Metric / Dimension | Verified Baseline (baseline-v1) | Target |
|---|:---:|:---:|
| **BM25 NDCG@10** | **0.06312** (MRR@10 0.05421, R@10 0.09216, R@100 0.22603) | — |
| **Dense NDCG@10** | **0.06596** (MRR@10 0.05581, R@10 0.09907, R@100 0.25259) | — |
| **Hybrid NDCG@10** | **0.08840** (MRR@10 0.07257, R@10 0.13971, R@100 0.29774) | **~0.20** |
| Evaluator Agreement | **PASS** (reference, pytrec_eval, ir_measures, trec_eval agree) | 100% |
| Current Bottleneck | **RANKING** — RRF tuning (E001) and a general-domain cross-encoder (E002) both failed | Active |

---

## 2. Can We Trust This Number?

**YES.** This is the first verified baseline on the full, pinned benchmark:
- **Dataset:** CoIR-Retrieval/apps (MTEB AppsRetrieval), pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5` (8,765 documents, 3,765 test queries, 1 relevant pair per query).
- **Frozen runs:** All run outputs are frozen in `benchmark/verification/ranks/` and verified with exact SHA-256 hashes.
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

---

## 4. Experiment History

| ID | Description | Dev NDCG@10 | Conf NDCG@10 | Full NDCG@10 | Decision | Key Takeaway |
|---|---|:---:|:---:|:---:|:---:|---|
| **BASE** | Verified baseline-v1 | 0.09351 | 0.08342 | **0.08840** | **VERIFIED** | First trusted baseline; established 5-way evaluator consensus. |
| **E001-fusion** | Controlled RRF sweep (315 configs) | 0.09383 | 0.08321 | **0.08845** | **REJECT** | Parameter tuning cannot resolve merger dilution without harming NDCG; unlocks E002. |
| **E002-reranker** | MS-MARCO MiniLM cross-encoder over Hybrid top-k (k = 20 / 50 / 100) | 0.07281 (k=20) | 0.06670 | **0.06972** | **REJECT** | Worse than RRF at every depth (CI excludes 0); web-trained reranker does not transfer to code. |

---

## 5. Next Steps

- **Active Experiment: E003-dense-windows** (next in the pre-registered queue)
  - Replace the single whole-document vector with id-aligned sliding windows (256/64, max over windows) so the 23.5% of documents truncated at 256 word-pieces can be found.
  - Candidate pool headroom (Oracle@100 = 0.2977) still supports the ~0.20 NDCG@10 target; a code-trained reranker remains a possible later experiment.

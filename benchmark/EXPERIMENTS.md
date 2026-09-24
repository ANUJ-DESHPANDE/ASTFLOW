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
| **E001-fusion** | "Current equal-weight RRF is burying correct candidates that one retriever found strongly. Changing fusion should recover some of these candidates." | Systematic sweep of 315 RRF configurations: k ∈ {10, 20, 30, 60, 100} × weights ∈ {1:0, 0:1, 1:3, 1:2, 1:1.5, 1:1, 1.5:1, 2:1, 3:1} × depth ∈ {10, 20, 50, 100, 200, 500, 1000} on 1,859 dev queries | 0.08840 (Dev: 0.09351, Conf: 0.08342) | Dev Winner: **0.09383** (k=30, 1:1, d=1000); Conf: **0.08321**; All: **0.08845** | Dev: +0.00032 ([-0.00251, +0.00310]); Conf: -0.00022 ([-0.00331, +0.00286]) | **REJECT** | `exp/E001-fusion` |
| **E002-reranker** | "The current Hybrid candidate pool contains relevant documents that are ranked too low. A model that jointly reads the query and candidate code may distinguish relevant candidates better than mechanical RRF." | CrossEncoder (`cross-encoder/ms-marco-MiniLM-L-6-v2` @ `233902d`) reranking frozen Hybrid top-k, k ∈ {20, 50, 100} on 1,859 dev queries | 0.08840 (Dev: 0.09351, Conf: 0.08342) | Dev Winner: **0.07281** (k=20); Conf: **0.06670**; All: **0.06972** | Dev: -0.02070 ([-0.02975, -0.01186]); Conf: -0.01672 ([-0.02479, -0.00876]); All: -0.01869 ([-0.02467, -0.01271]) | **REJECT** | `exp/E002-reranker` |
| **E003-dense-windows** | "23.5% of documents are cut at 256 word-pieces; embedding every part of a document lets Dense find answers it never retrieves, and Hybrid inherits them." | Dense document vector → id-aligned sliding windows (256/64, max over windows); one pre-registered configuration | 0.08840 (Dev: 0.09351, Conf: 0.08342) | Hybrid Dev: **0.09444**; Conf: **0.08433**; All: **0.08932** (Dense All: 0.06596 → **0.07065**) | Hybrid Dev: +0.00093 ([-0.00232, +0.00426]); Conf: +0.00091 ([-0.00231, +0.00441]); All: +0.00092 ([-0.00145, +0.00333]) | **REJECT** | `exp/E003-dense-windows` |

### Detailed Findings for E001-fusion
- **Question A (Best Top-100 Candidate Recall):** $k=100$, ratio $1:1$, depth $500$ maximized DEV Recall@100 to `0.31469` (vs `0.30554` baseline, recovering 17 more candidates on DEV and 25 more across the full test set). However, this dropped NDCG@10 to `0.08757`.
- **Question B (Best NDCG@10):** $k=30$, ratio $1:1$, depth $1000$ produced the highest DEV NDCG@10 (`0.09383` vs `0.09351`, delta `+0.00032`), but failed on confirmation (`0.08321` vs `0.08342`, delta `-0.00022`).
- **Conclusion:** Neither split's 95% bootstrap interval excludes zero. RRF is a rank-sum heuristic that cannot separate semantic matches from keyword noise; parameter shifts alone cannot recover the 209 lost candidates without degrading top-10 precision. RRF optimization alone is **rejected**.
- Full sweep data archived in [`benchmark/results/fusion_sweep_e001.json`](results/fusion_sweep_e001.json).

### Detailed Findings for E002-reranker
- **Dev sweep (1,859 queries, NDCG@10 vs 0.09351 baseline):**

  | Depth | NDCG@10 | Delta (95% CI) | MRR@10 | Recall@10 | Recall@20 |
  |---:|---:|---|---:|---:|---:|
  | 20 | **0.07281** | -0.02070 ([-0.02975, -0.01186]) | 0.05483 | 0.13233 | 0.18236 |
  | 50 | 0.05805 | -0.03546 ([-0.04550, -0.02566]) | 0.04395 | 0.10490 | 0.15923 |
  | 100 | 0.05146 | -0.04205 ([-0.05292, -0.03142]) | 0.03978 | 0.09037 | 0.12964 |

  Every depth is significantly worse than Hybrid, and the loss grows with depth: the deeper the pool
  handed to the cross-encoder, the more distractors it promotes into the top 10.
- **Confirmation (depth 20, run once, 1,906 queries):** 0.08342 → 0.06670 (-0.01672, CI [-0.02479, -0.00876]); MRR@10 0.06766 → 0.05071.
- **Full set (depth 20, 3,765 queries, tag `e002-reranked-d20`):** 0.08840 → 0.06972 (-0.01869, CI [-0.02467, -0.01271]);
  MRR@10 0.07257 → 0.05274; Recall@10 0.13971 → 0.12590. NDCG@10 improved on 210 queries and worsened on 335.
- **Why:** `ms-marco-MiniLM-L-6-v2` is trained on web passages, not on problem-statement → Python-solution
  pairs. It reorders by surface topicality and does worse than rank fusion on this task.
- **Verification:** runs scored independently by `python -m benchmark.score_e002` (reference, astflow,
  pytrec_eval, ir_measures: 0 disagreements); only the top-k is permuted and the tail is untouched on all
  3,765 queries; every committed `ranks/e002-*.ranks.tsv.gz` rebuilds its recorded run SHA-256. The full run was
  produced on GPU (CUDA) and matches the CPU-produced dev d20 run on 1,859 / 1,859 dev queries.
- **Artifacts:** [`experiments/E002.json`](experiments/E002.json), `results/reranker_{dev_d20,dev_d50,dev_d100,confirmation_d20,all_d20}.json`,
  `verification/ranks/e002-*.ranks.tsv.gz`. A general-domain cross-encoder is **rejected**; a code-trained
  reranker would be a new, separately pre-registered experiment.

### Detailed Findings for E003-dense-windows
- **Configuration:** the single pre-registered one — windows of 256 word-pieces, overlap 64, max over windows.
  8,765 documents → 13,545 windows; 2,039 documents need more than one window (max 316).
- **Environment control:** the unchanged harness regenerated baseline dense and hybrid on `dev` on this machine.
  Rankings differ from the frozen files only in low-ranked positions (top 100 identical for 1,844 / 1,859 dense and
  1,854 / 1,859 hybrid queries) and **0 queries change any reported metric**, so frozen baseline-v1 remains the comparator.
  (The pre-registration asked for identical rankings; this relaxation is recorded here and in `experiments/E003.json`.)
- **Results vs frozen baseline-v1** (NDCG@10 delta with paired-bootstrap 95% CI; Hit@100 = queries with the answer in the top 100):

  | Split | Mode | NDCG@10 | Delta (95% CI) | MRR@10 | Recall@10 | Hit@100 |
  |---|---|---|---|---|---|---|
  | dev (1,859) | Dense | 0.06904 → 0.07253 | +0.00349 ([+0.00025, +0.00720]) | 0.05955 → 0.06173 | 0.10005 → 0.10758 | 473 → 481 |
  | dev | **Hybrid** | 0.09351 → 0.09444 | +0.00093 ([-0.00232, +0.00426]) | 0.07761 → 0.07776 | 0.14470 → 0.14900 | 568 → 565 |
  | confirmation (1,906) | Dense | 0.06295 → 0.06881 | +0.00587 ([+0.00198, +0.01025]) | 0.05217 → 0.05807 | 0.09811 → 0.10388 | 478 → 493 |
  | confirmation | **Hybrid** | 0.08342 → 0.08433 | +0.00091 ([-0.00231, +0.00441]) | 0.06766 → 0.06910 | 0.13484 → 0.13379 | 553 → 560 |
  | all (3,765) | Dense | 0.06596 → 0.07065 | +0.00469 ([+0.00202, +0.00744]) | 0.05581 → 0.05988 | 0.09907 → 0.10571 | 951 → 974 |
  | all | **Hybrid** | 0.08840 → 0.08932 | +0.00092 ([-0.00145, +0.00333]) | 0.07257 → 0.07338 | 0.13971 → 0.14130 | 1,121 → 1,125 |

- **Decision: REJECT.** The Hybrid dev delta was positive, so confirmation and the full set were run once as
  pre-registered, but the Hybrid NDCG@10 CI includes 0 on every split (the KEEP rule needs it to exclude 0).
- **What it shows:** windows make Dense itself significantly better on every split (all: +0.00469, CI excludes 0;
  +23 answers in the top 100), confirming that truncation costs Dense. RRF k=60 absorbs almost all of that gain:
  Hybrid moves +0.0009 and gains only 4 top-100 answers on the full set. Recall@100 CIs include 0 in both modes.
- **Verification:** runs generated and cross-checked by `benchmark.verify_retrieval` (reference, astflow,
  pytrec_eval, ir_measures agree on all 6 runs); window alignment proven (all 6,726 single-window documents match
  their whole-document vectors, min cosine 0.9999996; 25 probe documents re-embedded window by window, min cosine
  0.9999998; window counts match the tokenizer for all 8,765 documents); every `ranks/e003-windows*.ranks.tsv.gz`
  rebuilds its manifest's run SHA-256. Record: [`experiments/E003.json`](experiments/E003.json).

### Pre-registration for E003-dense-windows (written 2026-09-24, before any E003 code)
- **Hypothesis:** 23.5% of documents (2,061 / 8,765, `docs/audit/corpus-analysis.json`) exceed MiniLM's 256
  word-piece limit, so their single dense vector ignores the rest of the code. Embedding every part of a document
  lets Dense find answers it currently never retrieves, and Hybrid inherits those candidates.
- **The one variable:** dense *document* representation. Whole-document vector → id-aligned sliding windows over the
  document's word-pieces, window 256, overlap 64 (stride 192), each window embedded by the same model; document
  score = max cosine over its windows. Documents of ≤ 256 word-pieces keep exactly one vector. Implemented with the
  existing `Embedder.encode(use_windows=True, window_size=256, overlap=64)` and the Retriever's existing max-pool
  path, used as-is. (Known property of that code: windows are decoded to text and re-tokenized, and the model's
  256 limit includes `[CLS]`/`[SEP]`, so a full window loses its last 2 word-pieces — covered by the 64-piece
  overlap except at a document's very end.)
- **Unchanged:** BM25; dense model and weights (`all-MiniLM-L6-v2`, safetensors SHA-256 `1377e9af…`); query encoding;
  dense threshold 0.05; RRF k=60, weights 1:1; candidates 500; depth 1,000; boosts off; qrels; evaluator; tie-break.
- **Configurations:** exactly one (256/64, max-pool). No sweep over window size, overlap or pooling is registered.
- **Generation and scoring:** `python -m benchmark.verify_retrieval --dense-windows 256:64 --modes dense,hybrid`
  (frozen TREC runs, cross-checked by every available evaluator, manifest with checksums). BM25 is not regenerated.
- **Environment control:** before E003 is compared, the unchanged harness regenerates baseline dense and hybrid on
  `dev`; its rankings must match the frozen baseline-v1 rank files per query.
- **Metrics:** Dense and Hybrid Recall@100 (= Hit@100; one relevant document per query) is the mechanism metric;
  NDCG@10, MRR@10 and Recall@10 are reported for both modes. Paired bootstrap 95% CI
  (`forensics.paired_bootstrap`, 10,000 samples, seed 20260923) on NDCG@10 and Recall@100, against the frozen
  baseline-v1 rank files.
- **Decision rule (rule 5):** the system's output is Hybrid, so **KEEP** requires a positive Hybrid NDCG@10 delta whose
  CI excludes 0 on `dev`, confirmed by a positive Hybrid NDCG@10 delta whose CI excludes 0 on `confirmation`.
  Gains in Dense only, or in Recall@100 only, are reported as evidence but do not earn KEEP.
- **Procedure:** run `dev`. If the Hybrid NDCG@10 dev delta is positive, run `confirmation` once, then the full
  3,765-query set as the official frozen run. If it is not positive, E003 is **REJECT** on `dev` and `confirmation`
  stays untouched (there is no registered sweep to continue).

---

## Pre-registered queue (evaluated against baseline-v1 evidence)

Which experiment runs first is decided by `BOTTLENECK_RULES_V1` in
`benchmark/analyze_baseline.py`, applied to baseline-v1.

| ID | Entry condition | Status | Hypothesis | Exact change | Metric that should move | Cost | Needs Hugging Face? |
|---|---|---|---|---|---|---|---|
| **E001-fusion** | Verdict FUSION (gain ≥ 0.03) | **EVALUATED — REJECT** | RRF parameter tuning recovers lost candidates without harming precision | RRF k, weights, depth sweep offline | NDCG@10, Hit@100 | Minutes, CPU | **No** |
| **E002-reranker** | Next in queue (RRF cannot fix ranking or recover candidates cleanly) | **EVALUATED — REJECT** | A cross-encoder reading query and code together can score relevance directly over the top 50–100 candidates | Rerank Hybrid top-k (k ∈ {20, 50, 100}) with a real cross-encoder over frozen candidates; candidate retrieval unchanged | NDCG@10, MRR@10 (bounded above by Oracle@k = 0.2977) | Hours of CPU on benchmark machine | **Yes** |
| **E003-dense-windows** | Candidate expansion for the 65% of queries missed by both engines | **EVALUATED — REJECT** | 23.5% of documents are cut at 256 word-pieces; incomplete embeddings lose documents in candidate generation | Whole-document vector → id-aligned sliding windows (256/64, max over windows) | Dense and Hybrid Hit@100, then NDCG@10 | ~3× embedding time | **Yes** |

---

## Pre-protocol history (not verified — kept so nothing is lost)

| Label | Change | NDCG@10 | Scorer | Evidence | Status |
|---|---|---:|---|---|---|
| H1 | BM25 (k1 1.5) | 0.06104 | MTEB 2.21 | `results/mteb-bm25/` | real, older code, not reproduced |
| H2 | Hybrid RRF k=60 | 0.08815 | MTEB 2.21 | `results/mteb-hybrid/` | real, older code, not reproduced |
| H3 | BM25 k1 1.6 + code stopwords | 0.06312 (claimed) | MTEB 2.21 (claimed) | none | claim only |
| H4 | H3 inside Hybrid | 0.089 | MTEB 2.21 | `results/mteb/` | real, uncommitted code |
| H5 | Windowed dense (256/64, max-pool) via `apps_fixed.npy` | Dense 0.0010, Hybrid 0.0322 (claimed) | ASTFLOW direct adapter | `results/apps.md` prose only | **invalid** — alignment bug |
| H6 | Unspecified "BM25F + windows + reranker" config | 0.1184 on 100 queries (claimed) | unknown | none | claim only; reranker never executes |

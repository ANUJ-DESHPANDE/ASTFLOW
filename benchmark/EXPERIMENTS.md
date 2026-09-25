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
- **Product follow-up (2026-09-25 audit):** the rejected cross-encoder was still reachable in the product through the
  undocumented `ASTFLOW_RERANKER_ENABLED` setting (`backend/app/retrieval/reranker.py`). It was removed from the
  product path; `Retriever.rank` now rejects any mode other than `bm25`/`dense`/`hybrid`. The benchmark runner that
  produced the E002 results (`benchmark/run_reranker_benchmark.py`) and all E002 artifacts are unchanged.

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
- **Correction (post-E003 read-only audit, 2026-09-25):** "RRF absorbs the gain" is incomplete. Split by the relevant
  document's length (all 3,765 queries, frozen runs): for the 1,168 queries whose answer is longer than 256 word-pieces,
  Dense NDCG@10 0.0634 → 0.0866 and **Hybrid 0.0989 → 0.1145** (Dense Hit@100 308 → 374); for the 2,597 queries whose
  answer is ≤ 256, Dense 0.0671 → 0.0635 and **Hybrid 0.0837 → 0.0780** (Dense Hit@100 643 → 600). Max-pooling over
  windows favours long documents, pushing short correct answers down. Hybrid kept about half of the positive Dense
  gain (+17.6 of +33.3 summed NDCG points on the 65 queries Dense improved); the short-document losses cancelled it.
  The null Hybrid result is therefore a representation trade-off, not only fusion absorption.
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

### Pre-registration for E004-long-query (written 2026-09-25, before any E004 code)

**Question.** Does allowing dense retrieval to represent the complete query, rather than only the first 256
word-pieces, significantly improve dense retrieval recall, and does that improvement carry through to the production
hybrid ranking?

**Evidence behind it** (post-E003 read-only audit of committed runs): 3,350 / 3,765 queries (89.0%; dev 1,650 / 1,859,
confirmation 1,700 / 1,906) exceed 254 content word-pieces (median 467, p90 759, max 2,570). On the 415 queries that
fit, Dense NDCG@10 is 0.161 vs BM25 0.091; on truncated queries 0.054 vs 0.060 (correlational: short problems may also
be easier). 65% of answers are in neither retriever's top 100, so first-stage recall is the main limit.

**What the current model and API permit** (measured on this machine, not assumed):
- `sentence-transformers/all-MiniLM-L6-v2` (BERT, 6 layers, 384-d, absolute position embeddings, 512 positions) runs
  as Transformer → mean Pooling → Normalize. `max_seq_length` is 256 (tokenizer `model_max_length` 256), i.e. 254
  content word-pieces plus `[CLS]`/`[SEP]`. Everything after is silently dropped: for a 692-piece query,
  `encode(full query)` equals the embedding of its first 254 pieces (cosine 1.0000000), while the next 254 pieces embed
  to cosine 0.66 with it.
- The only query-encoding call is `Retriever.rank` → `Embedder.encode([query])` (`search.py:105`). Document vectors,
  BM25, RRF and the reranker flag are separate code paths.
- Raising `max_seq_length` to 512 is mechanically possible but does not represent the complete query (1,551 / 3,765 =
  41.2% exceed 510 content pieces) and puts positions 257–512, which this model was never fine-tuned on, into play.
  It changes two things at once and still truncates, so it is **not** a condition.

**Separation of concerns — what E004 changes and what it holds fixed:**

| Layer | E004 |
|---|---|
| Query-side representation | **Changed** (the one variable) |
| Document-side representation | Fixed: baseline-v1 one vector per document (not E003's windows); vector cache identity `cc3d1f5b729fa376dc5f9aed` |
| Fusion | Fixed: RRF k=60, weights 1:1, candidates 500, depth 1,000, boosts off; no tuning |
| Reranking | None (E002 reranker off) |
| BM25, qrels, evaluator, dense threshold 0.05, model weights (SHA-256 `1377e9af…`), production defaults | Unchanged |

**The one experimental condition — `longquery-mean254`:**
1. Tokenize the query with the model's own tokenizer, no special tokens, no truncation.
2. Split the word-piece ids into consecutive **non-overlapping** chunks of 254 (the last chunk may be shorter). Chunks
   are built from token ids directly (no decode/re-tokenize) and each is wrapped as `[CLS] chunk [SEP]` ≤ 256 — the
   model's configured limit, so no chunk uses a position the baseline does not use.
3. Run each chunk through the model's Transformer and mean-Pooling modules (pre-Normalize). Combine chunks by a mean
   weighted by each chunk's token count (content + 2 specials), then L2-normalize. This equals the model's own
   mean pooling over every token of the query, each token contextualized within its chunk.
4. Score documents with that single query vector exactly as today (dot product with the baseline document vectors,
   threshold 0.05), then RRF as today. One query vector → one dense ranking; no max/sum over chunks.

Queries of ≤ 254 content word-pieces become a single chunk and are, by construction, encoded exactly as in the baseline.
Only the 3,350 truncated queries can change.

**Why one condition, and why this one.** It changes only how much of the query the dense model sees. It keeps the
model's pooling rule (mean over tokens), its sequence limit, the single-vector scoring and every other layer. Rejected
alternatives, each of which would add a second variable: 512 tokens (still truncates, untrained positions); max or sum
over per-chunk scores (changes the similarity function and the meaning of the 0.05 threshold); overlapping chunks
(counts some tokens twice in the mean); first+last chunk or summarization (partial or rewritten query).

**Integrity requirements (a run that fails any of these is invalid, not a result):**
- For every query of ≤ 254 content word-pieces, the E004 query vector equals the baseline `Embedder.encode` vector
  (cosine ≥ 0.99999), and its per-query Dense and Hybrid metrics equal frozen baseline-v1.
- For truncated queries, the baseline vector equals the first chunk's normalized embedding (cosine ≥ 0.99999),
  proving the baseline saw only that chunk.
- On probe queries, the chunk-weighted vector equals a direct mean over all chunks' token embeddings (cosine ≥ 0.99999).
- Document vectors are the baseline-v1 cache (same identity, harness alignment probe passes).
- All evaluators in `evaluation.cross_check` agree; runs are generated from committed code (no tracked-file changes);
  every frozen rank file rebuilds its manifest SHA-256.

**Baseline.** Frozen baseline-v1 `dense` and `hybrid` rank files. The E003 environment control (same machine and
package versions: 0 queries changed any metric) applies; the first integrity check above re-verifies it inside E004.

**Metrics** (vs frozen baseline-v1, paired bootstrap 95% CI, `forensics.paired_bootstrap`, 10,000 samples,
seed 20260923):
- **Primary (decides):** Hybrid NDCG@10.
- **Secondary (reported, do not decide):** Hybrid MRR@10, Recall@10, Recall@100 (= Hit@100) with CI on Recall@100.
- **Diagnostic (answers the question's first half; does not decide):** Dense NDCG@10, MRR@10, Recall@10, Recall@100
  with CIs on NDCG@10 and Recall@100; the same split into truncated vs fitting queries and by chunk count (2, 3, ≥ 4).
- The oracle diagnostics are not used to claim anything.

**Decision rule.** KEEP requires, on the primary metric: a positive Hybrid NDCG@10 delta whose 95% CI excludes 0 on
`dev`, **and** the same on `confirmation`, **and** all integrity requirements met. Anything else is REJECT. Dense-only
or Recall-only gains are recorded as evidence and do not earn KEEP.

**Procedure.**
1. Commit the implementation (a benchmark-only query encoder, a `verify_retrieval` flag, a freeze/score script) before
   any run; production code and defaults are not touched.
2. `dev` (1,859): generate `dense,hybrid` with the condition. If the dev primary criterion fails → **REJECT**, stop;
   `confirmation` stays untouched.
3. If dev passes → `confirmation` (1,906) once → full 3,765-query set once as the official frozen run. Decision from
   dev + confirmation; the full set is reported.
4. No retuning between steps (no change to chunk size, pooling, threshold or RRF).

**Computational cost** (measured): document vectors are reused from the baseline-v1 cache (no re-embedding). Queries
need 9,188 chunk passes instead of 3,765 (mean 2.44 chunks; distribution 1: 415, 2: 1,789, 3: 1,186, 4: 294, ≥5: 81),
≈ 23 ms per chunk on CPU → ≈ +2 minutes of query encoding over all queries, ≈ +35 ms median per query. Expected wall
time on this machine: ≈ 12 min for `dev`; ≈ 45 min if confirmation and the full set also run.

**Artifacts.** Runs generated into a scratch `--out` (verify_retrieval rewrites `<out>/apps.qrels`), then frozen:
`benchmark/verification/manifest-e004-longquery{-dev,-confirmation,}.json`,
`ranks/e004-longquery{-dev,-confirmation,}-{dense,hybrid}.ranks.tsv.gz`, per-query TSVs, and
`benchmark/experiments/E004.json` (condition, per-query chunk counts, integrity proofs, metrics and CIs per split and
subgroup, runtime, environment, code SHA-256, decision). Embeddings on CPU, as in baseline-v1.

**Reproducibility.** Pinned dataset revision `f22508f9…`, qrels SHA-256, model weights SHA-256, package versions,
bootstrap seed, generator commit and file hashes recorded in the manifests and `E004.json`; rank files rebuild their
run SHA-256; re-running the scorer on committed artifacts must reproduce `E004.json`.

**Production implications.** Query-side only: no index rebuild, no embedding-cache or `embeddings.npy` change, no
schema bump. Adoption would add a long-query encoding method to `Embedder` used by `Retriever.rank` (also reached by
the agent's follow-up queries), behind a `Settings` flag, with latency growing ≈ 23 ms per extra 254-piece chunk on CPU.
Queries that fit in 254 word-pieces are unaffected by construction; how long real app queries are has not been measured. Production defaults stay unchanged unless
E004 is KEEP and a separate change is approved.

---

## Pre-registered queue (evaluated against baseline-v1 evidence)

Which experiment runs first is decided by `BOTTLENECK_RULES_V1` in
`benchmark/analyze_baseline.py`, applied to baseline-v1.

| ID | Entry condition | Status | Hypothesis | Exact change | Metric that should move | Cost | Needs Hugging Face? |
|---|---|---|---|---|---|---|---|
| **E001-fusion** | Verdict FUSION (gain ≥ 0.03) | **EVALUATED — REJECT** | RRF parameter tuning recovers lost candidates without harming precision | RRF k, weights, depth sweep offline | NDCG@10, Hit@100 | Minutes, CPU | **No** |
| **E002-reranker** | Next in queue (RRF cannot fix ranking or recover candidates cleanly) | **EVALUATED — REJECT** | A cross-encoder reading query and code together can score relevance directly over the top 50–100 candidates | Rerank Hybrid top-k (k ∈ {20, 50, 100}) with a real cross-encoder over frozen candidates; candidate retrieval unchanged | NDCG@10, MRR@10 (bounded above by Oracle@k = 0.2977) | Hours of CPU on benchmark machine | **Yes** |
| **E003-dense-windows** | Candidate expansion for the 65% of queries missed by both engines | **EVALUATED — REJECT** | 23.5% of documents are cut at 256 word-pieces; incomplete embeddings lose documents in candidate generation | Whole-document vector → id-aligned sliding windows (256/64, max over windows) | Dense and Hybrid Hit@100, then NDCG@10 | ~3× embedding time | **Yes** |
| **E004-long-query** | Post-E003 audit: 89% of queries exceed Dense's 256 word-piece limit | **PRE-REGISTERED — awaiting approval to run** | Dense sees only the first 254 query word-pieces; representing the complete query improves Dense recall and carries into Hybrid | Query vector = token-weighted mean over non-overlapping 254-piece query chunks (one condition, `longquery-mean254`); documents, BM25, RRF unchanged | Hybrid NDCG@10 (decides); Dense Recall@100/NDCG@10 (diagnostic) | ≈ +2 min query encoding; no re-embedding | **Yes** (model already cached) |

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

# ASTFLOW Retrieval Progress

> **Read this file first.** It is the only document that describes the *current* state of
> ASTFLOW's search quality. Older files under `docs/audit/` are historical records.
> Last updated: 2026-09-23 (second session: baseline-v1 reported running on the benchmark machine).

---

## 1. Current Status

| | |
|---|---|
| **Current trusted NDCG@10** | **UNKNOWN — verification in progress** |
| Target | about 0.20 |
| Verification status | **Measuring tool: VERIFIED. Actual score: NOT VERIFIED.** |

**What this means in plain English.** We have now proven that our *measuring tool* is
correct: five independent scoring programs, including the official U.S. NIST tool that
the research community uses, give the same answer on the same search results. But we
have **not yet run today's ASTFLOW on the real benchmark** with that tool, because the
machine this session ran on is blocked from downloading the benchmark data and the AI
model (it cannot reach `huggingface.co`). So we know the ruler is straight; we have
not yet used it to measure the current system.

**NDCG@10**, explained once: for each test question, we look at ASTFLOW's top 10
results. If the correct code is at position 1 the question scores 1.0; lower positions
score less; not in the top 10 scores 0. NDCG@10 is the average over all 3,765 questions.
A score of 0.09 roughly means "the correct answer is usually not near the top."

---

## 2. Can We Trust This Number?

**Not yet — there is no trusted number.** Here is what *is* established:

- **The measuring tool is trustworthy.** Golden tests with hand-checkable answers pass,
  and on 1,000 randomized questions (including questions where search returned
  nothing) ASTFLOW's own scorer, `pytrec_eval` (what the official MTEB benchmark uses),
  `ir_measures`, a plain reference implementation, and NIST `trec_eval` 10.0-rc3 all
  agree — to 10 decimal places, or to trec_eval's 4-digit printed precision.
- **The old numbers in the repository are not trustworthy as "current".** Some were
  real measurements of *older code*; some have no evidence at all. See
  [Metric Claims We Found](#metric-claims-we-found).
- **Second-machine reproduction:** not done yet. It is the next step (section 10).

---

## 3. Current Retrieval System

In plain English:

```
A developer asks a question
        ↓
ASTFLOW finds code that shares WORDS with the question          (BM25)
        +
ASTFLOW finds code whose MEANING is similar to the question     (Dense / MiniLM)
        ↓
The two ranked lists are merged into one                        (Hybrid / RRF)
        ↓
The top results are returned
```

There is **no reranking step.** A "Reranked" mode appears in some old results, but the
code for a reranker is switched off (`CROSS_ENCODER_AVAILABLE = False` is written
directly into `backend/app/retrieval/search.py`), and the benchmark's "reranked" mode
simply runs Hybrid again. **Any "Reranked" number is a copy of the Hybrid number.**

Technical details (read from the code, not from older documents):

| Part | What the code actually does |
|---|---|
| BM25 (word matching) | `rank_bm25` BM25Okapi, **k1 = 1.6, b = 0.75**, positive-IDF variant `log(1 + (N - df + 0.5)/(df + 0.5))`; splits camelCase/snake_case; removes English stopwords plus `def else if import int list return str` |
| "BM25F" title field | Adds 2.0 × IDF for query words found in the document title. On this benchmark the "title" is the document ID (e.g. `d123`), so it has almost no effect |
| Dense (meaning) | `sentence-transformers/all-MiniLM-L6-v2`, 384 numbers per text, normalized; similarity = dot product; documents below similarity 0.05 are dropped; model reads at most 256 word-pieces, so ~23.5% of documents are cut off |
| Official benchmark representation | one vector per whole document (no windows) — `benchmark/run_mteb.py` |
| Hybrid | Reciprocal Rank Fusion, k = 60, weights 1.0 / 1.0, over the union of both lists |
| Candidate depth | **1,000 per list on the benchmark** (`size = max(500, limit=1000)`); 500 in the product app, which also turns on name/test boosts the benchmark turns off. Corrected 2026-09-23: an earlier version of this file said the benchmark used 500 |
| Ties | ASTFLOW breaks equal scores by document ID ascending — **MTEB re-sorts by ID descending** (see Lessons) |

---

## 4. Current Main Problem

**We cannot yet say where the system fails, because we have not yet measured it.** The
tool that will tell us (`benchmark/verify_retrieval.py`) now computes, for every
question, where the first correct answer appears (rank 1, 2–10, 11–50, … or not found)
and the "oracle ceiling" described below. It needs one real run.

**A useful fact about this benchmark.** Every question has exactly one correct document.
So a *perfect* reranker, limited to the top k results, can do no better than moving that
one document to position 1 — which means its score equals the share of questions whose
correct document is somewhere in the top k (called **Hit@k** or Recall@k). It also means
**NDCG@10 can never exceed Hit@10**: to reach 0.20, the correct document must be in the
top 10 for at least 753 of the 3,765 questions.

What the *old* official Hybrid run suggests (2026-09-21, older code — a hint, not a
trusted number):

| Candidates a perfect reranker could reorder | Best possible NDCG@10 |
|---|---:|
| top 20 | 0.176 — **below** the 0.20 target |
| top 100 | 0.298 |
| top 1000 | 0.648 |

If today's code looks similar, reranking only the top 20 can *never* reach 0.20, and
reranking the top 100 could in principle, but only if it lifts the correct document to
the top for about two-thirds of the questions where it is present. For about 70% of
questions the correct document was not in the top 100 at all. Baseline-v1 will replace
these hints with measured numbers; the rule for choosing what to fix was written down
*before* that data arrives (section 10).

---

## 5. Trusted Baseline

**None yet.** No `retrieval-trusted-baseline-v1` Git tag exists, on purpose. It will be
created only after section 10 is done.

---

## 6. Experiment History

No experiment has been run under the new rules (frozen run → independent scoring →
keep/reject). Earlier work is listed in `benchmark/EXPERIMENTS.md` as **pre-protocol
history** so it is not lost, but none of it counts as verified progress.

---

## 7. Failed Ideas

| Idea | What happened | Don't repeat because |
|---|---|---|
| Windowed dense embeddings loaded from `apps_fixed.npy` (direct adapter) | Dense collapsed to 0.0010: vectors were matched to the wrong documents because two scripts sorted documents differently | Fixed in code (vectors now matched by ID), but windowing itself has **never been measured correctly** — it is untested, not proven bad |
| Using "Reranked" as a separate result | It is Hybrid under another name | Only report a reranker once real reranking code runs |

---

## 8. Major Things We Learned

1. **A result file is not evidence unless we know which code produced it.** The
   `0.089` Hybrid result was produced on 2026-09-21 15:36 UTC by code that was never
   committed exactly (it sits between commits `589e712` and `39cfe20`).
2. **Human-edited summaries drift from machine outputs.** `benchmark/results/apps.md`
   says "3,765 queries" while its own companion file `apps.json` holds a different,
   32-query run.
3. **"0.0894" does not appear anywhere in the repository.** The only "0.0707" in the
   repository is the *MRR* of a *32-query* Dense run, not a full NDCG@10.
4. **Tie-breaking matters.** Hybrid (RRF) creates exact score ties. ASTFLOW orders ties
   by document ID ascending; MTEB and trec_eval re-sort them by ID descending. So the
   official MTEB number scores a slightly different order than ASTFLOW shows users. The
   new tool freezes ASTFLOW's own order, so every scorer sees the same thing.
5. **The "missing question" trap does not affect our old official runs.** MTEB only
   drops a question if it is absent from the results; `run_mteb.py` always includes
   every question. (A golden test disproved our first guess — that is the system
   working as intended.)
6. **ASTFLOW's own scorer is correct for this benchmark.** MTEB's own published
   statistics for AppsRetrieval (shipped inside the `mteb` package, independent of our
   code) say every question has **exactly one** correct document: 8,765 documents,
   3,765 questions, 3,765 relevant pairs. With one correct document per question the
   gain formula cancels out of NDCG, so ASTFLOW's formula (2^g − 1) and trec_eval's (g)
   give identical results. Its "MRR", however, has no cutoff, so it is not MTEB's MRR@10.
   The verifier now refuses to run if a downloaded dataset does not match these counts.
7. **The development/confirmation split is genuine** (1,859 + 1,906 questions, no
   overlap, fixed seed). But the "official test" is both halves together, so the old
   "tuned" full-test numbers were partly measured on questions used for tuning.
8. **Hybrid can be rebuilt exactly from the BM25 and Dense result lists.** With boosts
   off (as on the benchmark) Hybrid's score is only `1/(60 + BM25 rank) + 1/(60 + Dense rank)`.
   So fusion ideas can be tested offline from frozen runs, with no model and no download.
9. **The reranker code would not work even if switched on**: its model name
   (`mxbai-rerank-base-v2`) lacks the `mixedbread-ai/` prefix, every error is silently
   ignored, and it would reload the model for each question.

---

## 9. What We Are Doing Right Now

**Active step (not an experiment yet): Trusted Baseline V1.** The team reports that
the benchmark machine is running `python -m benchmark.verify_retrieval --split all --tag baseline-v1`
now. This analysis machine has no Hugging Face access and does not need it: it will
analyse the results from committed files only (`benchmark/analyze_baseline.py`). No
retrieval code may change while baseline-v1 is running.

---

## 10. What Happens Next

**Step 1 — benchmark machine, when baseline-v1 finishes:**

```bash
python -m benchmark.analyze_baseline pack --tag baseline-v1   # ~8 MB per mode, checksum-verified
git add benchmark/verification/manifest-baseline-v1.json benchmark/verification/apps.qrels \
        benchmark/verification/per-query-baseline-v1-*.tsv benchmark/verification/ranks/
git commit -m "benchmark: baseline-v1 artifacts" && git push
```

**Step 2 — any machine, no Hugging Face needed:**

```bash
git pull && python -m benchmark.analyze_baseline analyze --tag baseline-v1
```

This rebuilds each frozen run byte-for-byte and checks it against the manifest checksum,
re-scores it with every evaluator (an independent second-machine check), measures where
the correct document sits for every question, computes perfect-reranker ceilings,
checks that Hybrid is exactly the merge of the frozen BM25 and Dense lists, and applies
the pre-registered bottleneck rule. Report: `benchmark/results/retrieval_forensics-baseline-v1.md`.

**Step 3:** if every trust check passes, record Trusted Baseline V1 here, tag
`retrieval-trusted-baseline-v1`, and start the ONE experiment from `benchmark/EXPERIMENTS.md`
whose entry condition the data meets.

For reference, the original setup on a laptop that **can** reach huggingface.co was:

```bash
git pull && git checkout main
pip install -e ".[semantic,benchmark]" && pip install -r benchmark/requirements-mteb.txt ir-measures
python -m benchmark.mteb_appretrieval --download --download-only    # exports the PINNED dataset revision once
python -m benchmark.verify_retrieval --self-test                   # must print "agreement: PASS"
python -m benchmark.verify_retrieval --split all --tag baseline-v1 # ~1–3 h on CPU
```

Optional but recommended: build NIST trec_eval (`git clone https://github.com/usnistgov/trec_eval && make`)
and add `--trec-eval path/to/trec_eval`.

Then **commit** `benchmark/verification/` (manifest and per-query files; the large run files are
gitignored but their SHA-256 is in the manifest) so another machine can compare checksums. If the manifest's `corpus_sha256_run_mteb_formula` equals
`ce25930a1a449256589e9e064e5568de35e2397ce32d963739c22c126c115021`, the corpus is identical
to the one behind the historical official runs.

---

## Metric Claims We Found

Status meanings: **MACHINE-GENERATED** = written by a program, not a person;
**REPRODUCED** = regenerated by us and matched; **CLAIMED** = only written in prose;
**STALE** = measures older code than today's.

| Claimed score | Mode | Where it appears | Machine evidence? | Which code produced it | Status |
|---|---|---|---|---|---|
| NDCG@10 **0.06104** (MRR@10 .0522, R@10 .0898, R@100 .2255) | BM25 | README, `benchmark/results/mteb-bm25/` | Yes — official MTEB 2.21 scorer, all 3,765 queries, dataset rev `f22508f`, run 2026-09-19 | Older code (k1 = 1.5, no code stopwords) | MACHINE-GENERATED, STALE, NOT REPRODUCED |
| NDCG@10 **0.08815** (MRR@10 .0724, R@10 .1394, R@100 .2962) | Hybrid | README, `benchmark/results/mteb-hybrid/` | Yes — same scorer, run 2026-09-20 | Same older code | MACHINE-GENERATED, STALE, NOT REPRODUCED |
| NDCG@10 **0.089** (MRR@10 .0734, R@10 .1397, R@100 .2977) | Hybrid "tuned" | `docs/audit/RETRIEVAL-EXPERIMENTS.md`, `benchmark/results/mteb/` | Yes — same scorer, run 2026-09-21 | Uncommitted code between `589e712` and `39cfe20` | MACHINE-GENERATED, PROVENANCE UNRESOLVED |
| NDCG@10 **0.06312** | BM25 "tuned" | `docs/audit/RETRIEVAL-EXPERIMENTS.md` | **No artifact found** | Unknown | CLAIMED ONLY |
| **0.0631 / 0.0010 / 0.0322 / 0.0322** (3,765 q) | BM25 / Dense / Hybrid / "Reranked" | `benchmark/results/apps.md` | **No** — `apps.json` beside it is a different 32-query run | Windowed-cache code with the ID-alignment bug | CLAIMED; Dense & Hybrid INVALID (known bug); "Reranked" = Hybrid |
| **0.0904 / 0.0625 / 0.0916** (32 q) | BM25 / Dense / Hybrid | `benchmark/results/apps.json` | Yes, per-query rankings | Initial-commit code, ASTFLOW scorer | MACHINE-GENERATED, 32-QUERY SUBSET, STALE |
| **0.1184** (100 q) | Hybrid | `docs/audit/CURRENT-RETRIEVAL-CONFIG.md` | **No** | Unknown | CLAIMED ONLY, SUBSET |
| **0.0707** Dense / **0.0894** Hybrid (full) | Dense / Hybrid | Team discussion and recent AI prompts | **None in this repository.** "0.0894" appears nowhere | Unknown — if produced on another laptop, its run files were never committed | UNRESOLVED |

Nothing in this table is **REPRODUCED** yet.

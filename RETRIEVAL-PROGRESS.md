# ASTFLOW Retrieval Progress

> **Read this file first.** It is the only document that describes the *current* state of
> ASTFLOW's search quality. Older files under `docs/audit/` are historical records.
> Last updated: 2026-09-23.

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
| Candidate depth | 500 per list by default; benchmark asks for 1,000 |
| Ties | ASTFLOW breaks equal scores by document ID ascending — **MTEB re-sorts by ID descending** (see Lessons) |

---

## 4. Current Main Problem

**We cannot yet say where the system fails, because we have not yet measured it.** The
tool that will tell us (`benchmark/verify_retrieval.py`) now computes, for every
question, where the first correct answer appears (rank 1, 2–10, 11–50, … or not found)
and the "oracle ceiling" described below. It needs one real run.

What the *old* official results suggest (older code, so treat as a hint only): in the
2026-09-21 Hybrid run, a correct answer appeared in the top 10 for about **14%** of
questions and in the top 100 for about **30%** (Recall@10 = 0.140, Recall@100 = 0.298).
If that still holds, for about 70% of questions the correct code is **not even in the
first 100 results** — which would mean *finding* candidates, not *ordering* them, is the
bigger problem, and a reranker alone could not reach 0.20. This must be confirmed on
current code before anyone acts on it.

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

---

## 9. What We Are Doing Right Now

**Active step (not an experiment yet): establish Trusted Baseline V1** by running the
verification command on a machine that can download the model and data.

---

## 10. What Happens Next

On a laptop that **can** reach huggingface.co (the team's Windows machine did), run:

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

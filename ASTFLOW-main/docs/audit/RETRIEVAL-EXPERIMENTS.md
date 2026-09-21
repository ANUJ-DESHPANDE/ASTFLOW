# Retrieval experiment log

Format per the continuation prompt's section 24. This file is a scaffold: the tooling to
produce real entries was written and unit-tested this session, but no entries exist yet
because this session's cloud sandbox cannot reach huggingface.co (confirmed via the proxy
status endpoint: `gateway answered 403 to CONNECT` for `huggingface.co:443`) and therefore
cannot download the AppsRetrieval dataset. Do not fill this file in with invented numbers —
append real rows only after actually running the scripts below.

## How to produce a real entry

From the project root, with `.eval-venv` set up (`README.md`'s evaluation-environment section):

```sh
.eval-venv/bin/python -m benchmark.build_dev_split      # once; writes benchmark/dev_split.json
.eval-venv/bin/python -m benchmark.analyze_corpus        # token-length + stopword-candidate evidence
.eval-venv/bin/python -m benchmark.tune_bm25             # k1/b grid search, dev queries only
.eval-venv/bin/python -m benchmark.tune_bm25 --confirm --k1 <best> --b <best>   # once, before adopting
```

`tune_bm25.py` appends every run's results (grid search, confirmation, and any
`--stopwords-file` ablation) to `benchmark/results/bm25-tuning-log.json` automatically, with
git commit, timestamp, dataset revision, and dev fraction recorded per run — that file is the
authoritative machine-readable log; this document is the human-readable summary of what to
keep or reject, and should be updated by hand as real runs come back.

**Every script's own docstring says explicitly that it has not been executed against the
real dataset in this session.** Treat the first real run as a first run: read its output
for sanity (does dev BM25 NDCG@10 roughly track the committed official full-test BM25
NDCG@10 of 0.06104? Wildly different would suggest a wiring bug, not a real finding) before
trusting any config comparison from it.

## Experiment table (append real rows only)

| ID | Date | Git commit | Split (dev/confirmation/official) | Query/corpus count | Model/config | BM25 k1/b | NDCG@10 | MRR | Recall@10 | Latency | Decision |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---|
| — | — | — | — | — | — | — | — | — | — | — | No experiments run yet; see "How to produce a real entry" above |

## Ablation table (append real rows only)

| Configuration | NDCG@10 | MRR | Recall@10 | Latency | vs. baseline |
|---|---:|---:|---:|---:|---|
| BM25 baseline (k1=1.5, b=0.75, untuned rank_bm25 defaults) | — | — | — | — | — |
| BM25 tuned (k1/b from dev grid search) | — | — | — | — | — |
| BM25F (field-weighted name/imports/comments/body) | — | — | — | — | Not yet implemented as a testable config — see below |
| BM25 + code stopwords | — | — | — | — | — |
| Dense (MiniLM) baseline | 0.08815 (hybrid, not dense-only) | — | — | — | Dense-only NDCG@10 not separately measured against official AppsRetrieval; only hybrid is |
| Hybrid (current RRF, k=60) | 0.08815 | 0.0724 (@10) / 0.078815 (@1000) | — | ~263ms/query median | Historical official run, `benchmark/results/mteb-hybrid/` |
| Hybrid, tuned fusion | — | — | — | — | — |
| Reranker | — | — | — | — | Not attempted — candidate recall (are relevant docs even in top-50/100?) has not been measured, which the prompt says must come first |
| Agent refinement | ~0.0017 NDCG@10 delta, ~0 MRR delta (local 16-query fixture only) | — | — | Higher latency | `docs/audit/ablations.json`; not measured on AppsRetrieval itself |

## Known-not-yet-buildable: BM25F field weighting

`tune_bm25.py` currently ablates k1/b and an optional flat stopword list, both of which
reuse `Retriever`'s existing tokenizer/BM25 machinery unchanged. Field weighting
(`score = w_name*BM25(name) + w_imports*BM25(imports) + ...`) needs a different scoring
path — computing separate BM25 postings per field and combining them — which does not
exist in `Retriever` yet and was not added this session, per the prompt's explicit
instruction not to start by implementing BM25F before dev-split evidence justifies it.
If `analyze_corpus.py` and a first `tune_bm25.py` run suggest it's worth trying, that is
the next piece of tooling to write, informed by real numbers rather than guessed ahead of them.

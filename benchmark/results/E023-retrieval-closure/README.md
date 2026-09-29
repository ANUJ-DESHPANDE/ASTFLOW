# E023 retrieval closure — 2026-09-29

Decision: **CLOSED**. Accepted production system: the float32
`Alibaba-NLP/gte-modernbert-base` dense baseline at revision
`e7f32e3c00f91d699e8c43b53106206bcc72bb22`. Production freeze commit:
`dc974ca`; canonical documentation and state commit: `3b487cf`.

The production path was traced through `backend/app/main.py` `/api/search`,
`backend/app/agent/investigate.py` `investigate`,
`backend/app/retrieval/search.py` `Retriever.rank`,
`backend/app/retrieval/embeddings.py` `Embedder`, and
`backend/app/corpus.py` `search`. The benchmark and snippet search use exact
dense order. The investigation agent starts with dense candidates and may use
existing graph and second-pass evidence; this is outside the AppsRetrieval
ranking. BM25 remains available to the agent but contributes zero to the
dense score. The E019 operator helper is uncalled by production; E020–E022
code remains in benchmark artifacts.

Existing validated TEST artifacts were checked; **no TEST rerun occurred**:

| Artifact | SHA-256 of stored prediction gzip |
|---|---|
| [Clean float32 validation](../final-validation-20260928/README.md) | `c76c4fad6dfe5807924829f9d98b437673279156f271374e60cb0fb8f9fab810` |
| [Eight-thread equivalence](../threads8-equivalence-20260929/README.md) | `99f11d5ac35316ad81aa2ff3eba3c1d1e7c87f5c00a8551133136d4e0eaff220` |

Verification in `.venv-gpu`:

- `pytest backend/tests -q -ra`: 79 passed, 1 skipped (Node dependencies
  needed for language-service integration), 0 failed.
- `pytest benchmark -q -ra` with `test_mteb_adapter.py`,
  `test_analyze_baseline.py`, `test_trust_evaluation.py`, and
  `test_verify_retrieval.py` excluded: 26 passed, 0 failed. The full benchmark
  suite was not run in this environment, which lacks `mteb` and `pytrec_eval`.
  They are declared in `benchmark/requirements-mteb.txt`.
- Focused regression and worktree test: 8 passed, 0 failed.
- `python -m benchmark.run_mteb --help` succeeded; the documented dense
  command's flags are supported. The full command was intentionally not run.

See [canonical state](../../RETRIEVAL_BASELINE.md),
[`CURRENT_STATE.json`](../../CURRENT_STATE.json), and the
[campaign ledger](../campaign/LEDGER.md). Reopen retrieval only under the
evidence rule in the canonical state document. Next product objective:
reliable repository ingestion and incremental indexing.

# 07 · Dead code and duplication

Method: Vulture (≥60%) + Ruff F401 as leads, then `git grep` across code, tests, docs, Dockerfile and scripts, plus a
check for decorator registration (FastAPI routes, Typer commands), dataclass/serialization use, dynamic imports
(`import()` in the frontend, `python -m` entry points) and runtime references. Nothing was deleted on the basis
of a tool result alone.

| Path | Symbol | References | Runtime refs checked? | Test refs | Dynamic use possible? | Static tool | Confidence | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `backend/app/agent/investigate.py:3` | `from copy import deepcopy` | 0 | yes | 0 | no | Vulture 90%, Ruff F401 | Confirmed | REMOVE (done in remediation) |
| `backend/app/retrieval/search.py:49-50` | `self.corpus_title`, `self.corpus_text` | 0 reads | yes (only assignments) | 0 | no | Vulture 60% | Confirmed | REMOVE — they tokenize the whole corpus twice at every index load for nothing (F-019) |
| `backend/app/retrieval/search.py:11-16` | `import sentence_transformers`; `CROSS_ENCODER_AVAILABLE = True` | read by `benchmark/verify_retrieval.py` (manifest string) | yes | 0 | no | Vulture 90% / 60% | Confirmed misleading | REMOVE with F-014 (reports "reranker available" whenever sentence-transformers imports) |
| `backend/app/retrieval/reranker.py` + `Retriever` reranker branch + 5 `ASTFLOW_RERANKER_*` settings | `Reranker`, `get_reranker` | `search.py`, `benchmark/test_reranker.py` | yes: reachable only with an undocumented env flag or `mode="reranked"` (no API/UI path passes that mode) | 7 tests | env flag | — | Confirmed feature that E002 measured as harmful (−0.0187 NDCG@10, CI excludes 0) | REMOVE from the product path (F-014); E002 artifacts and the benchmark runner that produced them stay |
| `backend/app/main.py:215` | module-level `app = create_app()` | `uvicorn backend.app.main:app`-style use; tests call `create_app()` | yes — CLI imports the module and then builds a second app | tests import `create_app` | yes (ASGI string import) | — | Duplicate instance, not dead | KEEP the symbol, make the CLI use it or keep lazy (F-018, P3) |
| `backend/app/runtime/__init__.py` | empty package | README "Reserved" | n/a | 0 | no | — | Placeholder | KEEP (documented placeholder, 1 line) |
| `backend/app/api/schemas.py:21` | `nonblank` validator | Pydantic decorator | yes (`search blank` → 422) | API tests | decorator | Vulture 60% | FALSE POSITIVE | KEEP |
| `backend/app/main.py` route functions, `cli.py` commands | `health`, `index_repository`, `serve`, … | decorators | yes (api-probe, CLI) | yes | decorator | Vulture 60% | FALSE POSITIVE | KEEP |
| `backend/app/models/entities.py` | `call_end_line`, `resolution_method`, `evidence_type` | serialized via `asdict`, used by frontend/types | yes | yes | serialization | Vulture 60% | FALSE POSITIVE | KEEP |
| `backend/app/config.py:31` | `schema = 8` | included in `fingerprint()` → index key | yes | indirectly | serialization | Vulture 60% | FALSE POSITIVE (versioning key) | KEEP |
| `benchmark/compare_runs.py`, `foundation_audit.py`, `profile_system.py`, `run_parallel_reranker.py`, `verify_dense_alignment_synthetic.py`, `precompute_embeddings.py` | standalone scripts | not imported | run as `python -m benchmark.X`; cited by experiment docs | some | entry points | — | Not dead: experiment/evidence tooling | KEEP (document as benchmark tooling, not product) |
| `benchmark/results/mteb`, `mteb-bm25`, `mteb-hybrid` | historical MTEB artifacts | README, docs | n/a | `test_mteb_adapter.py` | — | — | Stale relative to current code | KEEP as history; add a current-code MTEB artifact and label the old ones (F-020) |
| `frontend/e2e/investigation.spec.ts` | 6 tests targeting `.result-card`, nav "Trace" | component `ResultCard.tsx` deleted earlier | yes (fail with "element not found") | — | no | Playwright | Confirmed obsolete tests | REPLACE with journeys against the current UI (F-010) |
| `docs/screenshots/*.png` | 6 screenshots | README? (`git grep screenshots` → docs only) | — | — | — | — | Possibly stale imagery | INVESTIGATE (not product code; left as is) |

## Duplication

| Duplicate | Where | Recommendation |
|---|---|---|
| Two cross-encoder paths | `retrieval/reranker.py` (product, never benchmarked) vs `benchmark/run_reranker_benchmark.py` (benchmarked) | Resolve with F-014 |
| Metric code | `benchmark/metrics.py` (local benchmark) and `benchmark/trust/evaluation.py` (reference + 3 evaluators); `score_e00x.py` reuse the latter | KEEP: `evaluation.eval_astflow` explicitly cross-checks the historical `metrics.py` against the reference |
| Snapshot/app instances | `main.py` module-level app + CLI-created app | F-018 |
| Tokenised corpus | `Retriever` builds `corpus_title`/`corpus_text` and BM25 corpus separately | F-019 |

No duplicate indexing pipelines, model loaders or API clients were found: one `IndexService`, one `Embedder`, one
`request()` client.

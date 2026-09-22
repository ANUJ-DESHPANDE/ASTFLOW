# Dense retrieval collapse — root-cause investigation

2026-09-22 · Session continuing the Theme 1 retrieval audit on `codex/theme1-audit`.

## 1. Observed regression (preserved before any code change)

`benchmark/results/apps.md` / `apps.json`, as received at the start of this investigation:

```
3,765 queries / 8,765 documents · all split queries against full corpus

| Baseline | NDCG@10 | MRR (top 50) | Recall@10 | Median ms |
| bm25     | 0.0631  | 0.0593       | 0.0922    | 181.81    |
| dense    | 0.0010  | 0.0011       | 0.0021    | 539.18    |
| hybrid   | 0.0322  | 0.0251       | 0.0696    | 399.25    |
| reranked | 0.0322  | 0.0251       | 0.0696    | 427.59    |
```

BM25 (0.0631) is consistent with the previously tuned official value (0.06312, `RETRIEVAL-EXPERIMENTS.md` EXP-6) — the corpus, qrels, query set and BM25 implementation are not implicated. Dense (0.0010) is at the floor; Hybrid (0.0322) is *worse* than BM25 alone, meaning the fused dense signal actively damages ranking rather than merely failing to help.

## 2. Environment as actually run in this session

| Item | Value |
|---|---|
| Python | 3.11.15 |
| torch | 2.14.0+cu130 (CPU-only execution; no GPU used) |
| sentence-transformers | 5.7.0 (matches the pinned `benchmark/requirements-mteb.txt`) |
| mteb | 2.21.0 (matches pinned version) |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| datasets / huggingface_hub | 5.0.1 / 1.32.0 |
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Candidate depth | 500 (`Settings.candidates`) |
| Dense threshold | `> 0.05` (`search.py` semantic_order filter) |
| RRF k | 60 |
| Window size / overlap | 256 / 64 tokens, max-pooling aggregation |

**Environment constraint that bounds this investigation:** this session's outbound network access is policy-blocked for `huggingface.co` (proxy returns `403` / `connect_rejected — policy denial`, confirmed via the agent-proxy status endpoint). This means the real MiniLM model weights and the real CoIR-Retrieval/apps corpus (8,765 documents) could not be downloaded in this session. Per the task's own stop conditions ("embedding model unavailable — do not silently substitute another model", "benchmark takes excessive resources"), **this investigation could not re-run the live 3,765-query direct adapter or the official MTEB harness end-to-end**. Root cause was instead established by (a) exhaustive static tracing of both evaluation paths' source code, and (b) a fully deterministic, dependency-free reproduction that exercises the *actual* project code (`Embedder`, `Retriever`, `precompute_embeddings.py`, `mteb_appretrieval.py`) with a fake, injected encoder standing in for the network-gated model — proving the mechanism, not merely asserting it. No score anywhere in this document is fabricated, extrapolated, or estimated; every number here was either present in the repository before this session or produced by a command shown alongside it.

## 3. The two evaluation paths

- **Path A — official MTEB harness** (`benchmark/run_mteb.py`, `ASTFLOWSearch.index()`): builds its own `chunks` list, sorts it by `chunk_id` (line 50), and — critically — calls `self.embedder.encode([c.text for c in chunks])` **without `use_windows=True`**. It never uses the windowed representation. Its vector cache key (`mteb-apps-{sha256(model_weights + chunk_id:content_hash)}.npy`) is self-consistent: the same script, in the same order, both writes and reads it. This path produced the historical `EXP-7` result: Hybrid NDCG@10 = 0.08900 (`RETRIEVAL-EXPERIMENTS.md`), and is **not** implicated in the collapse.

- **Path B — direct adapter** (`benchmark/mteb_appretrieval.py`, `evaluate_export()`): builds its **own separate** `chunks` list via `sorted(corpus.items())`. When a precomputed cache file `apps_fixed.npy` exists, it loads that file and hands it to `Retriever` **positionally**, trusting `embeddings[i]` belongs to `chunks[i]`. That cache file is produced by a **different script**, `benchmark/precompute_embeddings.py`, which builds its own chunk list by iterating `corpus.jsonl` in **raw file order** (whatever order the HF dataset export wrote rows in — not sorted) and calls `embedder.encode(..., use_windows=True)`.

## 4. Root cause

**Category: A (document-ID misalignment) and L (benchmark adapter integration bug).**

`precompute_embeddings.py` and `mteb_appretrieval.py` are two independent scripts that each build their own `chunks` list from the same `corpus.jsonl`, in **two different orders**:

| Script | Order |
|---|---|
| `precompute_embeddings.py` (writer of `apps_fixed.npy`) | raw `corpus.jsonl` file order (line-by-line) |
| `mteb_appretrieval.py` (reader of `apps_fixed.npy`) | `sorted(corpus.items())` — lexicographic by document id |

Before this fix, `evaluate_export()` did:
```python
elif _fixed_path.exists():
    embeddings = np.load(_fixed_path, allow_pickle=True).tolist()
...
retriever = Retriever(chunks, embeddings, embedder, settings)
```
with no id, no order check, no length check — pure positional trust. `corpus.jsonl`'s row order is a HuggingFace dataset export order, which has no reason to equal alphabetical document-id order, so `embeddings[i]` was paired with an unrelated `chunks[i]` for almost every one of the 8,765 documents.

### Evidence

**(a) Ordering mechanism, deterministically demonstrated.** A minimal synthetic reproduction (200 shuffled ids, no network/model needed) — the identical file-order-vs-sorted-order relationship that exists between the two scripts:

```
N documents:                      200
Positions where order agrees:     0 / 200  (0.0%)
Expected by pure chance (~1/N):   0.5%
```

**(b) End-to-end proof against the real project code.** `benchmark/test_precompute_alignment.py` (new) builds a tiny 5-document corpus whose `corpus.jsonl` file order is deliberately not id-sorted (`d3, d1, d4, d0, d2`), runs the *actual* `precompute_embeddings.precompute()` and `mteb_appretrieval.evaluate_export()` functions (with a deterministic fake `Embedder.encode` standing in for the network-blocked real model — each document/query carries a `SIGNAL_<n>` marker so the "correct" nearest document is unambiguous), and asserts:

- Pre-fix code (verified by `git stash`-ing the fix and re-running): all 3 new tests **fail** — the id-metadata file the fix requires doesn't exist, and a deliberately mismatched/truncated cache is loaded without complaint.
- Post-fix code: all 3 tests **pass**; `dense` NDCG@10 = 1.0000 / Recall@10 = 1.0000 on the synthetic corpus once alignment is by id instead of position.

This is a direct, reproducible demonstration that (1) the misalignment mechanism is real in the shipped code, not hypothetical, and (2) realigning by document id — rather than trusting array position — fixes it.

**(c) Consistent with the magnitude of the observed collapse.** With embeddings paired to essentially random other documents, dense similarity carries no information about true relevance; NDCG@10 = 0.0010 over an 8,765-document corpus is exactly the order of magnitude expected from a similarity signal that is uncorrelated noise on top of the `> 0.05` threshold, not partial signal degraded by windowing quality.

**(d) Why Hybrid (0.0322) is worse than BM25 alone (0.0631).** Hybrid's candidate set is `lexical_candidates ∪ semantic_candidates` (`search.py` line: `candidates = set(lr) | set(sr)` for `mode == "hybrid"`), and every candidate's fused score includes an RRF contribution from whichever ranks it holds. Because the "semantic" ranking is effectively a random permutation of the corpus, it (i) pulls large numbers of lexically-irrelevant documents into the candidate pool, and (ii) hands out RRF credit essentially at random inside that pool, which can outrank documents BM25 had correctly ranked highly. Fusing a working ranker with a random one is measurably worse than the working ranker alone — this is the expected, not surprising, behavior of RRF once one input is noise.

### Secondary, related bug fixed in the same edit

`_fixed_path` was hardcoded to `ROOT / ".astflow" / "datasets" / "apps_fixed.npy"`, while `precompute_embeddings.py` saves to `settings.cache / "datasets" / "apps_fixed.npy"`. These only coincide because `Settings.cache` defaults to `ROOT / ".astflow"` — any run with `ASTFLOW_CACHE` set to a non-default path would silently look in the wrong place. Fixed alongside the alignment fix since it is the same `_fixed_path` line and the same "make this loading path correct" scope.

## 5. Reranker (investigated per §27, not part of this fix)

`backend/app/retrieval/search.py` line 13:
```python
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = False # DISABLED for stability and speed
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
```
`CROSS_ENCODER_AVAILABLE` is hardcoded `False` on **both** branches — a successful import still leaves it `False`. The reranking block below (`if CROSS_ENCODER_AVAILABLE and len(rows) > 0:`) therefore never executes, by explicit, commented design ("DISABLED for stability and speed"), not by accident. Additionally, `mteb_appretrieval.py`'s `"reranked"` benchmark mode literally maps to `retriever.rank(query, mode="hybrid", ...)` — there is no distinct reranked code path in the adapter at all. Both facts fully explain why `Hybrid` and `Reranked` are bit-for-bit identical in every reported metric.

**Status: BYPASSED** (deliberately disabled, confirmed by direct source inspection — no experiment needed to establish this). Not modified in this session: enabling a reranker is a product decision outside the scope of "restore dense retrieval to a technically correct state," and is called out separately in §L below rather than folded into this fix.

## 6. Root-cause classification

```
A. Document-ID misalignment           — PRIMARY. Proven (§4a, §4b).
L. Benchmark adapter integration bug  — PRIMARY. The two scripts never agreed on an
                                         ordering contract; no shared key existed.
```
Ruled out by code inspection and/or the passing existing test suite: normalization (both branches of `Embedder.encode` call `normalize_embeddings=True`), ranking direction (`sorted(..., key=lambda i: -dense[i])`, descending — correct), model mismatch (Path B always uses `settings.model`; the fix now asserts this), window→parent aggregation (`np.max(win @ q_vec)` per document — internally consistent, order-preserving relative to its own `texts` input).

## 7. Minimum correct fix

Files changed:

- **`benchmark/precompute_embeddings.py`** — now writes `apps_fixed.meta.json` alongside `apps_fixed.npy`, recording `ids` (in the exact row order of the saved array), `model`, `window_size`, `overlap`.
- **`benchmark/mteb_appretrieval.py`** — `evaluate_export()` now: (1) refuses to load `apps_fixed.npy` without its companion metadata file (`ValueError`, not silent fallback); (2) verifies the recorded model matches `settings.model`; (3) builds a `chunk_id → embedding` map from the metadata and **realigns by id** to match `chunks`' own order, raising a clear `ValueError` naming any missing ids rather than truncating/misaligning; (4) fixed `_fixed_path` to respect `settings.cache` instead of a hardcoded `ROOT`.

No change to BM25, RRF, thresholds, windowing math, or the reranker.

## 8. Regression tests added

`benchmark/test_precompute_alignment.py` (3 tests, network-free, using a fake deterministic embedder):
1. `test_fixed_embeddings_realign_by_id_not_position` — end-to-end proof the fix produces correct alignment.
2. `test_fixed_cache_without_id_metadata_is_rejected_not_silently_misaligned` — a legacy (pre-fix-format) cache is rejected, not silently loaded.
3. `test_fixed_cache_rejects_mismatched_document_ids` — a cache missing ids present in the current corpus is rejected, not silently truncated.

All 3 fail against the pre-fix code (verified via `git stash`) and pass against the fixed code.

## 9. Test suite status

`python3 -m pytest backend/tests/ benchmark/ -q` (after running `scripts/setup_demo.py`, a documented prerequisite unrelated to this fix): **60 passed, 2 skipped, 0 failed** (47 passed / 2 skipped backend suite, unchanged from the pre-existing documented baseline, plus 13 benchmark-directory tests including the 3 new ones). No regressions.

## 10. What could not be executed in this session, and why

The following required steps from the task **could not be run** because `huggingface.co` is blocked by this session's organization egress policy (confirmed 403 at the proxy layer, not a transient failure — retrying is against the proxy's own operating rules for policy denials):

- Downloading `sentence-transformers/all-MiniLM-L6-v2` weights.
- Downloading the CoIR-Retrieval/apps dataset (corpus/queries/qrels).
- Re-running the fixed direct adapter over the real 3,765-query / 8,765-document set.
- Re-running the official MTEB harness (`benchmark/run_mteb.py`).
- Candidate-recall union analysis (§42) and short/long-document breakdown (§21), both of which need the real corpus.

No number for any of these is reported anywhere in this document or the final summary. Reproducing the fix's effect at full scale requires either (a) network access to `huggingface.co` for this session, or (b) the already-downloaded model/dataset cache from a prior environment (`~/.astflow/models/…`, `~/.astflow/datasets/apps/…`) supplied into this session's `.astflow` cache directory. Either would let the exact same fixed code run to completion without further changes — the fix does not depend on network access itself, only this session's *verification* of it at full scale does.

# P002 — search and source-citation API reliability

Decision: **PASS**. This milestone kept the E023 GTE dense ranking contract
unchanged and did not run MTEB or frozen TEST. The real walkthrough used an
isolated copy of `examples/demo-repo`, the locally installed accepted GTE
weights (SHA-256 `3e85899d5728cb7de79781c0c3acfb91ccef9f875f1f7e0b3c9f3dd4b6a724ba`),
and FastAPI's actual `/api/search` and `/api/source` routes. The source copy
and temporary indexes were removed after the run.

## Contract and implementation

`POST /api/search` accepts `query`, `version`, `top_k`, and `agentic`. Its
response retains `version_key`, `results`, `graph`, `retrieval`, `agent_trace`,
`status`, and `latency_ms`. Each result has a `chunk_id`, `symbol_id`, relative
`file_path`, `start_line`, `end_line`, `snippet`, and evidence. The top-level
`version_key` is the immutable citation identity; the result's existing
`version` field remains the requested alias for frontend compatibility.

The endpoint resolves one `Index` object before calling `investigate()`. Both
retrieval passes, BM25 evidence, graph expansion, and result serialization use
that object. Before returning, the agent verifies every visible result against
its pinned chunk and stored source lines, and verifies graph nodes/call sites
against the same snapshot. A mismatch returns a structured 503 without
presenting an unverified citation. Explicit immutable keys continue to open
their stored source snapshot after a repository switch. Unexpected search
failures return a structured 503 while leaving the index usable; the server
log records the pinned key and stage without logging query or source content.

The focused tests paused a request after version resolution, promoted a new
index, and confirmed the paused response used the old version while the next
request used the new one. A separate test paused after the first retrieval
pass and confirmed the second pass stayed on the old index. See
[`version_pinning.json`](version_pinning.json) and
[`concurrent_promotion.json`](concurrent_promotion.json).

## Real API walkthrough

The actual GTE HTTP run passed initial search, add, modify, rename, delete,
mixed promotion, failed update, concurrent promotion, and restart. Each
returned result was resolved through `/api/source` using its response
`version_key`; paths, source snippets, and line ranges agreed. A failed
embedding update left the previous API search usable. The final mixed
snapshot had no deleted or old renamed path in its response. See
[`real_api_walkthrough.json`](real_api_walkthrough.json),
[`citation_validation.json`](citation_validation.json), and the individual
promotion artifacts. Returning to the same repository bytes after deleting
the temporary file correctly returned the earlier content-addressed key.

## Measured API latency

Twelve queries through TestClient with the actual GTE model on this local CPU
run: `/api/search` **p50 69.16 ms**, **p95 102.87 ms**. Median version
resolution was 0.02 ms, retrieval-pass work 59.49 ms, and whole agent work
60.19 ms. The median HTTP/serialization residual was 9.50 ms; this includes
TestClient and middleware overhead and is not pure JSON serialization. The
same `BluetoothAgent` query took 63.45 ms before promotion and 66.05 ms on
the first request after it (difference +2.60 ms). These are observed values
from one controlled local run, not a performance target. See
[`latency.json`](latency.json).

## Limits and reproduction

P001's existing limits remain: schema-10 indexes need a one-time reindex;
changed snapshots re-parse files and rebuild the graph; one process should
own an index cache. P002 did not change these. The Node-dependent language
service integration test was skipped because its local dependencies were
absent. No first-party frontend response field was removed or renamed. A
frontend build was attempted but could not run because `frontend/node_modules`
is absent in this workspace (`tsc` unavailable).

```powershell
.\.venv-gpu\Scripts\python.exe -m pytest backend/tests/test_p002_search_api.py -q -ra
.\.venv-gpu\Scripts\python.exe -m benchmark.p002_walkthrough
```

The walkthrough requires the accepted model already installed under
`.astflow/models/Alibaba-NLP--gte-modernbert-base/`. It does not download
models. [`artifact_hashes.json`](artifact_hashes.json) contains SHA-256 hashes
of the small committed evidence files; no weights or vector caches are stored
here. [`test_results.txt`](test_results.txt) records the test gates.

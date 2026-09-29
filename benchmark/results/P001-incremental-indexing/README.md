# P001 — repository ingestion and incremental indexing

Decision: **PASS WITH DOCUMENTED LIMITATION**. Retrieval configuration and
ranking are unchanged. The product run used an isolated copy of the committed
11-file `examples/demo-repo` and the locally installed accepted GTE model.
It did not run MTEB or download a model. The original repository was not edited.

## What was verified

The indexer stores immutable snapshots under `.astflow/indexes/<version_key>`.
Each snapshot contains a manifest, SQLite metadata, and aligned dense vectors.
The registry changes only after the new snapshot has been saved and published;
searches continue to use the previous snapshot while an update is in progress.
Old snapshot keys remain addressable for pinned source citations. The embedding
cache uses exact indexed-text hashes and an identity including model revision,
precision, schema, and sequence limit. BM25 and graph structures are rebuilt
from the new logical corpus, so deleted and renamed files leave no stale
references.

The real GTE walkthrough passed fresh indexing, no-op, add, modify, rename,
delete, mixed mutations, restart, and a controlled embedding failure followed
by a successful retry. The automated fixture also compared the final logical
index and vectors with a fresh rebuild, checked search after mutations,
verified Git ignore rules and cache exclusion, and exercised concurrent search.
See [`real_repo_walkthrough.json`](real_repo_walkthrough.json),
[`rebuild_equivalence.json`](rebuild_equivalence.json), and
[`failure_recovery.json`](failure_recovery.json).

## Measured performance

| Operation | Wall time |
|---|---:|
| Initial full index, cold model | 18,570.10 ms |
| Full rebuild, model already loaded | 1,944.33 ms |
| No-op | 57.39 ms |
| One-file add | 180.74 ms |
| One-file modify | 183.54 ms |
| One-file rename | 186.91 ms |
| One-file delete | 72.01 ms |
| Mixed update | 250.60 ms |

The one-file modification took **0.0944×** the warm full rebuild time and
re-embedded **1 of 22 documents** (0.0455 of the final corpus). Times are one
local Windows CPU run, not a service-level latency guarantee. The cold full
run includes GTE model loading. [`performance.json`](performance.json) has
the machine-readable values and per-operation JSON files record file counts,
embedding reuse, and timings.

## Compatibility and limits

Index schema is now 11. Existing schema-10 indexes need an explicit reindex
because their cache records did not bind vectors to the full model revision.
The update path re-parses files and resolves the full graph on a changed
snapshot; only affected indexed text is sent to GTE. The HTTP index lock
rejects a second request in one application process, while the service lock
serializes direct calls. Separate server processes sharing one cache do not
have a cross-process write lock; run one ASTFLOW server per cache.

The locally configured TypeScript language-service integration was skipped by
the backend suite because Node dependencies were absent. The test suite
otherwise passed. See [`test_results.txt`](test_results.txt).

## Reproduce

```powershell
.\.venv-gpu\Scripts\python.exe -m pytest backend/tests -q -ra
.\.venv-gpu\Scripts\python.exe -m benchmark.p001_walkthrough
```

The walkthrough requires the accepted GTE model already installed at
`.astflow/models/Alibaba-NLP--gte-modernbert-base/`. It copies the model and
demo repository into a temporary directory and removes that directory after
the run. [`artifact_hashes.json`](artifact_hashes.json) records the small
evidence file hashes. No vectors or model weights are committed here.

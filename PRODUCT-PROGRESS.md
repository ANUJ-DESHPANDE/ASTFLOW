# ASTFLOW product progress

## P001 — repository ingestion and incremental indexing

**Decision:** PASS WITH DOCUMENTED LIMITATION. Implementation commit:
`f5d9f9a`; validation artifacts:
[`benchmark/results/P001-incremental-indexing/`](benchmark/results/P001-incremental-indexing/README.md).

**Goal:** keep the accepted GTE dense retrieval index synchronized with a
changing real repository while preserving the last usable snapshot on failure.
Retrieval ranking, document text, chunking, and embeddings are unchanged.

**Implementation:** working-tree discovery respects Git ignore rules and
skips the cache, symlinks, non-UTF-8 files, and over-limit sources. Schema-11
manifests include source hashes, model revision, operation counts, and timings.
No-op updates return without parsing or encoding. Changed snapshots reuse
embeddings for unchanged indexed text; path-dependent renames are reported and
processed as a safe delete plus add. New snapshot directories are published
before the registry points at them. Existing version keys remain readable
after promotion, including after restart. `/api/index` reports full,
incremental, or no-op behavior and rejects overlapping requests with HTTP 409.

**Tests and evidence:** 83 backend tests passed, one Node-dependent integration
test skipped; 26 available benchmark tests passed. A real GTE run on a copied
11-file demo repository passed the complete mutation and recovery walkthrough.
One-file modification took 183.54 ms versus 1,944.33 ms for a warm full
rebuild, with 1/22 documents re-embedded. The full measurements and recorded
checks are in the P001 artifact directory. MTEB/TEST was not rerun.

**Remaining limitations:** an existing schema-10 index requires a one-time
reindex. Changed snapshots re-parse files and re-resolve the graph, although
unchanged documents are not re-embedded. One cache must be served by one
ASTFLOW server process because the write lock is process-local.

**Next product milestone:** P002 — end-to-end search and source-citation API
reliability across an index promotion, including version-key continuity and
user-visible failure handling.

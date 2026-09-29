# ASTFLOW product progress

## P003 — Investigation agent, evidence grounding, and code-map correctness

**Decision:** PASS WITH DOCUMENTED LIMITATION. Implementation commit `6df2deb`. Validation artifacts:
[`benchmark/results/P003-agent-grounding/`](benchmark/results/P003-agent-grounding/README.md).
The P003 branch starts at `46324ca`; production GTE dense retrieval and the
closed retrieval campaign remain unchanged.

**Pipeline:** `/api/search` pins one immutable index, `investigate()` classifies
intent and symbols, ranks source chunks, optionally refines around observed
symbols, expands supported static calls, validates cited source, and returns
structured evidence. There is no LLM, query decomposition into independent
questions, or prose answer generator. `/api/map` renders indexed files and
supported static call relationships.

**Defects and fixes:** nearest-neighbor snippets were presented as relevant
code even when a named symbol or call premise was unsupported. Additive
grounding metadata now distinguishes verified definitions and calls, ambiguous
symbols, missing named symbols, and unsupported call premises. The frontend
labels all ranked snippets as candidates and links source-backed definitions
and call sites. Graph citation validation now checks exact indexed node
locations, edge identity, and displayed endpoints, preventing a real call-site
snippet from laundering a false edge.

**Validation:** ten manually specified golden fixture questions produced nine
structured factual claims, all source-backed, with zero unsupported or
contradicted claims. Ninety source citations resolved. Six expected file nodes
and four returned cross-file call edges were valid. Add, modify, rename, and
delete promotion left no stale nodes, edges, or citations. The old immutable
snapshot retained its original call, while the new snapshot rejected it after
modification. Actual local GTE `/api/search` runs passed on the fixture and
nine manually checked questions from the committed demo repository. Golden
investigation latency was p50 81.06 ms and p95 132.73 ms on that run. Focused
P003, P002, P001, retrieval regression, backend, and available benchmark tests
passed; MTEB and frozen TEST were not run.

**Limitations:** the product still offers source and graph navigation for broad
feature and dependency questions instead of a generated explanation. The map
models static calls, not import or containment edges; dynamic calls remain
unresolved. The frontend build was not run because local Node dependencies
are absent. P004 owns whole-product UI and demo hardening before code lock.

## P002 — search and source-citation API reliability

**Decision:** PASS. Implementation commit `d292625`; evidence:
[`benchmark/results/P002-search-api-reliability/`](benchmark/results/P002-search-api-reliability/README.md).
Retrieval optimization remains closed and the GTE dense ranking contract is
unchanged.

**Goal and invariants:** every source result, line range, graph citation, and
source fetch must resolve against the one immutable index selected for its
search request. A promotion may make a newer version active but cannot mix
old ranking with new source content.

**Implementation:** `/api/search` resolves one index and logs its version key;
the agent checks returned chunks and graph call sites against that index's
stored source before publishing a response. A missing query embedding or an
unexpected investigation error becomes a structured service error. Explicit
immutable keys remain valid for citation lookup after repository selection
changes. The existing frontend response fields are unchanged.

**Tests and real walkthrough:** 8 focused P002 tests passed; 91 backend tests
passed with one Node-dependent skip; 4 P001 tests, 2 E023 retrieval regression
tests, and 26 available benchmark tests passed. An actual GTE run through the
FastAPI routes passed initial search, add/modify/delete/rename/mixed promotion,
failed promotion, concurrent promotion, and restart. Citations were resolved
through `/api/source` by immutable key. MTEB and frozen TEST were not run.

**Latency:** on twelve local actual-GTE API queries, p50 69.16 ms and p95
102.87 ms. The same query before and immediately after promotion measured
63.45 ms and 66.05 ms respectively. Full evidence is in the P002 directory.

**Remaining limitations:** P001's schema-10 migration, full parse/graph
rebuild, and process-local cache lock remain. No P002 citation invariant is
left failing. The frontend build was blocked by absent local Node dependencies;
its existing response fields were checked directly against the frontend type
and consumers.

**Next product milestone:** P003 — investigation-agent correctness and
evidence grounding, focusing on whether claims and explanations accurately
reflect the already verified source evidence.

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

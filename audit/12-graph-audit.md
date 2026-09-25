# 12 · Graph / Map audit

The graph is a core product surface (S1: "answer structural queries … use AST or call-graph indexing"). It was
measured on the demo fixture and on two real repositories: expressjs/express `9a34acf` (141 JS files, 21.5k lines,
CommonJS) and lodash/lodash `2b5e6f7` (27 indexed JS files, IIFE-wrapped library).
Evidence: `evidence/graph-stats-before.json`, `evidence/graph-stats-after.json`, `evidence/resolver-nested-measure.json`.

## How the graph is built (traced)

| Aspect | Implementation |
|---|---|
| Nodes | Callable symbols (functions, arrow functions, methods, class-field arrows, callbacks) from tree-sitter (`parsing/javascript.py`); files in the overview |
| Edges | `CALLS` edges from the two-pass resolver (`structure/resolver.py`): supported local calls, same-class `this.method()`, constructor-held instances, unaliased relative ES6 named/namespace imports. TypeScript language service **corroborates** edges (never adds) |
| Meaning of an edge | "This call site statically resolves to that definition in this snapshot" — not runtime behaviour (the canvas caption says so) |
| Construction | NetworkX `DiGraph`; bounded BFS for trace (≤ 20 paths, ≤ 10,000 expansions, depth ≤ 8) |
| API bounds | `/api/map` ≤ 150 files or symbols; symbol neighbourhood depth ≤ 3 |
| Layout / render | `graphLayout.ts` deterministic layered layout (stable under reversed traversal, no overlap — unit-tested in `audit.spec.ts`); React Flow renders ≤ 60 nodes / ≤ 250 edges, with the limits disclosed in the key |
| Interaction | node search, click to select (highlights callers/callees), depth 1–3, direction filter, "Hide unrelated", "Explore calls" (server-side neighbourhood), "Open source", edge click → call-site evidence, fit/reset, zoom controls |

## Measured structure

| Repository | Callables | Edges before | Edges after F-023 | Isolated nodes before → after | Largest component after | Cross-file edges | Unresolved calls after |
|---|---|---|---|---|---|---|---|
| demo fixture | 21 | 12 | 12 | 33% → 33% | 9 | 9 | 9 |
| express | 3,120 | 12 | 284 | 99.3% → 90.8% | 41 | **0** | 10,472 |
| lodash | 4,463 | 20 | 1,336 (1,572 call-site records) | 99.4% → 77.5% | 511 | **0** | 16,939 |

Before the fix, 9,722 of express's and 17,002 of lodash's unresolved calls had the reason "Unsupported method or
nested callback scope": every call inside a function nested in another function was rejected, which in an
IIFE-wrapped library (lodash) or a callback-heavy code base (express) is almost every call. Commit `52063cf` resolves
plain identifier calls from nested scopes through the existing scope-chain lookup; **all 1,820 added edges were
independently confirmed by the TypeScript language service** (precision proxy 100%).

## Can a developer answer the key questions?

| Question | Demo fixture | express / lodash (after F-023) |
|---|---|---|
| What am I looking at? | Yes: file overview with cross-file edges; caption states "supported static calls · not runtime behavior" | Overview is a grid of 60/141 file boxes with **0 edges** (no cross-file resolution for CommonJS `require` / member calls) — little meaning |
| Why are these nodes connected? | Yes: edge click → call-site code + import/constructor evidence spans | Yes for resolved edges (same evidence panel) |
| Where is this code? | Yes: node label shows `file:line`; "Open source" opens Monaco at the lines | Yes |
| What calls this / what does this call? | Yes: selection highlights incoming (gold) / outgoing (green), counts shown | Within a file / IIFE: yes; across files: no (CommonJS) |
| What depends on this / what is affected by a change? | Partially: depth-2/3 neighbourhood + Compare view's added/removed call sites | Same limits |
| Graph → source navigation | Yes (node double-click, "Open source", edge click, unresolved-call links) | Yes |

## Findings

| ID | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| F-023 | P1 | Call graph essentially empty on real repositories (nested-scope calls rejected) | table above | **Fixed** (`52063cf`), TS-confirmed |
| F-029 | P2 | No cross-file edges for CommonJS (`require`, `module.exports`, `exports.x =`) or member calls on imported objects; the file overview of a CommonJS repo has no edges | express/lodash `cross_file_edges: 0` | Open — needs a conservative CommonJS resolver + a judged precision check; documented in README limits |
| F-030 | P2 | Overview of large repositories shows an unlabelled-looking grid at fit-to-screen zoom (60 of 141 files) — spaghetti is avoided, but so is meaning | browser screenshot on the express instance | Open — recommend clustering by directory and showing only files with edges first |
| F-031 | P3 | Anonymous functions assigned to properties are labelled `anonymous@L:C` (e.g. express `res.cookie`) | express map of `lib/response.js` | Open — a naming fix was prototyped and **rejected** because it hurt retrieval on an 8-question probe (`evidence/rejected-parser-heuristics.md`) |
| — | ok | Layout determinism and no-overlap | `audit.spec.ts` layout tests (small/medium/large/dense/disconnected) pass | Verified |
| — | ok | Limits disclosed (150 backend / 60 frontend nodes, 250 edges) | graph key text | Verified |

## Test coverage of the graph

`audit.spec.ts`: layout properties for 5 synthetic shapes, neighbourhood direction/depth, node search → selection →
hide unrelated → depth/direction → explore calls → fit → reset. `studio.spec.ts`: map file focus → node → open source;
trace → edge click → evidence. `journeys.spec.ts`: trace on a phone-sized screen. Backend: `test_nested_scope_calls.py`
(6 tests) plus the existing resolver/trace tests in `test_core.py` and `test_regressions.py`.

# Demo queries (chosen from measured evidence)

Every query below was run in the clean-clone walkthrough (`audit/JUDGE-WALKTHROUGH.md`, run 36257173755) with the
frozen configuration on a 4-vCPU CPU runner. Expected results were checked against source. Latencies are server-side
on that machine, warm; a laptop can differ.

## Q1 · Primary: plain-English retrieval

| | |
|---|---|
| QUERY | `where is the redirect location URL encoded` |
| REPO | expressjs/express |
| VERSION | 4.21.2 |
| EXPECTED RESULT | #1 `location`, `lib/response.js:914–926`: `res.location = function location(url) { … return this.set('Location', encodeUrl(loc)); }` |
| WHY IT IS GOOD | Plain English, no function name. The dense model ranks the right function first on its own (semantic #1). The answer is one click from the exact lines, and the same query drives the version demo (Q4). |
| EXPECTED LATENCY | ≈ 270 ms |
| FALLBACK QUERY | Q5 on the demo repository |

## Q2 · Usage (structural, unfamiliar repository)

| | |
|---|---|
| QUERY | `Where is compileQueryParser used?` |
| REPO | expressjs/express |
| VERSION | 4.21.2 |
| EXPECTED RESULT | #1 the definition (`lib/utils.js:182–205`); #2 its caller `set`, `lib/application.js:359–401`, labelled "1 call hop(s)" (`this.set('query parser fn', compileQueryParser(val))`) |
| WHY IT IS GOOD | The caller comes from the call graph (a CommonJS `require` resolved across files), not from text similarity. Expand **Investigation** to show plan → search → refine (caller expansion) → rank. |
| EXPECTED LATENCY | ≈ 305 ms |
| FALLBACK QUERY | Q3 |

## Q3 · Structural: call order ("which X before Y")

| | |
|---|---|
| QUERY | `Which functions call checkBluetoothPermission before openBluetoothSettings?` |
| REPO | demo repository (bundled) |
| VERSION | working-tree |
| EXPECTED RESULT | Source-order evidence `checkBluetoothPermission → openBluetoothSettings` in `BluetoothAgent.execute`, `bluetooth/BluetoothAgent.js:7–8`, labelled "Lexical order only; completion is not guaranteed"; `BluetoothAgent.execute` in the top 3 |
| WHY IT IS GOOD | The challenge's own example query type, answered with explicit static evidence and an honest limit |
| EXPECTED LATENCY | ≈ 145 ms |
| FALLBACK QUERY | Map → **Trace a path** `VoiceHandler` → `BluetoothAgent`: supported path through `IntentRouter.route`; click an edge for its call site |

## Q4 · Version retrieval (P1)

| | |
|---|---|
| QUERY | Q1 again after switching the version selector 4.18.2 → 4.19.2 → 4.21.2 |
| REPO | expressjs/express |
| VERSION | 4.18.2, 4.19.2, 4.21.2 |
| EXPECTED RESULT | #1 `location` each time, at `906–916` (`var loc = url;`), `907–925` (the open-redirect fix, `schemaAndHostRegExp`) and `914–926` (`deprecate('res.location("back")…')`) |
| WHY IT IS GOOD | Same question, three real releases, three different implementations; every snippet matches `git show <tag>`. Incremental indexing reused 2,955 of 3,262 vectors for 4.19.2. |
| EXPECTED LATENCY | ≈ 120–280 ms per version |
| FALLBACK QUERY | Demo repository: **Compare** v1 vs v2 ("symbols modified"; `AuthService.restore` delegates to `SessionManager.restore` in v2) |

## Q5 · Fallback: usage on the demo repository

| | |
|---|---|
| QUERY | `Where is openBluetoothSettings used?` |
| REPO | demo repository |
| VERSION | working-tree |
| EXPECTED RESULT | #1 definition `settings/deeplinks.js:2`; #2 `BluetoothAgent.execute` (only caller, 1 call hop); #3 `IntentRouter.route` |
| WHY IT IS GOOD | Small, fast and cached; works even if the express snapshots are missing |
| EXPECTED LATENCY | ≈ 160 ms |

## Honesty moment (optional, 10 s)

`Where is the Kafka consumer offset committed?` on express returns **"Closest matches by meaning"**, with "No result
shares a word or symbol with your question … may be unrelated". The product does not pretend.

## Avoid on stage

- `Where is view template rendering implemented?` (T5 failed). The word "view" is also a symbol name, and the
  exact-name boost lifts the `View` constructor and test callbacks above the render methods.
- Broad questions over test-heavy repositories: generated test-callback names (`callback@8:16…`) clutter the list.

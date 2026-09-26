# Judge walkthrough (clean clone, CPU, frozen configuration)

**Run:** workflow `walkthrough.yml`, run 36257173755, fresh `git clone` of this branch at `ca023da`.
**Machine:** GitHub-hosted runner, AMD EPYC 7763, 4 vCPU, 16 GB RAM, no GPU. This is the slower of the two runner CPU
types (see Performance).
**Procedure:** only the README. Install Python 3.12, Node 22 and Git, run `npm run setup`, then `npm run demo`. After
that the product was driven through its HTTP API (`scripts/judge_walkthrough.py`) and through the browser UI
(`audit/walkthrough/ui.spec.ts`).
**Evidence:** `audit/walkthrough/` holds `results.json`, `results.md`, `ui.json`, `health.json`, `hardware.txt`,
`setup.log`, `demo.log` and `screens/*.png`.

Expected answers were written from the repositories' source **before** the run. Every returned snippet (top 3) was
fetched back through `/api/source` for the *selected* version and had to lie within the reported lines of that exact
snapshot: **true for every task.**

## Setup and runtime identity

| Check | Result |
|---|---|
| Undocumented manual interventions | **0** |
| `npm run setup` (venv, pip, npm ci, build, demo history, 0.6 GB model download) | 101 s |
| `npm run demo` until the UI answers (model load + demo v1/v2/working tree indexed) | 12 s |
| Start-up line | `Retrieval: Alibaba-NLP/gte-modernbert-base · dense · CPU (frozen submission configuration)` |
| `/api/health` → `retrieval` | model `Alibaba-NLP/gte-modernbert-base`, mode `dense`, precision `float32`, `frozen_submission_configuration: true` |
| Indexed versions report their model | every express and demo snapshot: `embedding_model` = the frozen model |
| Disk | `.venv` 1.6 GB (CPU PyTorch), model 576 MB, `node_modules` 226 MB |

**Does a judge who follows the README get the frozen GTE system? PASS.** Runtime-verified above; no environment
variables were set. Without the model the product refuses to index and says how to fix it
(`backend/tests/test_frozen_product.py`); it never falls back silently.

## Tasks

Verdicts: **PASS** if an expected answer is ranked first. For usage and call-order questions the bar is the top 3,
because the definition the user named legitimately comes first. **PARTIAL** if within the top 5, **FAIL** otherwise.
Latency is server-side, warm.

### T1 · Plain-English retrieval (unfamiliar repository): PARTIAL

- **Query:** "Which code picks the response format based on what the client says it accepts?"
- **Repository / version:** expressjs/express @ 4.21.2 (152 files, 3,270 chunks).
- **Expected:** `res.format`, `lib/response.js:684–709`.
- **Top results:**
  1. `accepts` (`lib/request.js:132–135`)
  2. **`format`** (`lib/response.js:684–709`)
  3. `format` (`examples/content-negotiation`)
  4. `acceptsEncodings`
  5. a test callback
- **Correct?** Partly. #2 is the answer. #1, `req.accepts`, is the other half of content negotiation and is called
  by `res.format`.
- **Latency:** 234 ms.
- **UX confusion:** both top results carry "Exact symbol" because the English words "format" and "accepts" are also
  function names. Their semantic ranks are 27 and 49, so these two were lifted by name matches, not by meaning.
- **Value demonstrated:** plain English lands in the right module with `file:line` and one click to source.

### T2 · Usage query: PASS (express), PASS (demo)

- **Query (express):** "Where is compileQueryParser used?" @ 4.21.2.
- **Expected:** its caller `app.set` (`lib/application.js`, `this.set('query parser fn', compileQueryParser(val))`).
- **Top results (express):**
  1. `compileQueryParser` (definition)
  2. **`set`** (`lib/application.js:359–401`, *1 call hop*)
  3. `lazyrouter`, 1 hop
  4. test callbacks
- **Latency:** 305 ms.
- **Query (demo):** "Where is openBluetoothSettings used?". Top results: the definition, then **`BluetoothAgent.execute`**
  (its only caller, 1 hop), then `IntentRouter.route` (calls `execute`). Latency 160 ms.
- **Correct?** Yes. The real call site is found through the call graph (CommonJS `require` resolution on express),
  not by text similarity.
- **UX confusion:** test callbacks carry generated names (`callback@7:16.callback@8:21…`) that are hard to read.

### T3 · Structural query (call order): PASS

- **Query:** "Which functions call checkBluetoothPermission before openBluetoothSettings?"
- **Repository / version:** demo @ working-tree.
- **Expected:** `BluetoothAgent.execute`, which calls `checkBluetoothPermission()` and then `return
  openBluetoothSettings()`.
- **Result:**
  - Sequence evidence: "checkBluetoothPermission → openBluetoothSettings · Direct calls in separate statements of
    the same function body. Lexical order only; completion is not guaranteed · `bluetooth/BluetoothAgent.js:7–8`".
  - Ranked list: the two named functions, then `BluetoothAgent.execute` (#3).
- **Correct?** Yes, checked against source. **Bug found and fixed in this pass:** the parser used to refuse order
  evidence for any function containing `return`, so the demo's own structural question had no answer
  (`041aba9`). A final `return` cannot skip earlier statements; early exits still disqualify a function (tests).
- **Latency:** 145 ms.

### T4 · Version retrieval (P1): PASS × 3

- **Query:** "where is the redirect location URL encoded", same wording on each version.
- **Repository:** expressjs/express, real Git tags 4.18.2, 4.19.2 and 4.21.2 of the full repository.

| Version | #1 result | Semantic rank | Snippet = `git show <tag>` lines | Latency |
|---|---|---:|---|---:|
| 4.18.2 | `location`, `lib/response.js:906–916` (`var loc = url;`) | 1 | true | 118 ms |
| 4.19.2 | `location`, `lib/response.js:907–925` (open-redirect fix: `schemaAndHostRegExp`) | 1 | true | 280 ms |
| 4.21.2 | `location`, `lib/response.js:914–926` (`deprecate('res.location("back")…')`) | 1 | true | 270 ms |

- **UI:** switching the version selector and asking again shows each version's lines. The selector, the source
  status (`L906–916 · 662b180b`, `L907–925 · 4309fb00`, `L914–926 · 5bb450e1`) and the snippet always refer to the
  same snapshot (screenshots `02-express-*`). The automated text check marked 4.18.2 false: Monaco renders spaces as
  non-breaking spaces, so the multi-word marker did not match. The screenshot shows `var loc = url;` at line 907.
- **Demo repository (v1 → v2 refactor):** "Where is the saved session restored after restart?" returns
  `AuthService.restore` at #3 on v1 and `SessionManager.restore` at #3 on v2, behind the delegating
  `AuthService.restore`. **PARTIAL × 2**: correct per version, not first.

### T5 · Large-repository navigation: FAIL

- **Query:** "Where is view template rendering implemented?" @ express 4.21.2.
- **Expected:** `View.prototype.render` (`lib/view.js`), `app.render` / `tryRender` (`lib/application.js`) or
  `res.render`.
- **Top results:**
  1. `View` constructor (`lib/view.js:52–95`, relevant file, not the render method)
  2–5. test callbacks whose generated names end in `.View`
  - the expected render implementations at #9
- **Cause:** the query word "view" equals the symbol name `View`, so the exact-symbol boost lifted the constructor and
  test callbacks above the render methods. The dense first stage ranked them lower.
- **Not fixed.** The ranking is part of the frozen configuration, and changing the boost now would be tuning on this
  walkthrough. Recorded as open P1 finding J-1.
- **Relationships of #1:** `View` has no resolved callers or callees in the static graph (it is used through
  `this.get('view')`, a dynamic lookup), so graph navigation does not help here.
- **Latency:** 308 ms.

### T6 · No evidence (honesty): PASS × 2

- **Queries:** "Where is the Kafka consumer offset committed?" (express) and "qxzjvnonexistentidentifier" (demo).
- **Result:** both are labelled **"Closest matches by meaning"**, with the text "No result shares a word or symbol
  with your question. These 10 snippets are only the nearest code by meaning and may be unrelated." The list is not
  presented as the answer (screenshot `06-express-no-evidence.png`).

### T7 · Graph: PASS

- **Symbol:** `IntentRouter.route` (demo).
  - Callers: `VoiceHandler.handleRequest` (expected).
  - Callees: `BluetoothAgent.execute`, `openWifiSettings` (expected).
- **Trace** `VoiceHandler.handle → openBluetoothSettings`: SUPPORTED, path `handle → handleRequest → route → execute
  → openBluetoothSettings`. In the UI, clicking an edge opens its call-site evidence and source (screenshot
  `09-demo-trace-edge.png`).
- **Large repository:** the express map shows "150 most connected of 152 source files". It is readable but bounded,
  and most express calls are member or dynamic calls that stay unresolved (shown as such).

### Summary

| | Count |
|---|---:|
| Tasks attempted | 13 (T1, T2 × 2, T3, T4 × 5, T5, T6 × 2, T7) |
| PASS | 9 |
| PARTIAL | 3 (T1, T4-demo v1, T4-demo v2) |
| FAIL | 1 (T5) |
| Browser journeys | 2 / 2 passed; 0 console errors on the demo path (`ui.json`) |

**Would a technically competent evaluator understand ASTFLOW's value within five minutes? YES, on the prepared
path.**

- The runtime identity, version retrieval, call-order evidence, usage via the call graph and the honesty label are
  clear and correct within seconds of asking.
- An unguided evaluator on a large repository will meet two confusions: generated test-callback names
  (`callback@8:16.callback@9:32…`) crowding the lists, and English words that are also symbol names being labelled
  "Exact symbol" (T1, T5). The demo script avoids both by using queries verified here (`submission/DEMO-QUERIES.md`).

## Performance (CPU, measured)

| Item | Measured |
|---|---|
| Hardware | AMD EPYC 7763, 4 vCPU, 16 GB (walkthrough); Intel Xeon Platinum 8573C, 4 vCPU (index-timing) |
| Model load + demo index (3 snapshots, 17–21 chunks each) | 12 s from `npm run demo` to a ready UI |
| First index, express 4.18.2 (153 files, 3,226 chunks) | **712.5 s** (AMD, float32, API with TS enrichment); 374.5 s (Intel AMX, CLI, before the float32 change) |
| Incremental, 4.19.2 (2,955 reused / 307 new) | 79.4 s (AMD); 45.7 s (Intel) |
| Incremental, 4.21.2 (2,888 reused / 382 new) | 92.8 s (AMD); 51.9 s (Intel) |
| Short query (42 characters), warm | P50 266 ms, max 271 ms |
| Long query (1,880 characters, dataset-style), warm | P50 1.66 s, max 1.69 s |
| Ranking after encoding (official harness) | P50 27.7 ms |
| Server memory after indexing three express versions | peak RSS 1.96 GB |
| AppsRetrieval corpus for `astflow snippets` | 8,754 published vectors downloaded and spot-checked; relevant doc ranked #1 for q5001; 50.7 s from an empty cache, search 3.4 s |

Initial index, incremental update and query are different costs. The first index embeds every chunk once. A new
version embeds only chunks whose text changed, about 10% of express between these releases. A query encodes only the
question and scores cached vectors.

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| J-0a | P0 | Product defaulted to MiniLM Hybrid, not the frozen GTE Dense | **Fixed** `75928d3` |
| J-0b | P0 | Silent lexical fallback without the model | **Fixed** `75928d3` (actionable error; explicit `ASTFLOW_SEMANTIC=off`) |
| J-0c | P0 | float16 checkpoint ran 6× slower on common CPUs (express first index 40 min on AMD) | **Fixed** `db57806` (float32; vectors cos ≥ 0.9995 vs evaluation) |
| J-0d | P1 | `astflow snippets -c apps` would embed 8,765 documents on CPU (≈ 4 h) first | **Fixed** `dd534ee` (published, spot-checked vectors) |
| J-0e | P1 | `npm run setup` did not install what `astflow snippets -c apps` needs | **Fixed** `dd534ee` |
| J-0f | P1 | Linux setup installed CUDA PyTorch (5.8 GB `.venv`) | **Fixed** `7a4bc86` (1.6 GB) |
| J-0g | P1 | Demo call-order question had no evidence | **Fixed** `041aba9` |
| J-0h | P1 | Progress batching (added in this pass) lost length-sorting | **Fixed** `498163b` |
| J-0i | P2 | "Use demo repository" silently did nothing before the page loaded | **Fixed** `041aba9` |
| J-1 | P1 | English words equal to symbol names trigger the exact-symbol boost (T1, T5) | **Open.** Ranking is frozen; the demo avoids it |
| J-2 | P2 | Generated names for anonymous test callbacks are hard to read in result lists | Open |
| J-3 | P2 | Version selector lists every tag (319 for express) | Open |
| J-4 | P2 | UI configuration line omits the precision (it is in `/api/health`) | Open |

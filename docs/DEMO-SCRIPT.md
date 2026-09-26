# ASTFLOW — 5-minute demo script

Goal (official brief): show the solution **answering queries live and how fast it is**, not only numbers.
Every step below was run on 2026-09-26 against the committed code; latencies are from that run (CPU, lexical
fallback in the recording container; with the MiniLM model add ~10–40 ms of query encoding).

Setup before recording: `npm run setup`, `npm run demo` (indexes the fixture's `v1`, `v2` and working tree), a second
terminal in the project root, and a three-version express checkout for step 5
(`npm pack express@4.18.2 express@4.19.2 express@4.21.2`, one commit + tag per version — see `audit/FINAL-SUBMISSION-READINESS.md`).

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Title slide → the ASTFLOW window on the demo repository | "An agent or a new developer can't read thousands of files. The bottleneck is *getting to the right lines*. ASTFLOW ranks code snippets for a plain-English question, on CPU, for any Git version." |
| 0:30–1:00 | Architecture slide (README diagram) | Tree-sitter callable chunks → BM25 + CPU embeddings → RRF → at most one evidence-driven refinement pass → ranked snippets with file:line. Call graph and Git snapshots are indexes, not guesses. |
| 1:00–1:40 | Ask: **"How is the input preprocessed before going to the main function?"** (the brief's own example) | `voice/normalizeInput.js:2` ranks first, then `VoiceHandler.handle`. Click it: exact lines open. Point at the latency. |
| 1:40–2:15 | Ask: **"Where is the Bluetooth settings deeplink used?"** (usage query) | Rank 1 is the caller `BluetoothAgent.execute`, and `openBluetoothSettings` (the deeplink) is listed with it. Expand **Investigation** to show PLAN → SEARCH → OBSERVE → RANK. |
| 2:15–3:00 | Map → **Trace a path** `VoiceHandler` → `BluetoothAgent`; then ask **"Which files call normalizeInput before IntentRouter?"** | Structural query: supported static call edges with call-site evidence; SEQUENCE evidence is lexical order, stated honestly. Mention CommonJS `require()` is resolved too (express: 0 → 11 cross-file edges). |
| 3:00–3:45 | Compare `v1` ↔ `v2` for "session restoration"; then terminal: `astflow search <express> "where is the redirect location URL encoded" --version v4.18.2` and `--version v4.21.2` | P1: the same query returns `lib/response.js` `location` at L906–916 in 4.18.2 and L914–926 in 4.21.2, with each version's code. Re-opening a cached version: ~50 ms. |
| 3:45–4:30 | Terminal: `astflow snippets --query-file hard_problem.txt` (a full competitive-programming statement) | The screening setting: a ~2,000-character problem statement against the 8,765-snippet CoIR Apps corpus; ranked Python solutions with ids and rank evidence, query latency printed. Bonus: `-c v1=… -c v2=…` folds identical snippets across versions. |
| 4:30–5:00 | Results slide | Official MTEB AppsRetrieval (test, 3,765 queries): NDCG@10 and MRR from `appsretrieval_results.json` (see the readiness report for the current numbers), CPU-only indexing and query latency, what was tried and rejected (E001–E005). |

Do **not** show the 16-query local fixture score as retrieval quality; it is a regression fixture.

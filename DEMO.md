# ASTFLOW demo

## Prepare and start

Use Python 3.12 (3.11+ supported), Node.js 22.12+, npm, and Git. From the repository root:

```sh
npm run setup
npm run demo
```

Open <http://127.0.0.1:8000>. Setup installs pinned Python dependencies, runs `npm ci`, builds the React frontend, prepares the demo Git history, and downloads the pinned GTE model. `npm run demo` indexes `examples/demo-repo` and serves the production build. The initial model download requires network access; later starts use the cache. If setup reports that GTE is unavailable, rerun `npm run setup` with network access. ASTFLOW will not silently substitute another model.

## Walkthrough

1. Confirm the Explorer shows `examples/demo-repo` source and that **How this works** reports GTE dense retrieval on CPU.
2. Ask **Where is validateCredentials defined?** Open the indexed definition in `auth/credentials.js` and inspect its exact lines.
3. Ask **Why does openBluetoothSettings call openSettingsUri?** Open the supported call site in `settings/deeplinks.js`.
4. Ask **How does VoiceHandler reach BluetoothAgent?** Expand **Investigation** to see the second pass, then use **Map → Trace a path** for the source-backed static path.
5. Ask **Where is the Kafka consumer implemented?** The answer must say that no verified implementation was found. Any ranked snippets remain labeled as candidates.
6. Open **Map**. Its arrows represent supported static caller-to-callee relationships. Select a file or node to inspect source. The map does not assert runtime behavior, imports, or containment.
7. To demonstrate an update without altering the committed fixture, copy `examples/demo-repo` to a temporary directory and select that copy with **Repository settings → Open & index**. Add `demoUpdate.js` containing `export function demoUpdate() { return 'updated'; }`, then choose **Reindex repository**. Ask **Where is demoUpdate defined?** and confirm both the citation and Map file selector show `demoUpdate.js`.
8. Reindex unchanged source once more. The UI should say **Repository already up to date**. Reload the page; the indexed workspace, search, and map should remain available.

The committed demo also has `v1` and `v2` snapshots for Compare. The UI shows grounded navigation, not an LLM-written architecture summary. Dynamic dispatch may remain unresolved. For a focused release verification, run `npm run build`, `npm run test:ui` while the demo server is running, and `python -m pytest backend/tests` in the installed Python environment.

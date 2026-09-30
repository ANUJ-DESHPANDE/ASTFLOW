# ASTFLOW release candidate state

ASTFLOW is a local JavaScript repository investigation application. It indexes source and Git snapshots, returns ranked code candidates with pinned source citations, identifies verified definitions and static calls, draws a code map of supported calls, and updates snapshots incrementally. It does not execute indexed repositories or use an LLM to write explanations.

The accepted production model is `Alibaba-NLP/gte-modernbert-base`, revision `e7f32e3c00f91d699e8c43b53106206bcc72bb22`. Ranking uses exact dense dot product over normalized embeddings, top 1000, 512 tokens, CPU float32, and up to eight physical-core-aware threads. Reranking, MMR, and BM25 final fusion are off. The frozen validated AppsRetrieval TEST scores are NDCG@10 **0.5509** and MRR@10 **0.5050**; P004 does not rerun that set.

## Install and run

Requirements: Python 3.11+ (3.12 recommended), Node.js 22.12+, npm, and Git. From the repository root:

```sh
npm run setup
npm run demo
```

Open <http://127.0.0.1:8000>. `npm run setup` uses `requirements.lock.txt` for Python, `npm ci` for Node, and an explicit model download. After setup, the model and index live under `.astflow` by default. The server binds to localhost port 8000. A development frontend can be started with `npm run dev` on port 5173; Vite proxies `/api` to the backend. Configuration is documented in `.env.example`; keep `ASTFLOW_MODEL` and `ASTFLOW_RETRIEVAL` at their defaults to reproduce the accepted ranking.

Use **Repository settings** to choose a JavaScript repository and index its working tree or a Git revision. Ask a question in the companion panel; select a definition, call site, or ranked snippet to open its repository-relative file and lines. Map arrows show supported static calls. Choose **Reindex repository** after edits. See [DEMO.md](DEMO.md) for the canonical walkthrough and [README.md](README.md) for CLI and setup details.

## Validated scope and limits

P001 validated ingestion and promotion; P002 validated immutable API citations; P003 validated structured grounding and map semantics. P004 validates the built frontend with the actual GTE backend and committed demo repository. The validated product implementation is commit `6447aa1` on `release/P004-product-hardening`; the branch's final pushed HEAD is the release candidate commit reported in the P004 decision dashboard. Code lock follows only when the P004 criteria pass.

ASTFLOW currently returns grounded source and graph navigation rather than generated prose explanations. The map models static calls, not import or containment edges; dynamic dispatch remains unresolved. JavaScript (`.js`, `.mjs`, `.cjs`, `.jsx`) is the indexed language set. Schema-10 indexes require a one-time reindex; changed snapshots still parse and rebuild graph state; cache write locking is local to one server process. These limits are documented capability boundaries, not demonstrated citation failures.

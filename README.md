# ASTFLOW

**Find the code. Trace the path. See what changed.**

ASTFLOW is a local repository investigation engine for JavaScript. Ask a question, get ranked source snippets, follow supported call relationships, and compare the answer across Git snapshots. The snippet list is the canonical answer; graphs and explanations supplement it.

It runs on a CPU, needs no paid API, and never executes an indexed repository. The included source fixture has voice routing, Bluetooth settings, authentication, test cases, dynamic dispatch, and two real Git commits showing a session-management refactor.

## Quick start

Requirements: **Python 3.12** (3.11+ supported), **Node.js 22.12+**, npm, and Git. Run commands from this directory.

```sh
npm run setup
npm run demo
```

Open **http://127.0.0.1:8000**. Setup creates `.venv`, installs Python and Node dependencies, builds the frontend, prepares the demo Git history, and attempts to download the free MiniLM embedding model. The download happens only during setup or the explicit `model-download` command. If unavailable, source search and all structural/version features remain usable with a clearly reported lexical fallback.

`npm run demo` indexes `v1`, `v2`, and the working tree with one shared model instance, then starts FastAPI serving the built React UI. First startup includes model loading; subsequent indexes reuse saved vectors. Stop with Ctrl+C.

On Windows the setup script uses `py -3.12`; on macOS/Linux it uses `python3`. The Python environment can also be prepared manually:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm run build
.\.venv\Scripts\python.exe scripts/setup_demo.py
.\.venv\Scripts\python.exe -m backend.app.cli model-download
npm run demo
```

On macOS/Linux replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`. Activating the environment makes the `astflow` CLI available directly.

## Try the investigation

1. Search **Where is Bluetooth settings handled?** Open `openBluetoothSettings` to inspect the exact indexed lines.
2. Search **How does VoiceHandler reach BluetoothAgent?** The investigation panel shows the observed candidates, refinement action, second search, and final ranking.
3. Open **Trace**, enter `VoiceHandler` and `BluetoothAgent`, then choose **Trace path**. Click an edge to open its stored call site.
4. Search **Where is session restoration handled?** Open **Changes**, select `v1` and `v2`, and compare. `AuthService.restore` delegates to the added `SessionManager.restore` in v2.
5. Try **Where is authentication validated before a session is created?** Direct lexical ordering is shown separately from call-path evidence.

The demo is source code, not a lookup table. Its query strings are only UI examples and benchmark inputs; the retrieval engine contains no query-specific answers. Demo authentication is deliberately a small fixture, not a production authentication implementation.

## Use another repository

Click the repository name, enter an absolute local path, and choose `working-tree`, `HEAD`, a tag, or a commit. Index each version you want to investigate. Use the sidebar selector to switch snapshots. Reindex explicitly after working-tree edits.

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli index C:\projects\my-app --version HEAD
.\.venv\Scripts\python.exe -m backend.app.cli search C:\projects\my-app "Where is input validated?" --version HEAD
.\.venv\Scripts\python.exe -m backend.app.cli compare C:\projects\my-app "session restoration" HEAD~1 HEAD
.\.venv\Scripts\python.exe -m backend.app.cli serve
```

`serve` opens the last indexed workspace. `serve PATH` indexes that path's working tree first. The UI's repository dialog also accepts arbitrary Git revision expressions; only committed source blobs are read, without checkout changes.

## Architecture

```mermaid
flowchart TD
    R[JavaScript repository / Git snapshot] --> D[Deterministic source discovery]
    D --> P[Tree-sitter symbols and source spans]
    D --> T[TypeScript language service]
    P --> C[Function and method chunks]
    P --> G[Two-pass call resolver / NetworkX graph]
    T --> G
    C --> S[(SQLite sources, symbols, chunks, edges)]
    C --> E[CPU embeddings / persisted NumPy arrays]
    G --> S
    Q[Natural-language question] --> I[Deterministic intent planner]
    I --> H[BM25 + semantic ranks + exact symbols]
    S --> H
    E --> H
    H --> O[Observe candidates, agreement, targets, paths]
    O --> F[At most one evidence-driven refinement]
    G --> F
    F --> A[Ranked source snippets]
    A --> V[Exact source / trace / version comparison]
```

```text
backend/app/
  api/           Pydantic request contracts
  parsing/       Tree-sitter JavaScript extraction
  indexing/      Safe discovery, immutable snapshots, orchestration
  retrieval/     Code tokens, BM25, CPU embeddings, rank fusion
  structure/     Static resolver, graph queries, TS enrichment
  agent/         Observable two-pass investigation
  versions/      Symbol, edge, and retrieval comparison
  storage/       SQLite and NumPy persistence
  runtime/       Reserved; runtime execution is not enabled
  main.py        FastAPI and built frontend
  cli.py         Independent CLI entry points
backend/tests/   Parsing, resolution, retrieval, API, Git, semantic tests
frontend/src/    React / TypeScript investigation interface
frontend/e2e/    Live browser integration tests
tools/          In-memory TypeScript compiler analysis
benchmark/      Graded queries, baselines, metrics, dataset adapter, reports
examples/demo-repo/  Actual JavaScript fixture with v1/v2 Git tags
scripts/        Setup, startup, live API verification
.astflow/       Generated indexes, models, screenshots (ignored by Git)
```

## How retrieval works

Discovery reads `.js`, `.mjs`, `.cjs`, and `.jsx`, excludes dependency/generated directories and minified bundles, skips symlinks, and normalizes paths to relative POSIX form. Input order, symbol tables, rankings, and graph serialization are deterministic. Source bytes are preserved as UTF-8; invalid UTF-8 files are reported and skipped.

Tree-sitter extracts functions, named arrow functions, classes, methods, class-field arrows, imports/exports, parameters, bindings, and call expressions. Retrieval chunks follow callable boundaries. Search context includes the qualified name, path, nearby comments, imports used by the callable, and its body. Files without callable units get module chunks of at most 80 lines. Whole-file chunks are not added on top of callable chunks.

Code tokenization splits camelCase, PascalCase, snake_case, and kebab-case while retaining complete identifiers. BM25 uses a positive-IDF formulation so tiny and single-document indexes remain searchable. The configurable default dense model is `sentence-transformers/all-MiniLM-L6-v2`, with normalized CPU embeddings and exact NumPy dot-product ranking.

Lexical and dense rankings are fused with reciprocal rank fusion (`k=60`). Scores are ranking signals, **not probabilities**. Exact symbols, symbol-token overlap, bounded graph proximity, and observed test references contribute small, inspectable boosts. Tests receive a modest downweight in ordinary production-code queries. The candidate pool is at least 50 where available; smaller repositories return the available matching chunks. Normal responses contain ten snippets.

The index stores vectors once, including their chunk-row mapping. There is no vector database and no remote embedding request during search.

## What the agent does

The planner recognizes locate, usage, path, sequence, version, and general intents. The first search is followed by an observation of ranking agreement, exact symbols, file diversity, missing structural targets, and supported paths.

For a structural query, missing target, or weak lexical/dense agreement, a second query incorporates symbols actually found or missed in the first pass. Its ranking contributes a bounded reciprocal-rank term. Graph expansion also uses the observed seeds and resolved query targets. It traverses at most two hops with distance decay. The agent stops after at most two retrieval passes.

The API exposes `PLAN → SEARCH → OBSERVE → REFINE → SEARCH → RERANK → STOP` when refinement is warranted; straightforward searches can stop after one pass. This is an operational activity log, with actual queries and counts. Disabling investigation mode disables the second pass while preserving ordinary hybrid/structural retrieval.

Version intent uses the explicitly selected snapshot. **Changes** runs the question against both selected versions; the engine does not guess an unspecified historical commit.

## Structural evidence and its limits

The resolver first discovers every symbol, then resolves relationships against the completed table. It supports local calls, named/default/namespace ESM imports, import aliases, same-class calls, and simple instances created in constructors, class fields, or local variables. Cyclic imports do not depend on traversal order. Targets are existing callable symbols; unresolved calls never create phantom nodes.

Each edge stores its source and target IDs, exact file and call line range, UTF-8 byte span, source expression, resolution method, and evidence sources:

- `STATIC_VERIFIED`: supported by the conservative syntax/binding resolver.
- `LANGUAGE_SERVICE_VERIFIED`: supported by a TypeScript declaration resolution.
- `SEARCH_INFERRED`: relevance or an unresolved relationship; never drawn as a verified call edge.

The TypeScript layer receives the snapshot through stdin and uses an in-memory compiler host. It does not load a target repository's configuration, plugins, or dependencies. Its timeout/failure is nonfatal. Confirmation from both analyzers is retained on one edge rather than duplicated.

Static evidence describes a supported source relationship, not proof of runtime execution. Reflection, computed/dynamic dispatch, dependency injection, arbitrary monkey-patching, complex alias/reassignment flows, CommonJS export resolution, and many reexport patterns remain outside the baseline. The language service may resolve some additional patterns. Search results stay useful when structure is unavailable.

Sequence evidence is **lexical order only**: calls in separate direct statements in the same function body. Calls in unrelated branches or nested arguments do not establish order. Exceptions, asynchronous completion, and full control-flow guarantees are not analyzed.

The graph API supports callers, callees, neighbors, shortest paths, and bounded paths. Trace defaults to five edges, has result/expansion limits, and shows only a relevant subgraph. A class name expands to its methods; an exact `path::qualified_name` identifies one symbol unambiguously.

## Versions and storage

Each source snapshot and analysis configuration receives its own content-addressed cache under `.astflow/indexes/<version_key>/`:

```text
index.sqlite          files, symbols, chunks, edges, metadata
embeddings.npy        normalized embeddings, when available
embedding_rows.json   vector-to-chunk mapping
manifest.json         revision, counts, timestamps, timings, model, configuration
```

Sources are served from the stored snapshot. Editing the working tree after indexing cannot change a result's source view. API responses include immutable `version_key` values to preserve this correspondence even when a named branch is later reindexed.

Comparison reports added, removed, and modified symbols; added/removed call sites; simple moved-symbol candidates; both ranked result sets; and rank changes. Stable identity is `path::qualified_name`, with source hashes for content changes. Move detection requires matching qualified names and strongly matching bodies. It is intentionally conservative rather than a general refactoring detector.

## Configuration

See [`.env.example`](.env.example). Variables are read from the process environment; the file is a template, **not automatically loaded**. Ranking weights and limits are centralized in [`backend/app/config.py`](backend/app/config.py).

| Setting | Default | Purpose |
| --- | --- | --- |
| `ASTFLOW_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | CPU embedding model name or local path |
| `ASTFLOW_SEMANTIC` | `auto` | Use a cached model; `off` forces lexical retrieval |
| `ASTFLOW_CACHE` | `.astflow` in this project | Index/model/state storage |
| `ASTFLOW_TS_ENRICH` | `true` | Enable best-effort compiler enrichment |

Download a changed model explicitly, then reindex:

```powershell
$env:ASTFLOW_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
.\.venv\Scripts\python.exe -m backend.app.cli model-download
```

No cloud LLM, API key, runtime execution, or external explanation service is configured.

## API

Interactive OpenAPI documentation: **http://127.0.0.1:8000/docs**.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Service/model status |
| `GET /api/repository?version=…` | Active repository, indexed versions, snapshot files |
| `POST /api/index` | `{repo_path, version, background: true}`; background jobs return 202 |
| `GET /api/index/status` | Actual stage, progress, error, and completed manifest |
| `POST /api/search` | `{query, version, top_k: 10, agentic: true}` |
| `POST /api/trace` | `{source_symbol_id, target_symbol_id, version, max_depth: 5}` |
| `GET /api/source` | `path`, `version`, `start_line`, `end_line` |
| `GET /api/versions` | Working tree, HEAD, tags, recent commits, index status |
| `POST /api/compare` | `{query, version_a, version_b}` |
| `GET /api/symbol/{symbol_id}` | Symbol metadata and caller/callee/neighbor IDs |

Search results contain rank, chunk/symbol IDs, qualified name, kind, relative path, inclusive start/end lines, exact source snippet, score, evidence contributions, and snapshot identity. Unindexed versions return an actionable error. Runtime trace IDs are rejected because runtime evidence is not implemented.

The service binds to loopback and validates Host/Origin headers. Source requests only address stored files, reject traversal, and validate line ranges. This is a single-user local prototype, not an authenticated multiuser server. Indexing never invokes `npm install`, tests, or application code in the target repository.

## Verification and benchmarks

```powershell
.\.venv\Scripts\python.exe -m pytest
npm run build
# With npm run demo running in another terminal:
.\.venv\Scripts\python.exe scripts/verify_demo.py
npm run test:ui
.\.venv\Scripts\python.exe -m benchmark.evaluate
```

Browser tests use installed Microsoft Edge by default. For another platform, set the Playwright `channel` in `playwright.config.ts` or install Chromium with `npx playwright install chromium` and remove the Edge channel. Tests use the **real running backend**; they do not mock search or graph responses. They save screenshots under `.astflow/screenshots/`.

Backend coverage includes parser spans/Unicode, named exports, arrows/JSX, deterministic resolution, aliases and cyclic imports, dynamic and shadowed calls, reassignment and `this` boundaries, conservative sequence ordering, source filters, lexical retrieval, real CPU semantic retrieval, persisted vectors, agent refinement, graph traversal, API/source validation, Git comparison, and real/failing TypeScript enrichment. Semantic integration tests report a skip when the optional model is not installed; language-service tests report a skip when Node dependencies are absent.

The local benchmark computes **NDCG@10, MRR, Recall@10**, median and p95 query latency for BM25-only, dense-only, hybrid, hybrid plus structure, and the full engine. It validates every relevance label against actual indexed symbols. Full per-query rankings and metrics are saved in [`benchmark/results/local.json`](benchmark/results/local.json), with a readable table in [`benchmark/results/local.md`](benchmark/results/local.md). Live API verification measurements are in [`benchmark/results/verification.json`](benchmark/results/verification.json).

The included 16-query/24-chunk benchmark is a small handcrafted regression fixture. It does **not** establish performance on large repositories or an official PRISM/MTEB evaluation. No benchmark numbers are hardcoded into the application. Index time includes CPU model loading on a cold process; query measurements warm the model first.

### CoIR / AppsRetrieval adapter

The optional adapter reads the real `CoIR-Retrieval/apps` dataset used by MTEB's AppsRetrieval task. It uses the inspected `datasets` 4.x API, validates current configurations/columns, pins the downloaded dataset revision, and exports ordinary BEIR JSONL/TSV files. It also accepts existing BEIR exports without network access.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[benchmark]'
.\.venv\Scripts\python.exe -m benchmark.mteb_appretrieval --download --max-queries 32
# Reuse downloaded files; 0 evaluates every test query against the full corpus:
.\.venv\Scripts\python.exe -m benchmark.mteb_appretrieval --max-queries 0
# Use a local BEIR-format export:
.\.venv\Scripts\python.exe -m benchmark.mteb_appretrieval --data C:\datasets\apps --max-queries 32
```

The default is a **32-query adapter smoke run against the full corpus**, explicitly labeled in `benchmark/results/apps.json` and `apps.md`. It compares BM25, dense, and hybrid retrieval. Apps documents are standalone Python solutions, so this adapter does not invent JavaScript graph or version evidence for them. It is not a run of the official MTEB evaluator and is not an official leaderboard score. Full-split execution is available but takes longer on CPU.

## Development

Run the backend in one terminal and `npm run dev` in another. Vite proxies `/api` to port 8000; open http://127.0.0.1:5173. `npm run build` performs TypeScript checking and a production Vite build. The source viewer and graph are loaded on demand. Monaco and its worker are bundled locally; source viewing requires no CDN.

The checked-in npm lock and Python constraints record the verified dependency set. SQLite indexes and embeddings are rebuildable runtime artifacts. The demo setup script is idempotent and refuses to overwrite unrelated existing demo Git history.

## Remaining optional work

- Runtime execution/coverage, explicit scenarios, and observed runtime evidence.
- A CPU cross-encoder reranker, retained only after a measured quality/latency improvement.
- Broader language-service resolution, test framework patterns, and moved-symbol analysis.
- External LLM planning or evidence-only explanation generation.
- Large-repository performance profiling, incremental indexing, and an independent relevance dataset.

These are not presented as implemented features. The core search, trace, source, and version workflows operate independently of them.

Implementation references: [Tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter), [Sentence Transformers encoding](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html), and [CoIR Apps dataset](https://huggingface.co/datasets/CoIR-Retrieval/apps).

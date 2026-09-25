"""Builds audit/findings.json (the master findings database) from the entries below."""
import json

F = []


def f(id, cat, sev, conf, title, desc, evidence, repro, files, feature, req, action, effort, deps, status, fix=None):
    F.append({"id": id, "category": cat, "severity": sev, "confidence": conf, "title": title, "description": desc,
              "evidence": evidence, "reproduction": repro, "files": files, "affected_feature": feature,
              "requirement": req, "recommended_action": action, "estimated_effort": effort, "dependencies": deps,
              "status": status, "fix_commit": fix})


f("F-001", "build/demo", "P0", "confirmed", "Demo fixture is a dangling gitlink; every clone is empty",
  "examples/demo-repo was committed as a gitlink (160000) to 31b94fc with no .gitmodules and no reachable object. "
  "npm run setup / npm run demo fail with 'Demo source files are missing'; 5 backend tests fail or error; the Docker "
  "image copies an empty directory.",
  ["audit/evidence/startup-before.log", "clean clone: setup exit 1 after 455 s (08-runtime-startup.md)",
   "audit/evidence/pytest-before.log"],
  "git clone ...; npm run setup", "examples/demo-repo, scripts/setup_demo.py", "startup, demo, tests", "S2 P1, S1 C8",
  "Restore the 11 fixture sources (setup_demo rebuilds v2 == 31b94fc exactly); pin LF", "S", "", "FIXED", "b2ea145")
f("F-002", "benchmark", "P1", "confirmed", "E003 commit broke verify_retrieval for callers without dense_windows",
  "args.dense_windows read unconditionally: test_verify_retrieval (2 failed) and test_analyze_baseline (5 errors). "
  "Introduced by this engagement's own E003 commit 95953a4.",
  ["audit/evidence/pytest-before.log"], "pytest benchmark/test_verify_retrieval.py", "benchmark/verify_retrieval.py",
  "trust harness", "E1", "getattr with a None default", "XS", "", "FIXED", "41fcee0")
f("F-010", "tests", "P2", "confirmed", "investigation.spec.ts targets a removed UI",
  "6/6 tests fail on .result-card / nav 'Trace' selectors from a deleted component.",
  ["audit/evidence/playwright-before.log"], "npx playwright test investigation", "frontend/e2e/investigation.spec.ts",
  "E2E", "E3", "Replace with journeys against the current UI", "S", "", "FIXED", "46a3d28")
f("F-011", "retrieval/UX", "P1", "confirmed", "Nonsense queries presented as 'the relevant code'",
  "Dense retrieval always returns nearest neighbours (cosine 0.11-0.15 for 'qxzjvnonexistentidentifier'); the UI "
  "headed them 'Here's the relevant code'.",
  ["audit/evidence/api-probe.json (search nonsense)", "playwright-before audit spec failure"],
  "Ask 'qxzjvnonexistentidentifier'", "backend/app/agent/investigate.py, frontend/src/App.tsx", "search answer",
  "C1, product honesty", "Add match_basis; honest heading", "S", "", "FIXED", "c992b87, 4746151")
f("F-012", "tests", "P3", "confirmed", "Compare-copy test asserted the wrong text",
  "The copied 'Before' snippet is a method body without 'AuthService'; a later step used a removed control.",
  ["audit/evidence/playwright-before.log"], "npx playwright test audit.spec.ts:23", "frontend/e2e/audit.spec.ts",
  "E2E", "E3", "Compare with the displayed snippet; use the Chat button", "XS", "", "FIXED", "46a3d28")
f("F-013", "benchmark protocol", "P2", "confirmed", "Confirmation split used three times during BM25 tuning",
  "bm25-tuning-log.json records 3 confirmation runs (k1 1.6 twice, 1.5 once); the ledger requires confirmation once "
  "per candidate. The README also claimed the tuning scripts were never run.",
  ["benchmark/results/bm25-tuning-log.json"], "inspect the log", "benchmark/tune_bm25.py, README.md",
  "experiment protocol", "E2", "Record the breach; correct the README", "XS", "", "DOCUMENTED")
f("F-014", "retrieval/product", "P1", "confirmed",
  "Rejected E002 cross-encoder still reachable in the product; misleading availability flag",
  "ASTFLOW_RERANKER_ENABLED (undocumented) routed search through a model that lowered NDCG@10 by 0.0187 (CI "
  "excludes 0); CROSS_ENCODER_AVAILABLE=True was written into manifests.",
  ["benchmark/experiments/E002.json", "backend/app/retrieval/search.py at f0f2fc9"], "ASTFLOW_RERANKER_ENABLED=true",
  "backend/app/retrieval/search.py, reranker.py, config.py", "ranking", "mission section 21",
  "Remove from the product; reject unknown modes", "S", "", "FIXED", "aa14805")
f("F-015", "UX naming", "P2", "confirmed", "'Explain' implies generated explanations that do not exist",
  "Top-bar Explain toggled a panel; 'Explain this code' ran a search. Generation is out of S1 scope.",
  ["frontend/src/App.tsx at f0f2fc9"], "click Explain", "frontend/src/App.tsx", "companion", "C16",
  "Rename to Ask / Find related code", "XS", "", "FIXED", "4746151")
f("F-016", "API", "P3", "confirmed", "/docs and /redoc render blank",
  "Swagger/ReDoc scripts load from cdn.jsdelivr.net; the app's own CSP blocks them.", ["curl /docs"], "open /docs",
  "backend/app/main.py", "API docs", "P7", "Disable; keep /openapi.json", "XS", "", "FIXED", "dc0365a")
f("F-017", "API naming", "P3", "confirmed", "Agent step named RERANK although it only sorts scores", "",
  ["backend/app/agent/investigate.py"], "any search", "backend/app/agent/investigate.py", "investigation log",
  "mission section 21", "Rename to RANK", "XS", "", "FIXED", "dc0365a")
f("F-018", "architecture", "P3", "confirmed", "Two IndexService instances per CLI process",
  "main.py builds a module-level app at import; cli demo builds another.", ["04-architecture-current.md"],
  "python -m backend.app.cli demo", "backend/app/main.py, cli.py", "startup", "-",
  "Make the module-level app lazy or reuse it", "XS", "", "OPEN")
f("F-019", "performance", "P2", "confirmed", "Title field re-tokenised every chunk on every query; two unused corpus copies",
  "lexical_scores looped over all chunks tokenising qualified_name per query (91.2 ms/query on 8,765 docs).",
  ["scores bit-identical on 300 queries x 8,765 docs; 91.2 -> 1.9 ms/query"], "see commit message",
  "backend/app/retrieval/search.py", "search latency", "C15", "Precompute title tokens", "S", "", "FIXED", "4cac3a9")
f("F-020", "benchmark", "P1", "confirmed", "No MTEB artifact for the current code",
  "results/mteb, mteb-bm25, mteb-hybrid came from three older code states (0.089 / 0.06104 / 0.08815).",
  ["02-retrieval-baseline.md"], "-", "benchmark/results/", "submission artifact", "C3, C8",
  "Generate artifacts for the current code", "S", "F-036, F-042", "FIXED", "c42b78a")
f("F-021", "maintainability", "P2", "confirmed", "Frontend source written as very long single lines",
  "App.tsx lines up to 1,881 chars; studio.css up to 14,088; Semgrep could only partially parse two files.",
  ["06-static-analysis.md"], "measure line lengths", "frontend/src/*", "all UI", "-",
  "Format with a formatter in a dedicated no-behaviour-change commit", "S", "", "OPEN")
f("F-022", "build", "P2", "confirmed", "Trust-harness evaluators not declared as dependencies",
  "pytrec_eval / ir_measures imported but in no requirements file; a fresh MTEB venv fails 3 tests.",
  ["eval-venv pytest output"], "pip install -r benchmark/requirements-mteb.txt; pytest benchmark/test_verify_retrieval.py",
  "pyproject.toml, benchmark/requirements-mteb.txt", "reproducibility", "E1",
  "Pin the versions recorded in the baseline manifest", "XS", "", "FIXED", "8b6713c")
f("F-023", "graph", "P1", "confirmed", "Call graph essentially empty on real repositories",
  "Every call inside a nested function was rejected: express 12 edges / 3,120 callables (99.3% isolated), lodash "
  "20 / 4,463.",
  ["audit/evidence/graph-stats-before.json", "audit/evidence/resolver-nested-measure.json"],
  "index expressjs/express", "backend/app/structure/resolver.py", "Map, Trace, structural answers", "C10, C11, C14",
  "Resolve identifier calls from nested scopes via the scope-chain lookup; verify with the TS language service",
  "M", "", "FIXED", "52063cf")
f("F-024", "benchmark", "P3", "confirmed", "verify_retrieval recorded git state at the end of a run",
  "A 27-minute run recorded a commit made mid-run.", ["02-retrieval-baseline.md"], "-",
  "benchmark/verify_retrieval.py", "provenance", "E1", "Capture at start", "XS", "", "FIXED", "4e9622d")
f("F-025", "accessibility", "P1", "confirmed", "Critical ARIA violation in every view",
  "role=tablist contained close buttons (aria-required-children) in 21/21 crawled states.",
  ["audit/evidence/ui-crawl-before.json", "Lighthouse accessibility 0.87 before"], "axe", "frontend/src/App.tsx",
  "all views", "mission section 15", "Labelled group + aria-current", "XS", "", "FIXED", "4746151")
f("F-026", "accessibility", "P2", "confirmed",
  "Insufficient contrast (hints, captions, Monaco tokens, highlighted and diff lines)", "3.5-4.4:1 in 17/21 states.",
  ["audit/evidence/ui-crawl-before.json", "frontend/e2e/a11y.spec.ts"], "axe",
  "frontend/src/studio.css, frontend/src/components/SourceViewer.tsx", "all views", "mission section 15",
  "Raise to >= 4.5:1", "S", "", "FIXED", "4746151")
f("F-027", "UI", "P3", "confirmed", "favicon.ico 404 on every load", "Console error; Lighthouse best practices 0.96.",
  ["audit/evidence/lighthouse/before-desktop.json"], "load /", "frontend/index.html", "-", "-",
  "Inline SVG favicon", "XS", "", "FIXED", "4746151")
f("F-028", "benchmark provenance", "P2", "confirmed",
  "Baseline-v1 generated from an unpublished dirty commit; '5 evaluators' overstated",
  "manifest-baseline-v1 records commit 7df804f8 (not in the repository) with modified search.py/embeddings.py; the "
  "manifest shows 4 evaluators.",
  ["benchmark/verification/manifest-baseline-v1.json"], "inspect the manifest", "docs", "trust", "E1",
  "Reproduce from committed code (done: identical metrics, 0 per-query metric changes) and correct the docs", "S",
  "", "MITIGATED")
f("F-029", "graph", "P2", "confirmed", "No cross-file edges for CommonJS or member calls",
  "express/lodash cross_file_edges = 0 after F-023.", ["audit/evidence/graph-stats-after.json"],
  "index expressjs/express; open Map", "backend/app/structure/resolver.py", "Map overview", "C10, C14",
  "Conservative CommonJS require/exports resolution with a judged precision check", "L", "", "OPEN")
f("F-030", "graph UX", "P2", "confirmed", "Large-repository overview is a grid of unconnected boxes",
  "60 of 141 files, 0 edges at fit-to-screen zoom.", ["12-graph-audit.md"], "express instance, Map",
  "frontend/src/components/TraceGraph.tsx", "Map", "-", "Cluster by directory; show connected files first", "M",
  "F-029", "OPEN")
f("F-031", "graph UX", "P3", "confirmed", "Functions assigned to properties are labelled anonymous@L:C",
  "e.g. express res.cookie. A naming fix was prototyped and rejected (it hurt an 8-question retrieval probe).",
  ["audit/evidence/rejected-parser-heuristics.md"], "express Map", "backend/app/parsing/javascript.py",
  "Map labels, results", "-", "Use the property path as a display name only (not the BM25 title field) and evaluate",
  "S", "", "OPEN")
f("F-032", "UI", "P1", "confirmed", "Uncaught page error when leaving the Compare diff",
  "'TextModel got disposed before DiffEditorWidget model got reset' in 10 crawl interactions (all viewports).",
  ["audit/evidence/ui-crawl-before.json"], "Compare, then click a source link", "frontend/src/components/SourceViewer.tsx",
  "Compare", "-", "keepCurrentOriginalModel / keepCurrentModifiedModel", "XS", "", "FIXED", "4746151")
f("F-033", "responsive UX", "P2", "confirmed",
  "Companion drawer covers the Compare result and opened sources on narrow screens",
  "Controls intercepted at 768/390 px (Playwright: companion subtree intercepts pointer events).",
  ["audit/tools/diag.audit.ts output"], "768 px: run Compare", "frontend/src/App.tsx", "Compare, results on mobile",
  "-", "Do not auto-open over the diff; close the drawer when a link is chosen", "S", "", "FIXED", "4746151")
f("F-034", "UI", "P3", "confirmed", "Monaco CancellationError surfaced as an unhandled rejection on tab switch",
  "Pre-existing (reproduced on the old build).", ["diagnostic run on old and new builds"], "switch tabs quickly",
  "frontend/src/components/SourceViewer.tsx", "source viewer", "-", "Swallow only Monaco 'Canceled' rejections", "XS",
  "", "FIXED", "4746151")
f("F-035", "performance", "P3", "confirmed", "/api/versions spawns ~15 git processes per call",
  "P50 345 ms on the demo; called on every refresh.", ["audit/evidence/perf-api-before.json"], "GET /api/versions",
  "backend/app/indexing/discovery.py", "snapshot selector", "-", "Cache per refs state", "S", "", "OPEN")
f("F-036", "benchmark", "P1", "confirmed", "MTEB artifact scored a tie-broken order ASTFLOW never returns",
  "Raw RRF scores tie inside the top 10 for ~9% of queries; MTEB re-sorted ties: NDCG@10 0.089 / MRR@10 0.07338 vs "
  "0.0884 / 0.07257 for the actual order.",
  ["audit/evidence/mteb-hybrid-raw-rrf-scores", "benchmark/results/mteb-current-hybrid"], "run_mteb --mode hybrid",
  "benchmark/run_mteb.py", "official artifact", "C2, C3", "Emit rank-preserving scores (as the trust harness does)",
  "XS", "", "FIXED", "f0a88b3")
f("F-037", "performance", "P2", "confirmed", "plan() compiled one regex per symbol per query",
  "88% of search time on express (319 ms/query); 498 ms on lodash.",
  ["cProfile in the session log", "plan() outputs identical on 36 query/repository pairs"], "search on a large repo",
  "backend/app/agent/investigate.py", "search latency", "C15", "Substring pre-filter", "XS", "", "FIXED", "fb3e982")
f("F-038", "retrieval quality", "P2", "confirmed", "Test code crowds results on real repositories",
  "express: >= 4 test results in the top 5 for 4 of 8 hand-written questions; test/ directories are not detected as tests.",
  ["audit/evidence/rejected-parser-heuristics.md (probe ran lexical-only: model not in the scratch cache)"], "express instance", "backend/app/parsing/javascript.py, search.py",
  "search answers", "C1",
  "Detect test directories without adding test descriptions to the title field; evaluate on a judged set", "M", "",
  "OPEN")
f("F-039", "docs", "P2", "confirmed", "README claims contradicted by evidence",
  "Said the tuning scripts never ran (they did); local table produced without the model; the fixture was described "
  "as included (it was not); 'Explain' step; no mention of the reranker flag.",
  ["README.md at f0f2fc9"], "-", "README.md", "documentation", "mission section 34", "Correct the README", "S", "",
  "FIXED", "58fa778")
f("F-040", "CI", "P2", "confirmed", "No CI", "", ["no .github directory"], "-", ".github/workflows", "all", "E4",
  "Add PR validation and a manual benchmark workflow", "S", "", "FIXED (not yet run on GitHub)", "275fe27")
f("F-041", "deployment", "P3", "confirmed", "Docker image unverified", "Docker is not installed on the audit machine.",
  ["00-tooling-feasibility.md"], "docker build .", "Dockerfile", "container", "P6", "Build and run on a Docker host",
  "S", "external", "BLOCKED (external)")
f("F-042", "benchmark", "P2", "confirmed", "MTEB runs recorded no code provenance", "run_metadata.json had no commit.",
  ["benchmark/results/mteb*/run_metadata.json"], "-", "benchmark/run_mteb.py", "artifact provenance", "E1",
  "Record commit + dirty files at start", "XS", "", "FIXED", "3d47567")
f("F-044", "retrieval quality", "P1", "confirmed",
  "Retrieval accuracy on AppsRetrieval is low; candidate generation is the limit",
  "Hybrid NDCG@10 0.0884 (Recall@100 0.298); 65% of answers are in neither retriever's top 100; 89% of queries exceed "
  "the dense model's 256 word-pieces; median query/document vocabulary overlap 5.8%.",
  ["02-retrieval-baseline.md", "post-E003 audit"], "verify_retrieval / run_mteb", "retrieval", "retrieval",
  "C2 (P0 screening criterion)", "E004 (pre-registered, awaiting approval); E005 candidate (offline NL descriptions)",
  "L", "approval", "OPEN")

f("F-045", "performance", "P2", "confirmed", "rank() compiled one regex per candidate row",
  "The exact-symbol check built a case-insensitive boundary regex for up to 1,000 candidates per query: hybrid rank() "
  "84.6 ms (express) / 93.1 ms (lodash).",
  ["audit/evidence/perf-scale-before-f045.json", "audit/evidence/perf-scale.json"], "search on a large repo",
  "backend/app/retrieval/search.py", "search latency", "C15", "casefold substring pre-filter before the unchanged regex",
  "XS", "", "FIXED", "be291ba")
f("F-046", "graph", "P1", "confirmed", "Graph intermittently rendered invisible nodes / no edges",
  "After the canvas remounted, React Flow sometimes never measured nodes: nodes stayed hidden, then edges were never "
  "drawn (2 of 32 diagnostic traces; studio map test failed 3 of 12 repeats); the canvas also jumped once after "
  "render (two fits with different padding).",
  ["audit/tools/trace-edges.audit.ts results in 11-e2e / 12-graph-audit"], "Map -> file focus -> open source -> Trace",
  "frontend/src/components/TraceGraph.tsx", "Map, Trace", "C10", "fixed node size + declared handles; same fit padding",
  "S", "", "FIXED", "537233e")
f("F-047", "accessibility", "P3", "confirmed", "Heading levels skipped (h1 -> h3) in answer views",
  "axe heading-order (moderate) in 5 of 21 crawled states.", ["audit/evidence/ui-crawl.json (pre-fix)"], "axe",
  "frontend/src/App.tsx", "companion", "mission section 15", "companion title as h2", "XS", "", "FIXED", "89bb5da")

ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
F.sort(key=lambda x: (ORDER[x["severity"]], x["id"]))
summary = {}
for x in F:
    s = summary.setdefault(x["severity"], {"total": 0, "fixed": 0, "open": 0, "other": 0})
    s["total"] += 1
    head = x["status"].split()[0]
    s["fixed" if head == "FIXED" else "open" if head == "OPEN" else "other"] += 1
security = ["S-1 no authentication (local single-user tool, loopback only)",
            "S-2 absolute paths and raw git error text in responses",
            "S-3 git honours the target repository's config (no hooks run)",
            "S-4 CSP style-src 'unsafe-inline' (React Flow / Monaco)",
            "S-5 container process binds all interfaces inside the container"]
json.dump({"generated": "2026-09-25", "branch": "audit/master-remediation", "summary_by_severity": summary,
           "findings": F, "security_accepted": security},
          open("audit/findings.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps(summary))
print(len(F), "findings")

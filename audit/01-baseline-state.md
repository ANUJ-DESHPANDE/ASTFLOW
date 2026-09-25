# 01 · Baseline state (starting point of this audit)

Recorded 2026-09-25 before any production-code change.

## Git

| Item | Value |
|---|---|
| Starting branch | `exp/E004-long-query` (tracks `origin/exp/E004-long-query`) |
| Starting HEAD | `f0f2fc90953e2ba618bec44c1620359b9326e894` — "docs(e004): pre-register long-query dense representation experiment" |
| `origin/main` | `95953a4` (E003 result; E004 pre-registration is one commit ahead on its branch) |
| Remote | `origin https://github.com/ANUJ-DESHPANDE/ASTFLOW` (fetch/push) |
| Other remote branches | `codex/theme1-audit`, `github-original`, `claude/optimistic-cori-rhcy47`, `exp/E002-reranker`, `exp/E003-dense-windows`, `exp/E004-long-query` |
| Uncommitted tracked changes | none |
| Untracked | `ASTFLOW-main/` — leftover of the pre-restructure layout (contains an old `.venv`, `node_modules`, `.astflow` and the demo fixture's nested Git history with working files deleted). **Preserved, never modified.** |
| Stashes | none |
| Audit branch | `audit/master-remediation`, created from `f0f2fc9`. Local only; nothing pushed. |

To reproduce the starting tree: `git checkout f0f2fc90953e2ba618bec44c1620359b9326e894`.

## Environment

See `00-tooling-feasibility.md` for hardware/OS/network. Toolchains: Python 3.12.4 (`.venv`), Node v24.19.0,
npm 11.17.0, Git 2.55.0, Playwright 1.63.0 (Edge 153 channel). Docker: not installed.

Python packages in `.venv` (relevant subset): fastapi 0.141.1, uvicorn 0.53.0, pydantic 2.13.5, tree-sitter 0.25.2,
tree-sitter-javascript 0.25.0, networkx 3.6.1, rank-bm25 0.2.2, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1,
typer 0.27.2, sentence-transformers 5.7.0, transformers 5.17.0, torch 2.14.0+cu130 (lock: 2.14.0 CPU),
datasets 5.0.1, pytest 9.1.1, httpx 0.28.1, pytrec_eval-terrier 0.5.10, ir_measures 0.4.3.
Audit-only tools (not project dependencies): ruff 0.16.8, vulture 2.16, mypy 2.3.1, semgrep 1.178.0,
pip-audit 2.10.1, coverage 7.16.1 / pytest-cov.

Node dependencies: installed with `npm ci` from the committed lock (18 s, **0 vulnerabilities**). npm 11 reports
esbuild's postinstall as not approved; the build works regardless (platform binary package present).

## Starting quality signals (before any change)

| Check | Result | Evidence |
|---|---|---|
| `npm run build` (tsc -b + vite) | PASS in 49 s; warning: `SourceViewer` chunk 3.69 MB (Monaco, lazy-loaded) | `evidence/build-before.log` |
| Python tests (`backend/tests` + `benchmark`, MTEB module excluded) | **90 tests: 76 passed, 6 failed, 7 errors, 1 skipped** | `evidence/pytest-before.xml`, `evidence/pytest-before.log` |
| `benchmark/test_mteb_adapter.py` | collection error: `mteb` not installed in `.venv` (it belongs to the separate `.eval-venv`, per README) | same log |
| Coverage (backend + benchmark) | 59% of 4,718 statements | `evidence/coverage-before.json` |
| Playwright (existing 26 tests, live backend) | **18 passed, 8 failed** | `evidence/playwright-before.log` |
| `npm run demo` (documented startup) | **FAIL** after 12 s: `RuntimeError: Demo source files are missing` | `evidence/startup-before.log` |
| Clean clone → `npm run setup` (documented install) | **FAIL** after 455 s at `scripts/setup_demo.py` (same error); venv, npm ci and build succeed first | scratch clone log, summarized in `08-runtime-startup.md` |
| Ruff | 116 findings (36 unused imports, 30 import order, 15 loop-variable closures in benchmark scripts, …) | `evidence/ruff.txt` |
| mypy (`--ignore-missing-imports`) | 27 errors, mostly Optional narrowing / missing annotations | `evidence/mypy.txt` |
| Semgrep (324 rules) | 1 finding (`child_process` in `scripts/setup.mjs`, fixed args); 2 partial-parse errors on very long frontend lines | `evidence/semgrep.json` |
| pip-audit (lock, 75 packages) | 0 known vulnerabilities | `evidence/pip-audit.json` |
| npm audit | 0 vulnerabilities | `evidence/npm-audit.json` |

## Root causes of the starting failures (details in findings.json)

1. **F-001 (P0):** `examples/demo-repo` is a gitlink to commit `31b94fc` with no `.gitmodules` and no reachable
   object, so every clone gets an empty directory. Breaks setup, the demo and 5 backend tests.
2. **F-002 (P1, introduced by E003 commit `95953a4` in this same engagement):** `verify_retrieval.full_run` read
   `args.dense_windows` unconditionally; tests that build their own `Namespace` failed (2 failed + 5 errors).
3. Six Playwright failures target a removed UI (`.result-card`, a "Trace" nav button) — stale tests (F-010).
4. One Playwright failure is a real product defect: a nonsense query returns 10 dense-only results under
   "Here's the relevant code" (F-011).
5. One Playwright failure (compare copy) is under investigation (F-012).

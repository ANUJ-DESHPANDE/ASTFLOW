# 00 · Tooling feasibility (audit of the mission prompt itself)

Date: 2026-09-25 · Auditor: Claude (Opus 5.5) · Branch `audit/master-remediation`

The mission prompt names many tools. Each was checked against what this repository and machine actually are.
Only tools that add independent evidence are used.

## What the repository and machine are (measured)

| Item | Finding | Evidence |
|---|---|---|
| OS | Windows 11 Home 10.0.26200, Git Bash + PowerShell 5.1 | `Get-CimInstance Win32_OperatingSystem` |
| CPU / RAM | Intel i7-14650HX, 16 cores / 24 threads; 15.7 GB RAM (≈5 GB free at audit start) | `Win32_Processor`, `Win32_ComputerSystem` |
| GPU | NVIDIA RTX 4060 Laptop, 8 GB, driver 592.82 | `nvidia-smi` |
| Disk | C: 953 GB, 628 GB free | `df -h` |
| Network | github.com, huggingface.co, registry.npmjs.org all reachable (HTTP 200) | `curl` |
| Languages | Python 3.12 (backend, benchmark, scripts), TypeScript/React (frontend), one Node tool (`tools/ts_enrich.mjs`) | `git ls-files` (221 tracked files: 78 .py, 9 .ts, 7 .tsx) |
| Backend | FastAPI 0.141 + Uvicorn, Pydantic 2, Typer CLI, SQLite + NumPy persistence, tree-sitter-javascript, NetworkX, rank-bm25, sentence-transformers (optional) | `pyproject.toml`, `backend/app/*` |
| Frontend | React 19, Vite 7, TypeScript 5.9, @xyflow/react (graph), Monaco (source/diff), lucide icons | `frontend/package.json` |
| Package managers | pip (+ `requirements.lock.txt` constraints), npm 11 workspaces (`package-lock.json`) | root `package.json` |
| Python env | `.venv` Python 3.12.4 (created this session; torch 2.14.0+cu130 installed for E002 GPU runs; lock pins CPU torch 2.14.0) | `pip list` |
| Node | v24.19.0 (README requires 22.12+) | `node --version` |
| Tests | pytest (backend/tests, benchmark/test_*.py); Playwright 1.63 with Edge channel (`frontend/e2e/*.spec.ts`) | `pyproject.toml`, `playwright.config.ts` |
| Benchmark infra | Frozen-run trust harness (`benchmark/verify_retrieval.py`, `benchmark/trust/*`), MTEB runner (separate `.eval-venv`), E001–E004 ledger | `benchmark/EXPERIMENTS.md` |
| CI/CD | **None** (no `.github/`, no other CI config) | `ls .github` |
| Docker | `Dockerfile` + `.dockerignore` present; **Docker is not installed on this machine** | `docker --version` → not found |
| Models | `sentence-transformers/all-MiniLM-L6-v2` cached in `.astflow/models` (weights SHA-256 `1377e9af…`, matches baseline-v1 manifest); cross-encoder `ms-marco-MiniLM-L-6-v2` in HF cache (E002) | `sha256sum`, manifests |
| Dataset | CoIR-Retrieval/apps revision `f22508f9…` exported to `.astflow/datasets/apps` | `metadata.json` |
| Browsers | Microsoft Edge 153 and Google Chrome installed | `Program Files` |

## Tool decisions

| Tool (named in prompt) | Decision | Why |
|---|---|---|
| pytest (+ pytest-cov / coverage.py) | **USE** | Native test framework; coverage measures what is exercised. |
| Playwright | **USE** | Already the project's E2E framework (Edge channel); drives the real backend. |
| Ruff | **USE** (installed in `.venv` only) | Fast Python linter covering pyflakes/bugbear/etc.; replaces several overlapping linters. |
| mypy | **USE WITH MODIFICATION** | Code is mostly untyped; run with `--ignore-missing-imports` for real type bugs only, not as a gate. |
| pyright | **REDUNDANT** | Overlaps mypy; adds no independent evidence here. |
| TypeScript compiler (`tsc -b`) | **USE** | Already runs in `npm run build`; strict type check of the frontend. |
| ESLint | **NOT APPLICABLE (not configured)** | No ESLint config or dependency exists; `tsc` strict build is the existing gate. Adding an ESLint stack now would be new tooling without a demonstrated defect it would catch. |
| Vulture | **USE** (evidence only) | Dead-code hints; every hit verified by hand (FastAPI/Typer decorators are false positives). |
| Semgrep | **USE** (`p/python`, `p/security-audit`, `p/secrets`, `p/typescript`, `p/react`, metrics off) | Independent security/code rules. Runs on Windows (1.178). |
| SonarQube | **REPLACE WITH BETTER TOOL** | Requires a server/JVM; for a 221-file repo Ruff + Semgrep + mypy + tsc cover the same classes of issues offline. |
| CodeQL | **NOT APPLICABLE (now)** | Requires GitHub code scanning or the CodeQL CLI + database build; Semgrep taint rules cover the relevant flows for this size. Recommended for CI later. |
| dependency-cruiser | **REDUNDANT** | Frontend is 12 source files with a flat import graph (`App.tsx` → 6 components). Manual trace is exact. |
| pip-audit | **USE** | Known-vulnerability check of the locked Python set. |
| npm audit | **USE** | Known-vulnerability check of the npm lock. |
| axe-core (`@axe-core/playwright`) | **USE** | Accessibility rules inside the existing Playwright runs. |
| Lighthouse | **USE WITH MODIFICATION** | Run ad hoc via `npx lighthouse` against the local build (Chrome installed); not added as a dependency. |
| Third-party "UI/UX audit" repositories | **NOT APPLICABLE** | None identified that add value beyond axe + Lighthouse + Playwright screenshots; not installed. |
| MTEB | **USE WITH MODIFICATION** | Only in the separate evaluation environment the README prescribes; the frozen trust harness is the authoritative path for experiments (E001–E003). |
| Docker build/run | **INCOMPATIBLE (on this machine)** | Docker not installed. Documented as UNVERIFIED, not claimed. |
| Hugging Face downloads | **USE** | Network available; model weights verified by SHA-256 against the baseline manifest. |

## Consequences for the mission

- Docker verification cannot be performed here; it stays UNVERIFIED.
- CI must be added from scratch (none exists).
- "Reranked" retrieval mode: the UI has **no retrieval-mode selector**; the only `reranked` path is benchmark-only
  and off by default (see 05-feature-inventory).
- BM25 tuning / document expansion / reranker experiments are governed by `benchmark/EXPERIMENTS.md` rules
  (pre-registration, dev → confirmation once). E004 was pre-registered and then cancelled for now by the project owner (2026-09-25); pre-registration kept in the ledger, not run.

# 10 · API audit

Every route in `backend/app/main.py` was enumerated (no routers elsewhere; `openapi.json` lists the same set) and
exercised live by `audit/tools/api_probe.py` (66 cases; raw responses in `evidence/api-probe.json`). All cases
returned the expected status both before and after remediation; the only intended change is `/docs` → 404.

| Method | Path | Request schema | Frontend caller | Validation / errors verified | Tests |
|---|---|---|---|---|---|
| GET | `/api/health` | — | none (scripts, CI health wait) | always 200; reports model status | `test_api_versions`, probe |
| GET | `/api/repository?version=` | query `version` (optional) | `refresh()`, version switch, startup | unknown version → 200 with base repository (files for the requested snapshot only when indexed) | probe |
| GET | `/api/versions` | — | `refresh()` | runs ~15 `git` subprocesses per call (P50 345 ms on the demo) — F-035 | probe, perf |
| POST | `/api/index` | `IndexRequest{repo_path 1–4096, version 1–200, background}` (`extra=forbid`) | reindex, repository dialog, "Update snapshot" | missing path → 422; nonexistent → 404; file not dir → 400; bad revision → 400 with git message; `--output=…` → 400 "Invalid Git revision"; concurrent → 409; background → 202 | probe, `test_audit_reliability`, E2E dialog journey |
| GET | `/api/index/status` | — | 1 s poll while indexing | reports stage/progress/error | probe, E2E reindex |
| POST | `/api/search` | `SearchRequest{query 1–2000 non-blank, version, top_k 1–50, agentic, runtime_trace_id}` | ask, "Find related code", version switch | blank/missing/wrong type/extra field (e.g. `mode`) → 422; 2001 chars → 422; unindexed/unknown version → 400; runtime trace → 400; response now carries `match_basis` | probe, `test_api_contract`, `test_core`, E2E |
| POST | `/api/trace` | `TraceRequest{source, target 1–1000, version, max_depth 1–8}` | Trace | depth 9 → 422; unknown symbols → 200 `NO_STATIC_PATH_FOUND`; ambiguous → `AMBIGUOUS_SYMBOL` | probe, `test_core` |
| GET | `/api/source?path&version&start_line&end_line` | query | opening files, results, evidence links, diff | traversal/absolute/backslash → 400; not in snapshot → 404; range outside/end<start → 400; start 0 → 422; unindexed version → 400 | probe, `test_api_versions` |
| GET | `/api/map?version&file&symbol&depth` | query, depth 1–3 | Map view | unknown file/symbol → 404; depth 4 → 422; ≤ 150 nodes with `SEARCH_LIMIT_REACHED` | probe, E2E map |
| GET | `/api/checkpoint` | — | 15 s poll on the working tree | re-hashes the working tree at most every 10 s | probe |
| POST | `/api/compare` | `CompareRequest{query, version_a, version_b}` | Compare | missing field → 422; unindexed → 400; same version → 200 (empty diff) | probe, `test_api_versions`, E2E |
| GET | `/api/symbol/{id:path}` | path | **none** (documented API for tools; used by tests and `scripts/audit_api.py`) | unknown → 404 | probe, `test_api_versions` |
| GET | `/openapi.json` | — | — | 200 | probe, `test_api_contract` |
| GET | `/docs`, `/redoc` | — | — | **were 200 but blank** (CDN scripts blocked by CSP) → now 404 (F-016) | `test_api_contract` |
| GET | `/`, `/assets/*` | — | browser | SPA entry + hashed assets | E2E |

## Cross-cutting behaviour (verified)

- Host allow-list → 400; foreign `Origin` → 403; `Sec-Fetch-Site: cross-site` → 403; non-JSON POST → 415; body > 16 KB →
  413 (streamed, rejected before parsing); malformed JSON → 422; security headers on every response (see 15-security).
- Error bodies are `{detail}`; the frontend maps network failure, non-JSON (e.g. a 502 HTML page) and 422 to distinct
  user messages (E2E "API network failure, malformed reply…" passes).
- No frontend call targets a nonexistent endpoint (every `request()` path above exists). Unused by the frontend:
  `/api/symbol/{id}` (kept: documented, tested) and `/api/health` (used by scripts/CI).

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| F-011 | P1 | Dense-only nearest neighbours returned for nonsense queries without any signal that they share no evidence | Fixed: `match_basis` in the response (`c992b87`) + honest UI heading (`4746151`) |
| F-016 | P3 | `/docs`, `/redoc` served blank pages | Fixed (`dc0365a`) |
| F-017 | P3 | Agent step named `RERANK` although no reranking model exists | Fixed → `RANK` (`dc0365a`) |
| F-035 | P3 | `/api/versions` spawns ~15 git processes per call (345 ms demo P50); called on every refresh | Open (cache per HEAD/tag state) |
| S-2 | P3 (accepted) | Absolute paths and raw git error text in responses | Local single-user tool; documented |

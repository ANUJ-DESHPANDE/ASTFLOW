# 15 · Security

Scope: a **single-user local tool** that binds to 127.0.0.1, reads repositories the user points it at, and serves a
browser UI. Scanner output is evidence, not a verdict; every item below was checked in code and, where possible,
exercised against the running server (`audit/tools/api_probe.py` → `evidence/api-probe.json`, 66/66 cases as expected).

## Automated

| Tool | Result |
|---|---|
| Semgrep (python, security-audit, secrets, typescript, react; 324 rules) | 1 finding, false positive (fixed-argument `spawnSync` in `scripts/setup.mjs`) |
| pip-audit (75 locked Python packages) | 0 known vulnerabilities |
| npm audit (lockfile) | 0 vulnerabilities (also after adding `@axe-core/playwright`) |
| Secrets scan (Semgrep `p/secrets`) + manual `git grep` for tokens/keys | none found; no `.env` committed (`.env.example` only) |

## Boundary controls — verified at runtime

| Control | Evidence | Result |
|---|---|---|
| Loopback bind | `cli.serve`/`demo` use `host="127.0.0.1"` | OK |
| Host header allow-list (DNS rebinding) | `Host: evil.example` → 400 | OK |
| Cross-origin API use | `Origin: https://evil.example` → 403; `Sec-Fetch-Site: cross-site` → 403; Vite dev origin allowed | OK |
| JSON-only POST (blocks form/CSRF simple requests) | `text/plain` → 415 | OK |
| Body size cap | 20 KB body → 413 | OK |
| Input validation | blank/missing/wrong type/extra fields → 422 (`extra='forbid'`); bounds on `top_k`, `max_depth`, `depth`, lengths | OK |
| Source path traversal | `../../README.md`, `/etc/passwd`, backslash → 400; drive path / file not in snapshot → 404 | OK — only files stored in the index snapshot are ever served |
| Git argument injection | revision `--output=/tmp/x` → 400 "Invalid Git revision"; `--end-of-options`; list-form `subprocess` | OK |
| Security headers | CSP `default-src 'self'; script-src 'self'; … frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `no-store` on every response | OK |
| Deserialization | `np.load(..., allow_pickle=False)` everywhere; SQLite + JSON only | OK |
| XSS | frontend has 0 `dangerouslySetInnerHTML`/`innerHTML`/`eval`; all content rendered as React text; Monaco read-only | OK |
| Repository content is never executed | discovery reads bytes; TS enrichment parses in memory (`tools/ts_enrich.mjs`); no `npm install`, no tests run | OK |
| Symlinks / junctions / escapes | skipped; `resolve().is_relative_to(repo)` check | OK |
| Resource limits | 1 MB per file, 50 MB total, 20,000 files; 60/120 s git timeouts; 45 s TS timeout | OK |

## Findings

| ID | Severity | Finding | Evidence | Recommendation |
|---|---|---|---|---|
| F-016 | P3 | `/docs` (Swagger UI) is still served but loads its scripts from `cdn.jsdelivr.net`, which the app's own CSP blocks → blank page; `/redoc` likewise | `curl /docs` shows jsdelivr URLs + `script-src 'self'` | Disable `docs_url`/`redoc_url`; keep `/openapi.json` (README already documents only that) |
| S-1 | P3 (accepted) | No authentication: any process on the same machine can call the API and index any readable local directory | by design ("single-user local prototype", README) | Keep loopback-only; document; never bind `0.0.0.0` outside the container |
| S-2 | P3 (accepted) | `/api/repository` and index manifests expose absolute local paths; `ValueError` messages (e.g. git stderr) are returned verbatim | `api-probe.json` ("fatal: Needed a single revision") | Acceptable for a local tool; would need sanitising for any shared deployment |
| S-3 | P3 | Git commands run inside the *target* repository and honour its `.git/config`. The commands used (`rev-parse`, `ls-tree`, `cat-file`, `tag`, `log`) do not run hooks or refresh the index, and Git ≥ 2.35.2 refuses repositories owned by another user (`safe.directory`) | code review, `discovery.py` | Document: only index repositories you would open in your own Git client |
| S-4 | P3 | CSP allows `style-src 'unsafe-inline'` | header | Required by React Flow/Monaco inline styles; no script injection path; accepted |
| S-5 | info | Container listens on all interfaces inside the container (`container_start.py`) | README | Publish only to host loopback (`-p 127.0.0.1:8000:8000`) as the README says; Docker unverified here |

No P0/P1 security defects were found. "Zero scanner findings" is **not** the basis of this conclusion; the runtime
probes and code review above are.

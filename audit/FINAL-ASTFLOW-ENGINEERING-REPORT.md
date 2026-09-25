# ASTFLOW — Final engineering report (audit, verification, remediation)

Date 2026-09-25 · Branch `audit/master-remediation` (local, not pushed) · started from `f0f2fc9`.
Every claim below links to evidence under `audit/` (documents `00`–`18`, `findings.json`, `evidence/`).

## Executive summary

ASTFLOW is a local, CPU-only code-retrieval and repository-investigation tool for JavaScript (FastAPI + React), plus a
rigorous retrieval-evaluation harness for the CoIR AppsRetrieval screening benchmark. At the start of the audit it
**could not be installed from a clone** (the demo fixture was a dangling gitlink), 13 of 90 Python tests and 8 of 26
browser tests failed, the call graph was essentially empty on real repositories, the UI presented nonsense-query
results as "the relevant code", a retrieval component measured as harmful was still reachable, and the official MTEB
artifacts did not correspond to the current code.

After 22 small, evidence-backed commits: clean clone → `npm run setup` → demo works; **96** Python tests pass
(1 skipped by design), **28/28** browser tests (6 new demo-critical journeys + an accessibility gate), **66/66** API
probe cases; **0** console errors and **0** serious/critical axe violations across 326 exercised controls in 21
UI states; Lighthouse accessibility **1.00** (was 0.87); the call graph on real repositories has 20–65× more edges,
all independently confirmed by the TypeScript language service; search on real repositories is ~3× faster with
bit-identical rankings; the frozen retrieval baseline was **re-generated from committed code** with 0 per-query metric
changes, and official MTEB artifacts for the current code now match it exactly.

What is **not** solved: retrieval accuracy itself (Hybrid NDCG@10 0.0884; 65% of answers are not in either retriever's
top 100). The evidence points at candidate generation (query truncation, vocabulary mismatch); E004 was pre-registered
and then cancelled for now by the owner. CommonJS cross-file edges, directory clustering in the graph overview and a code formatter
pass are the main remaining engineering items. Docker could not be verified (not installed here).

## Starting state (`01-baseline-state.md`)

Clean tree at `f0f2fc9` (plus the untracked `ASTFLOW-main/` leftover, untouched). Python tests 76 pass / 6 fail /
7 error / 1 skip; Playwright 18/26; `npm run demo` and a clean-clone `npm run setup` both failed; coverage 59%;
no CI; Docker not installable here.

## Verified requirements (`03-requirements-matrix.md`)

Primary source: the Samsung PRISM Theme 1 reference PDF found on the machine (the original guideline PDFs cited by the
earlier matrix are not present). 16 competition requirements traced: 7 verified, 8 partial (mostly quality/scope:
accuracy, agentic refinement benefit, structural envelope, code-aware embeddings, submission assets), 1 missing (bonus
evolutionary retrieval).

## Architecture before / after (`04`, `17`)

Single process; content-addressed snapshots (SQLite + NumPy); BM25 + MiniLM + RRF; bounded agent; conservative
resolver + NetworkX; React studio. The target keeps this design (no rewrite is justified). Changes made: reranker
removed from the product path; resolver handles nested-scope identifier calls; three hot paths de-quadratified; MTEB
adapter scores the product's real order. Target additions (not done): CommonJS resolution, graph clustering, cached
`/api/versions`.

## Feature inventory before / after (`05-feature-inventory.md`)

Before: 2 broken (setup/demo, `/docs`), 3 misleading/harmful (no-evidence answers, reranker flag, "Explain"),
5 partial. After: 22 working, 0 broken, 2 removed (reranker path, blank docs pages), 1 missing (bonus), 1 unverified
(Docker).

## Bugs, dead code, duplicates, fake/stub features

39 findings in `findings.json` (P0 1 · P1 10 · P2 17 · P3 11); 28 fixed, 3 documented/mitigated/blocked, 8 open.
Dead code confirmed and removed: `reranker.py` + 5 settings + the Retriever branch, `CROSS_ENCODER_AVAILABLE`,
unused `corpus_title`/`corpus_text`, unused `deepcopy` import, obsolete `investigation.spec.ts` (`07-dead-code.md`).
Vulture's other hits were framework registrations (false positives). Fake/alias features: a "reranked" mode that would
silently alias hybrid (now rejected explicitly), the harmful reranker flag (removed), "RERANK" log label (now "RANK"),
"Explain" naming (now "Ask"). Stubs honestly reported: runtime tracing (400), `runtime/` package.

## Security (`15-security.md`)

No P0/P1 security defects. Verified at runtime: loopback bind, Host allow-list, cross-origin and cross-site blocking,
JSON-only POST, 16 KB body cap, traversal-safe source API, git-argument-injection guard, CSP and security headers,
no pickle loading, no HTML sinks in the UI. Semgrep: 1 false positive; pip-audit and npm audit: 0 vulnerabilities.
Accepted for a single-user local tool: no auth, absolute paths/raw git errors in responses, target repo git config
honoured, `style-src 'unsafe-inline'`.

## Performance (`14-performance.md`)

In-process search P50/P95 (semantic on): demo 6/13 ms; express 135/174 → **43/50 ms**; lodash 158/205 → **54/76 ms**.
Fixes were proven output-identical (bit-identical scores, identical plans, identical rankings). Cold indexing is
embedding-bound (express 38.6 s, lodash 97.5 s on CPU); cached re-index ≤ 1.9 s; RSS 0.95–1.26 GB. `/api/versions`
≈ 350 ms remains (F-035). One measurement error of my own (lexical-only runs caused by a fresh cache without the model)
was caught and corrected before use.

## UI/UX and accessibility (`09`, `13`)

Crawl of every reachable control in 21 state × viewport combinations: 312 visible effects, 0 console errors (was 10),
0 not-found (was 44), 9 explained non-defect rows. axe critical 21 → 0, serious 17 → 0, moderate 24 → 0.
Lighthouse accessibility 0.87 → 1.00 (desktop and mobile), best practices 0.96 → 1.00. Narrow-screen drawer behaviour
fixed. Remaining UX: graph overview at scale (F-030), companion cognitive load, real-repo result quality (F-038).

## Graph (`12-graph-audit.md`)

Edges: express 12 → 284, lodash 20 → 1,336 (1,820 added call-site edges, 100% TS-confirmed); isolated nodes
99.3% → 90.8% and 99.4% → 77.5%. Intermittent invisible nodes / missing edges fixed (0/32 failures after `537233e`).
Cross-file edges in CommonJS repositories remain 0 (F-029).

## Retrieval (`02-retrieval-baseline.md`, `benchmark/EXPERIMENTS.md`)

| System (AppsRetrieval test, 3,765 queries) | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | Status |
|---|---|---|---|---|---|---|
| BM25 (baseline-v1, reproduced; = MTEB current) | 0.06312 | 0.05421 | 0.09216 | 0.16866 | 0.22603 | verified |
| Dense (baseline-v1, reproduced) | 0.06596 | 0.05581 | 0.09907 | 0.19389 | 0.25259 | verified |
| Hybrid (baseline-v1, reproduced; = MTEB current) | **0.08840** | 0.07257 | 0.13971 | 0.23400 | 0.29774 | verified (product) |
| E001 best fusion (all) | 0.08845 | — | — | — | — | REJECT |
| E002 cross-encoder d20 (all) | 0.06972 | 0.05274 | 0.12590 | — | — | REJECT |
| E003 dense windows, Hybrid (all) | 0.08932 | 0.07338 | 0.14130 | — | 0.29880 | REJECT |

Only measured systems are listed. The final (product) system is the reproduced Hybrid. BM25 tuning had already been
done (confirmation split used three times — recorded); document expansion is supported by the vocabulary-mismatch
measurement but needs generated descriptions (E005 candidate, not built); the reranker was measured and removed.
No dev scores are presented as final scores.

## Tests (final run)

Python 96 passed / 1 skipped (MTEB module runs in the eval venv: 7/7); backend coverage 82.9% → 87.3% (retrieval
85.0%, API 87.8%, structure 91.8%, parsing 97.5%, agent 93.9%, indexing 86.0%). Playwright 28/28. API probe 66/66.
Evaluator self-test PASS. Clean clone: `npm run setup` exit 0 (577 s), demo healthy in 13 s, 15/16 browser tests on the
fresh clone before the graph fix, 28/28 on the final build.

## Remaining limitations / known issues / future work

Open, in order (`18-remediation-plan.md`): F-044 retrieval accuracy (E004 pre-registered but cancelled for now; E005 candidate —
needs a model/licensing decision), F-029 CommonJS edges, F-038 tests crowding real-repo results, F-030 graph overview
clustering, F-021 formatter pass, F-035 cached versions, F-031 display names, F-018 duplicate app instance, F-041
Docker verification. CI workflows were added but have not run on GitHub (no push authorisation).

---

## Dashboard

```
ASTFLOW PROJECT STATE
Commit: see `git log -1` on audit/master-remediation (22 commits after f0f2fc9; not pushed)
Branch: audit/master-remediation
Date: 2026-09-25

Build: PASS (tsc -b + vite build; Monaco chunk size warning only)

Tests
  Unit+Integration (pytest backend/tests + benchmark): 96 passed, 1 skipped, 0 failed
  MTEB adapter + harness (eval venv): 7 passed
  API (live probe): 66/66 as expected
  E2E (Playwright, live backend): 28 passed, 0 failed (6 journeys, 2 a11y, 20 studio/audit)
  Total: 197 checks · Passed: 197 · Failed: 0

UI
  Controls discovered: 1,094 visible control instances across 21 states/viewports (326 unique interactions)
  Controls tested: 326 · Passed: 317 (312 effect + 2 expected no-op + 3 correctly disabled) · Failed: 0
  Partial: 9 (explained: Monaco internal input 6, open narrow-screen drawer 3) · Unreachable: 0

Accessibility
  Lighthouse: 100 desktop / 100 mobile (was 87)
  axe critical: 0 (was 21) · axe serious: 0 (was 17)

Static analysis
  Critical: 0 · High: 0 · Medium: 0 (mypy 27 typing notes, no runtime bug) · Low: 108 ruff style/lint notes
Security
  Critical: 0 · High: 0 · Medium: 0 · Low: 5 accepted (local single-user tool)
Dead code
  Confirmed: 6 removed · Suspected: 1 (unused import in a test)
Features
  Working: 22 · Partial: 0 · Broken: 0 · Missing: 1 (bonus) · Removed: 2 · Unverified: 1 (Docker)

Retrieval (AppsRetrieval test, 3,765 queries; frozen harness = MTEB 2.21.0 on current code)
  BM25:   NDCG@10 0.06312  MRR@10 0.05421  R@10 0.09216  R@50 0.16866  R@100 0.22603
  Dense:  NDCG@10 0.06596  MRR@10 0.05581  R@10 0.09907  R@50 0.19389  R@100 0.25259
  Hybrid: NDCG@10 0.08840  MRR@10 0.07257  R@10 0.13971  R@50 0.23400  R@100 0.29774
  Final:  = Hybrid (E001–E003 rejected; E004 cancelled for now)

Performance (CPU, semantic on)
  Startup: demo healthy 13 s from a fresh clone (model load 8.4 s when cold)
  Indexing: demo 0.6 s · express 38.6 s · lodash 97.5 s (cached ≤ 1.9 s)
  Search P50: 6 ms demo · 43 ms express · 54 ms lodash
  Search P95: 13 ms demo · 50 ms express · 76 ms lodash
  Graph P95: map 18–23 ms · trace 27 ms (demo, HTTP)

P0 Remaining: 0
P1 Remaining: 1 (F-044 retrieval accuracy — experiment-gated)
Known blockers: Docker not installed (F-041); CI first runs on GitHub with this push; E004 cancelled for now

Next recommended action: check the first CI run on GitHub, then implement F-029
(CommonJS resolution) with TS-corroboration precision checks.

Exact commands to reproduce validation
  npm ci && npm run build
  .venv/Scripts/python.exe scripts/setup_demo.py
  .venv/Scripts/python.exe -m pytest backend/tests benchmark --ignore=benchmark/test_mteb_adapter.py -o addopts="" -q
  .venv/Scripts/python.exe -m benchmark.verify_retrieval --self-test
  npm run demo            # in another terminal
  .venv/Scripts/python.exe audit/tools/api_probe.py
  npx playwright test     # PLAYWRIGHT_CHANNEL=chromium off Windows
  npx playwright test -c audit/tools/playwright.audit.config.ts ui-crawl   # full control crawl (~25 min)
  .eval-venv/Scripts/python.exe benchmark/run_mteb.py --mode hybrid --output out/mteb-hybrid
```

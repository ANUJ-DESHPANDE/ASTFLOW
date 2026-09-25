# 06 · Static analysis

Raw outputs: `audit/evidence/{ruff.txt, mypy.txt, vulture-60.txt, semgrep.json, pip-audit.json, npm-audit.json, build-before.log}`.
Tool choices and rejected tools: `00-tooling-feasibility.md`.

## Summary (starting state, commit `f0f2fc9`)

| Tool | Scope | Findings | True positives worth acting on |
|---|---|---|---|
| `tsc -b` (strict, via `npm run build`) | frontend | 0 errors | — |
| Ruff 0.16.8 (default rules) | backend, benchmark, scripts | 116 | see table below |
| mypy 2.3.1 (`--ignore-missing-imports`) | backend | 27 | 0 confirmed runtime bugs (Optional narrowing where the code already guards; missing local annotations) |
| Vulture 2.16 (≥60%) | backend, scripts | 29 | 5 (see 07-dead-code) |
| Semgrep 1.178 (324 rules: python, security-audit, secrets, typescript, react) | backend, benchmark, scripts, tools, frontend/src | 1 finding, 2 partial-parse errors | 0 |
| pip-audit 2.10 | `requirements.lock.txt` (75 pins) | 0 known vulnerabilities | — |
| npm audit | `package-lock.json` | 0 vulnerabilities | — |

## Ruff — classification of the non-cosmetic rules

| Rule (count) | Where | Classification | Action |
|---|---|---|---|
| F401 unused-import (36) | mostly benchmark/tests; `investigate.py: deepcopy`; `search.py: sentence_transformers` | TRUE POSITIVE (cosmetic, except `search.py` — the import only exists to set the misleading `CROSS_ENCODER_AVAILABLE = True`) | Remove the product ones with F-014 |
| I001 unsorted-imports (30) | everywhere | TRUE POSITIVE, cosmetic | Not changed (style-only churn) |
| B023 loop-variable closure (15) | `benchmark/profile_system.py` (11), `score_e002.py`, `score_e003.py` (2 each) | FALSE POSITIVE on inspection: the lambdas are called immediately inside the same iteration (`mean = lambda …` used in the loop body) | None |
| BLE001 blind except (7) | `embeddings.py:38` (model load fallback), benchmark scripts | Intentional: model-load fallback must degrade to lexical; benchmark scripts record the reason | None |
| S110 try/except/pass (1) | `verify_retrieval.py:84` (`model_identity` best effort) | Intentional, diagnostic-only field | None |
| PLW1510 subprocess without `check` (3) | `discovery.py:21`, `typescript.py:11`, `verify_retrieval.py:41` | FALSE POSITIVE: return codes are inspected explicitly | None |
| RUF009 / B008 (2) | `config.py` dataclass default `Path(...)`, Typer `Argument` default | Framework idiom / evaluated once at import by design | None |
| B006 mutable default (1) | `benchmark/foundation_audit.py:17` | LIKELY TRUE POSITIVE, benchmark-only script, never mutated | None |

## mypy — the 27 errors

All 27 were read. Categories: 13 missing local annotations (`var-annotated`), 5 `dict.get(str | None)` where the
key is checked before use, 4 `None has no attribute encode/tokenizer/save/idf` on attributes guarded by
`load()`/`if self.bm25`, 3 tree-sitter `Node | None` narrowing, 1 `object has no attribute chunk_id` and 1 unary `-` on
`object` (both on untyped dict rows). **No finding reproduces as a runtime failure** — every guarded path is
covered by tests that pass (89/89 after the P0 fixes). Classification: NEEDS NO ACTION for correctness; typing
hygiene only.

## Semgrep

- `javascript.lang.security.detect-child-process` in `scripts/setup.mjs:10` — `spawnSync` with fixed program names and
  argument arrays, `shell` only for `npm.cmd` on Windows with fixed arguments. **FALSE POSITIVE.**
- Partial parsing of `frontend/src/App.tsx` (cols 441/950) and `TraceGraph.tsx` (cols 232/384): the parser gave up
  on extremely long single lines. Those regions were reviewed manually for XSS sinks: the frontend never uses
  `dangerouslySetInnerHTML`, `innerHTML` or `eval` (`git grep` → 0 hits); all text is rendered through React. The
  underlying maintainability issue is F-021.

## Security-relevant manual review (details in 15-security.md)

`subprocess` use (git, node) always passes argument lists, never `shell=True`; revision strings are validated
(`--output=/tmp/x` → 400 "Invalid Git revision", see `api-probe.json`).

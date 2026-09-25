# 08 · Runtime startup

## A. Documented clean startup (fresh clone, README "Quick start")

| | Before (`f0f2fc9` + `41fcee0`) | After (`46a3d28`) |
|---|---|---|
| `git clone` → `examples/demo-repo` | **0 files** (dangling gitlink) | 11 files |
| `npm run setup` | **exit 1 after 455 s** at `scripts/setup_demo.py`: `RuntimeError: Demo source files are missing` (venv, locked pip install, `npm ci`, `npm run build` succeeded first) | **exit 0 after 577 s** (venv, locked install incl. CPU torch, `npm ci`, build, demo Git history, MiniLM download) — timing taken while other audit jobs used the CPU |
| demo Git history | — | v1 `7826d38`, v2 `31b94fc` (deterministic, identical to this workspace) |
| `npm run demo` equivalent (`cli demo --port 8020` in the clone) | not reachable | **healthy 13 s** after start: v1 17 snippets / 11 relationships, v2 and working tree 21 / 12; semantic model ready |
| Browser suites against the fresh clone (journeys, a11y, studio) | — | 15 / 16 on the first run; the one failure was the intermittent graph-render bug, then fixed in `537233e` (graph tests 24/24 repeats, full suite 28/28) |

Interventions needed after the fixes: **none**. Undocumented prerequisites discovered: none beyond the README's
(Python 3.12, Node 22.12+, npm, Git, network for the one-time pip/npm/model downloads). Warnings seen: npm 11 lists
esbuild's install script as "not yet covered by allowScripts" (build still works); Node prints DEP0190 because
`scripts/setup.mjs` spawns `npm.cmd` with `shell: true` on Windows (fixed arguments; P3).

## B. Developer startup

`.venv` + `npm run build` + `npm run demo` in this workspace: before the fixture restore, **failed after 12 s** with the
same `RuntimeError` (`evidence/startup-before.log`). After: starts, indexes three snapshots and serves the UI; the audit
ran against this instance for the whole session. `npm run dev` (Vite on :5173 with `/api` proxy) is accepted by the
backend's origin allow-list (`api-probe.json`, "search allowed dev origin").

## C. Production-like startup

`Dockerfile` (lexical-only image, non-root) could not be built: Docker is not installed on the audit machine
(F-041, externally blocked). Static review: the image copies `examples/` — which was empty on every clone before
`b2ea145` — so the container demo would have failed the same way; it now contains the fixture.

## Logs and errors during runtime

- Backend logs during the session: no stack traces except intentional 4xx from the API probe.
- Browser console: before — favicon 404 on every load; `TextModel got disposed…` when leaving Compare (10 crawl
  interactions); Monaco `Canceled` rejections on tab switch. After — none (final crawl, 09).
- Failed network requests: none in the final crawl other than those the probe provoked deliberately.

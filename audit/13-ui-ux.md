# 13 · UI / UX audit

No single "UX score" is claimed. Measurable dimensions (Lighthouse, axe, overflow checks, control crawl) are reported
separately from heuristic judgements. Viewports: 1440×1000 (desktop), 768×1024 (tablet), 390×844 (phone).

## Measured

| Measure | Before | After | Evidence |
|---|---|---|---|
| Lighthouse accessibility (desktop) | 0.87 | **1.00** | `evidence/lighthouse/before-desktop.json`, `after-desktop.json` |
| Lighthouse best practices (desktop) | 0.96 (favicon 404 console error) | **1.00** | same |
| axe critical (all crawled states, Monaco excluded) | 1 rule in 21/21 states (`aria-required-children`, open-file strip) | 0 | `evidence/ui-crawl-before.json` → `ui-crawl.json` |
| axe serious | colour contrast in 17/21 states | 0 | same |
| axe serious/critical **including Monaco** (code, answer, map, compare, dialog; desktop + phone) | not measured before | **0** (gate: `frontend/e2e/a11y.spec.ts`) | `evidence/playwright-after.log` |
| axe moderate | no `h1`; duplicate banner in the dialog | 0 | crawl |
| Horizontal overflow at 390 / 768 / 1440 px | none | none | crawl `horizontal-overflow` pseudo-rule |
| Uncaught page errors during the crawl | 10 (`TextModel got disposed…` leaving Compare) + `Canceled` on tab switch | 0 expected (fixes F-032/F-034; see final crawl in 09) | crawl, diag |
| Controls with no visible effect | 2 × "ASTFLOW home" (reloads the same single-page app: expected) | same | crawl |

## Heuristic review (evidence-backed)

| Dimension | Observation | Action |
|---|---|---|
| Information architecture | Three workspace views (Map, Compare, Code) + a persistent companion; the snippet list in the companion is the canonical answer and every item links to exact lines | keep |
| Naming / honesty | "Explain" suggested generated explanations that do not exist; answers with only nearest-neighbour evidence were headed "Here's the relevant code"; agent log said "rerank" | fixed: "Ask", "Find related code", "Closest matches by meaning", "rank" |
| Feedback / loading | Real loading states: index progress bar with stage text, "Analyzing your code…" status (role=status), "Opening source tools…" while Monaco loads | keep |
| Empty states | Explicit: no repository, unindexed snapshot ("Index v1 to explore…"), no source selected, no graph relationships, fewer than two indexed versions, no shared modified source | keep |
| Error states | `role=alert` notice with dismiss; distinct messages for network failure, invalid (non-JSON) reply, 422 and server detail; tested with injected failures | keep |
| Responsiveness | Drawers below 850/600 px. Before: Compare opened the companion drawer over the diff; a result chosen in the drawer opened *under* it | fixed (F-033) |
| Keyboard / focus | Ctrl+K focuses the composer; Escape closes dialog and drawers; dialog traps focus; visible focus rings | keep (tested) |
| Contrast / readability | Several secondary texts and Monaco tokens were 3.5–4.4:1 | raised to ≥ 4.5:1 |
| Graph comprehension | Clear on the fixture; on real repositories the file overview is a grid of 60 of N files with no edges (CommonJS) and nodes named `anonymous@L:C` | open: F-029, F-030, F-031 (12-graph-audit) |
| Cognitive load | The companion stacks answer, investigation log, sequence evidence, suggestion chips and unresolved calls in one scroll; long answers push the heading out of view | open (P3): collapse older turns / pin the latest heading |
| Result relevance on real code | On expressjs/express, test files crowd the top 5 for 4 of 8 hand-written questions | open (P2); one heuristic fix was tried and rejected with evidence (`evidence/rejected-parser-heuristics.md`) |
| Code reviewability | Frontend written as very long single lines (App.tsx up to 1,881 chars/line; CSS lines up to 14,088) | open (P2, style-only; not reformatted to avoid churn during the audit) |

## Not done

- Lighthouse performance scores were not recorded: the machine was running benchmark jobs, so timing scores would be
  noise. Bundle sizes and API latencies are in 14-performance.
- No usability study with real users; heuristic judgements above are the auditor's, tied to screenshots/crawl evidence.

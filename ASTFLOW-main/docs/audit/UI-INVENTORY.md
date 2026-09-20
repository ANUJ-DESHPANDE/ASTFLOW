# Visible UI and API inventory

Implementation abbreviations: **App** = `frontend/src/App.tsx`; **Graph** = `components/TraceGraph.tsx`; **Viewer** = `components/SourceViewer.tsx`; **Parts** = `components/StudioParts.tsx`. API handler is `backend/app/main.py` unless noted. Main browser evidence: `frontend/e2e/studio.spec.ts`, `audit.spec.ts` and final JSON. No feature is classified as verified merely because it has a handler.

| Control / interaction | Implementation → API/data | Exercised state | Classification / remaining coverage |
|---|---|---|---|
| Repository picker / settings modal | App → repository/index/status → IndexService | Open, focus wrap, Escape, source retained; reindex via rail | WORKING common path; arbitrary-path form submission browser error not separately tested (API invalid paths tested) |
| Demo shortcut / Open & index | App → index/status | Clean CLI setup/demo verified, existing UI reindex verified | PARTIALLY WORKING verification: exact shortcut submit not clicked in final suite |
| Map / Compare / Code top tabs | App mode → map/compare/source | Real views/source and transitions | WORKING |
| Rail Explorer / map / compare / evidence / settings | App state, shared view handlers | Explorer/settings/top-level equivalents; mobile drawer | PARTIALLY WORKING coverage: shield focus and each redundant rail click not separately asserted |
| Explain toggle / mobile close / Escape | App local state | Desktop hide/show; mobile Escape | WORKING; individual close-icon click not separately asserted |
| File tree folder toggles and files | FileTree → source(snapshot,path) | File selection, source equality; child file visibility | WORKING navigation; every folder toggle not separately clicked |
| Filter files | App local filtering | Matching, no match, cleared | WORKING; empty display is an empty tree, not an explanation |
| Repository version | App → repository/map/search(selected version) | v1 switch, stale search response, commit-only startup | WORKING; commit-only startup uses deliberate response simulation |
| Reindex / progress | App → POST index, GET status | Real job completes, editor restored | WORKING success; error status path API tested, full background crash UI not induced |
| Passive source-change notice / Update snapshot | App → checkpoint, index | Backend file change/immutable old source test | PARTIALLY WORKING verification: notice/update button not exercised in final browser suite |
| Source tabs / close | App + Viewer → source | Open multiple files, switch, close | WORKING |
| Source highlight and line/path footer | Viewer → source full content/range | Actual result/source navigation | WORKING; every Unicode rendering scenario not browser-tested |
| Editor zoom | Viewer options | 125% then100% | WORKING |
| Copy selected source | App → Clipboard API | Clipboard text matches AuthService source | WORKING success; denied-permission notice not induced |
| Expand workspace | App → Fullscreen API | Enter and exit checked on document | WORKING success; browser-denied branch not induced |
| Query composer / send | App → POST search(query,version,top_k,agentic) | Real query, ranked results, loading gate, network abort, HTML502, recovery/no results | WORKING tested states; timeout branch not waited for |
| Ctrl+K / Enter / Shift+Enter | App keyboard handlers | Main send clicks; Escape tested | NOT TESTED individually in final suite |
| Composer plus / prompt-help / source badge / Chat focus | App local shortcuts | Implementation inspected | NOT TESTED individually; no fake upload/tool backend is implied |
| How this works / refinement checkbox | App → search.agentic | Expanded and unchecked; request body asserted false | WORKING; semantic fallback copy inspected |
| Source result cards / ranking details | App → source with result snapshot | Correct source session restoration, file/line/rank display | WORKING; score itself remains a ranking signal, not confidence |
| Investigation disclosure | App → search.agent_trace | Real trace data verified via backend; UI rendering inspected | PARTIALLY WORKING verification: disclosure click not independently asserted |
| Explain this code / Explore connections / See what changed | App shared handlers | Common target workflows exercised | PARTIALLY WORKING coverage; Explain means symbol retrieval, not generated explanation |
| Map file selector | App → GET map(file,version) | VoiceHandler file and real callable nodes | WORKING |
| Graph node search/center | Graph local loaded nodes | Match selected, details asserted | WORKING; outside loaded graph unsearchable |
| Incoming/outgoing/depth/hide | Graph local neighborhood; Explore calls → map(symbol,depth) | Outgoing/depth2/hide; pure helper verifies both directions | WORKING; API expansion always fetches up to depth3 then UI narrows |
| Fit/reset/zoom/pan | Graph / React Flow | Fit transform and reset selection asserted | PARTIALLY WORKING coverage: manual pan/individual +/- not separately automated |
| Node select / Open source / Explore calls | Graph → App/source/map | Select, explicit source, actual cross-file expansion | WORKING; double-click and file-node “Explore file” equivalents not separately clicked |
| Graph breadcrumb | App mapSymbol reset | Implementation inspected | NOT TESTED click |
| Call edge / supporting links | Graph/App → source captured snapshot | Real edge opens evidence/source; backend verifies import/call spans | WORKING basic path; each supporting link/race combination not separately tested |
| Trace fields / Trace action | App → POST trace | VoiceHandler→BluetoothAgent real supported path | WORKING; ambiguity/limit/no-path via backend, not every browser state |
| Unresolved call disclosure/links | App → map.unresolved/source | Resolver abstention tests; UI inspected | PARTIALLY WORKING verification, not all disclosure links clicked |
| Sequence section | SequenceEvidence → search.sequences/source | Real unsupported return case explicitly abstains | PARTIALLY WORKING verification: eligible positive-card source click not exercised in browser |
| Compare selectors / Compare submit | App → compare + source both snapshots | Actual v1/v2 source, counts and Monaco diff | WORKING |
| Changed symbol selector | App → source versionA/B | Initial modified symbol diff rendered | PARTIALLY WORKING verification: secondary symbol change not exercised |
| Before/after copy / source links | Parts/App → clipboard/source | Primary source copy tested; cards inspected | PARTIALLY WORKING verification: both card copy and denial separately untested |
| Inspect change / history | App saved comparison/version state | Main compare works; history fix inspected | PARTIALLY WORKING verification: historical reopen not separately asserted |
| Added/removed symbol disclosure | App comparison.changes | Backend verifies additions/removals; UI strings | PARTIALLY WORKING; entries are labels, not full separate diffs |
| Error dismissal | App state | Actual failed request notice dismissed then recovered | WORKING |
| Spinner/progress/reduced motion | FlowMark/CSS/App | Real delayed response and mobile reduced-motion mode | WORKING within browser test; exact video timing not claimed |
| Tooltips / all hover styles / accessibility | Native titles/CSS/aria labels | Focus trap, accessible selectors, mobile no horizontal overflow | PARTIALLY WORKING; no full screen-reader or contrast audit |

## Backend endpoint coverage

`scripts/audit_api.py` records 40 expected statuses and JSON checks in `api-probes.json`; backend tests also assert substantive data. Requests are real TestClient requests against temporary indexes, except the lock is deliberately held for the duplicate-job case.

| Endpoint | Contract / significant tested cases |
|---|---|
| GET health | Status/service and semantic availability; Host guard |
| GET repository | Current manifest/files, empty pre-index and unknown selected version |
| POST index | Absolute directory + optional revision/background; valid index, unknown/empty path, duplicate lock409, JSON415/body413 |
| GET index/status | State/progress/stage; actual browser job completion |
| POST search | Query1–2000, top_k1–50, version1–200, agentic; whitespace/type/extra/bounds422; no repository400; real snippets |
| POST trace | Required nonblank symbols, depth1–8; known path and supported ambiguity/limit states; unsupported symbols |
| GET source | Indexed relative path + lines/version; exact source, empty file, missing file, traversal, invalid/out-of-range lines |
| GET versions | Git labels plus indexed aliases; provenance and index state |
| GET map | Repo/file/callable neighborhood; missing file/symbol404, depth1–3; actual depth and callsite evidence |
| GET checkpoint | Passive changed flag; original snapshot bytes preserved |
| POST compare | Nonblank query and two selected versions; additions/removals/modifications/ranks/source truth |
| GET symbol/{id} | Known symbol definition and unknown symbol handling |
| GET / and assets | Production HTML and Monaco/graph chunks; clean setup smoke and real browser |

## User journeys and boundaries

1. **Ask → rank → source:** live search and snippet equality pass.
2. **Bluetooth → source → trace:** real demo call edges checked against indexed byte slices; passes.
3. **Switch Git version → same query/source:** backend real commits and browser stale-response guard pass.
4. **Compare v1/v2 → source truth:** passes for added/removed/modified symbols and changed calls.
5. **Weak search → agent decision → quality:** actual conditional refinement and controlled ablations; measured benefit small, not assumed.
6. **Break connection → useful error → recovery:** deliberately aborted and malformed responses pass.
7. **No matches:** lexical nonsense query returns explicit empty state. Semantic retrieval can return weak matches; no calibrated no-result guarantee exists.

No runtime debugger, generated patch Apply button, Figma importer or code-writing assistant is claimed. Screenshot-only controls unrelated to ASTFLOW were not implemented as fake actions.

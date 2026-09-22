# Samsung Theme 1 requirement → implementation matrix

Audit date: 20 September 2026. `PASS` means demonstrated within the stated envelope, not a claim of competitive quality or complete JavaScript analysis.

## Source of truth

- **G**: supplied `theme1_guidelines.pdf`, four pages, extracted from `fwdsamsungprismgenaihackathon3_0registrationli.zip`.
- **B**: supplied `Samsung PRISM_Y2026_GenAI_Hackathon_3rd_Edition.V2(2).pdf`, fifteen pages.
- Both documents were read completely. The theme-specific guide is used for primary evaluation requirements; the general brochure's additional requirements are retained below.
- **Conflicts:** G p2 says CSV once; G p3 repeatedly requires framework-generated JSON. This audit produces MTEB JSON and preserves ranked predictions. B p4 says JavaScript and optimisation suggestions as bonus; G uses a Python dataset, makes all-version retrieval the bonus, and excludes post-retrieval generation. Do not present the JavaScript agent as measured on Python. Do not claim generated explanations improve the screening score. Confirm these inconsistencies with organisers before final submission; they do not prevent the current evaluation.
- Samsung's **P0 retrieval accuracy** is distinct from ASTFLOW's earlier internal P0 engineering milestone.

Paths below are relative to the project root. Test prefixes: `T=backend/tests`, `U=frontend/e2e`, `A=docs/audit`, `E=benchmark/results`.

| Requirement/source | Priority | Source component; endpoint; UI | Test / benchmark evidence | Status | Remaining gap |
|---|---|---|---|---|---|
| Rank snippets for natural-language questions, G p1 | P0 | `retrieval/search.py`, `agent/investigate.py`; POST `/api/search`; App result cards | `T/test_api_versions.py`, `T/test_core.py`; E/mteb-bm25 and E/mteb-hybrid | PASS | Functionality verified; low official accuracy is a separate quality concern |
| Improve relevance on thousands of long snippets, G p1–2 | P0 | BM25, MiniLM, reciprocal rank fusion | 8,765 documents / 3,765 queries, full test split; hybrid NDCG@10 0.08815 | PARTIAL | No accuracy threshold specified; long bodies truncate in embeddings, no held-out tuning evidence |
| CPU/minimal GPU, G p1; B p4 | Runtime | `retrieval/embeddings.py`, NumPy/SciPy; model runs on CPU | `T/test_metrics_semantic.py`, official hybrid run, A/performance.json | PASS | Interrupted full-run wall time is not a throughput measurement |
| CoIR apps test split, G p2–3 | Dataset/evaluation | `benchmark/run_mteb.py`; no web endpoint | `benchmark/test_mteb_adapter.py`; exact dataset revision recorded | PASS | Dataset Python text does not exercise the JS parser or agent |
| MTEB evaluation, NDCG@10 and MRR, G p2–3 | Evaluation | `ASTFLOWSearch` SearchProtocol; MTEB evaluate/to_disk | E/mteb-hybrid/appsretrieval_results.json; bm25 counterpart | PASS | MTEB exposes cutoff-specific MRR: report MRR@10 and MRR@1000 explicitly |
| MTEB-generated result JSON, G p3 | Submission | Same runner and official serializer | Serialization regression; complete run artifacts | PASS | Release upload still outstanding; CSV wording conflict remains |
| Retrieval on different versions, G p2 | P1 | `indexing/service.py`, `versions/compare.py`; index/search/compare/versions; selectors | `T/test_api_versions.py`, `T/test_audit_reliability.py`, U/studio.spec.ts | PASS | Version aliases index explicitly; one workspace at a time |
| Reasonable rebuilding as code changes, G p2 | P1 | Hashes, isolated snapshot folders, stored vectors; index/checkpoint | Cache/reload tests; A/performance.json, one-file full rebuild | PARTIAL | No incremental parsing or changed-chunk embedding reuse; scale evidence uses small synthetic functions |
| Global ranking across all versions, G p2 | Bonus | No endpoint or global candidate merger | Source inspection: compare executes two independent searches | NOT IMPLEMENTED | Pairwise comparison is not evolutionary retrieval |
| Rank similar snippets from many versions, G p2 | Bonus | No near-duplicate grouping or global scoring | Source inspection of `versions/compare.py` | NOT IMPLEMENTED | Need global fusion, content grouping and provenance before any bonus claim |
| JavaScript OSS codebase, B p4 | Demo/scope | JS Tree-sitter parser; explicit local repo loader | Parser/resolver tests, actual bundled source fixture | PARTIAL | Demo is a constructed fixture; compatible real OSS repository still needs selection/audit/pinned commit |
| File and line locations, B p4 | Core output | `models/entities.py`, `main.py`; source/symbol/search; Monaco | Byte-span tests; API snippet equals indexed source; U/studio.spec.ts | PASS | Source matches static snapshot, not runtime observation |
| Structural/lexical-order and usage questions, B p4 | Demo | `structure/resolver.py`, `structure/graph.py`; search/trace/map; graph and sequence evidence | Frozen-boundary, ordered-pair, shadowing, trace tests; browser abstention case | PARTIAL | Conservative JS envelope; return/control-flow cases can abstain, no whole-language semantics |
| AST/call graph and embeddings, B p4 | Suggested approach | Two-pass parser/resolver, NetworkX, MiniLM | Static evidence tests; CPU semantic tests | PASS | TypeScript service corroborates JS edges only; it does not add `.ts` support |
| Observe and refine agentically, B p4 | Demo/approach | `agent/investigate.py`; POST search agentic flag; Investigation panel | `test_agent_refines_from_observed_symbols`, A/agent-trace-baseline.json and A/ablations.json | PARTIAL | Real conditional refinement, but a bounded rule policy; negligible measured local NDCG gain and no MRR gain |
| Precision@k, recall, latency, indexing cost, B p4 | Evaluation | MTEB scores, benchmark metrics, profiling harness | Official precision/recall keys; local recall; performance and run metadata | PASS | No representative 50k-line end-to-end performance study or human-labelled OSS test set |
| Query-response demo and speed, G p4 | Demo | Live search/source/trace/compare | Live browser journeys and API probes | PARTIAL | Required final presentation/video not supplied/verified |
| PPT/PDF and demo video, G p3–4; B p9–13 | Submission | No authored submission assets in audited project | Repository inventory | NOT IMPLEMENTED | Use supplied template, truthful results and ≤5 minute video; naming requirements from brochure |
| Reproducible README, G p3; B p12–13 | Submission | README, npm setup/demo, locks, source fixture | Fresh-environment verification described in REPORT | PARTIAL | Docker/semantic clean setup have separate verification limits |
| Docker files, B p12–13 | Submission | Dockerfile, .dockerignore, container_start.py | Static inspection only; Docker daemon connection failed | UNVERIFIED | Build/run image on a machine with Docker; default image intentionally lexical-only |
| GitHub release assets/tag, G p3; B p12–13 | Submission | Local commits and result JSON exist | No release publication executed | NOT IMPLEMENTED | Tag final commit `PRISM_GENAI_HACKATHON_Y2026`; upload required assets after final review |
| Explain/generate an answer after retrieval, G p1 | Explicit exclusion | Companion renders source facts, operational trace and evidence | UI/source inspection | OUT OF SCOPE | Product/demo aid, not screening improvement; no generative model added |
| Suggest code optimisations, B p4 bonus | Conflicting bonus | Not implemented | Source inspection | OUT OF SCOPE | Conflicts with narrower guide's retrieval focus; not claimed |

## Language support, without marketing expansion

| Capability | JavaScript | TypeScript source | Python |
|---|---|---|---|
| Repository ingestion | `.js/.mjs/.cjs/.jsx` | `.ts/.tsx` excluded | `.py` excluded |
| Functions/classes/methods/symbols/spans | Tree-sitter discovery | Not implemented | Not implemented |
| Imports and calls | Frozen conservative supported subset | Not implemented | Not implemented |
| Structural relationships | Supported calls; unresolved evidence elsewhere | TS language service corroborates **JS**, not TS input | None |
| Chunking | Callable chunks; bounded fallback module chunks | None | Dataset-provided document boundaries only |
| Comments/docstrings in retrieval | Source/comments/context included | None | Plain document text only; no docstring AST extraction |
| Official AppsRetrieval | Not the dataset language | Not the dataset language | BM25/dense/hybrid text ranking, preserving dataset IDs |

No JavaScript resolver types or additional repository languages were added during this audit.

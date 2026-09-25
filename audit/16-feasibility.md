# 16 · Feasibility review

## Technical feasibility (measured on this machine; see 14-performance for distributions)

| Dimension | Evidence | Assessment |
|---|---|---|
| Repository size | Hard limits: 20,000 JS files, 1 MB per file, 50 MB total (`config.py`) | Adequate for typical app/library repos; monorepos above 50 MB of JS are refused explicitly (not silently truncated) |
| Indexing time (cold, incl. embeddings, CPU) | demo 11 files 0.56 s (after an 8.4 s model load); express 141 files / 3,120 chunks 38.6 s; lodash 27 files / 4,463 chunks 97.5 s; cached re-index 0.04–1.8 s | Reasonable for a one-time build (S1 P1); embedding on CPU dominates |
| Re-indexing a changed version | content-hash embedding cache: demo v2 reused 13 of 21 vectors; unchanged snapshot → folder reuse | Meets S1 P1 intent; no incremental parsing (whole snapshot re-parsed) |
| Query latency | in-process search P50/P95: demo 6/13 ms, express 43/50 ms, lodash 54/76 ms (after F-037/F-045; express was 135/174 ms before) | Interactive |
| Memory / CPU / GPU | CPU only by design (`Embedder` uses `device="cpu"`); process RSS 0.95 GB (demo) to 1.26 GB (lodash), mostly torch + model | Runs on a laptop CPU; GPU not required; ~1.5 GB RAM advisable |
| Disk | per snapshot: SQLite + float32 vectors (≈ 1.5 KB × chunks) + manifest | small |
| Model downloads | one-time MiniLM download in `npm run setup` (or `astflow model-download`); lexical fallback when absent (`ASTFLOW_SEMANTIC=off`) | Works offline after setup; verified in the clean clone (model downloaded into the clone's `.astflow`, not a developer cache) |
| Concurrency | single-user; one indexing job at a time (409 otherwise); search while indexing uses the last ready snapshot | fine for a local tool, not a multi-user server |
| Persistence / recovery | atomic staging-folder rename with retry; corrupt index folders are renamed aside and rebuilt (`test_audit_reliability`) | good |

## Deployment feasibility (clean-machine path)

`git clone` → `npm run setup` (577 s) → `npm run demo` (healthy in 13 s) → index → query → graph: **verified** on a
fresh clone of `audit/master-remediation` (08-runtime-startup). Undocumented prerequisites: none found. The project
does not depend on a developer's Hugging Face cache (the clone downloaded its own model). Docker: unverified (no
Docker on this machine).

## Product feasibility

| Feature | Does it help the S1 developer problem? | Verdict |
|---|---|---|
| Ranked snippets with file/line, opened at the exact lines | Core S1 ask | Keep; quality on AppsRetrieval is low (NDCG@10 0.0884) and is the main open problem (F-044) |
| Agentic second pass | S1 "multiple retrieval passes"; measured benefit on the demo benchmark is small and not measured on AppsRetrieval (benchmark path runs without the agent) | Keep; measure on a judged real-repo set before claiming benefit |
| Call graph / Trace / Sequence | S1 structural and usage queries | Keep; now useful within files/IIFEs of real repos (F-023); cross-file CommonJS is the next gap (F-029) |
| Version comparison + snapshot selector | S1 P1 retrieval across versions | Keep |
| Evolutionary (all-version) retrieval | S1 bonus | Missing |
| Companion chat framing | Useful container for answers and evidence; must not imply generation | Kept, renamed "Ask" |
| Reranker | Not helpful (E002) | Removed |

**Overall:** feasible as a local, CPU-only, single-user investigation tool for JavaScript repositories up to tens of
thousands of files. The hard, unsolved part is retrieval accuracy on natural-language → code queries, which the
next retrieval experiments would address (E004 was pre-registered and cancelled for now; E005 is a candidate).

# ASTFLOW Retrieval — Session Handoff

_Last updated 2026-09-23 (second session). Contains only verified information._

## TRUST STATUS
Measurement system: **PARTIALLY VERIFIED** (the evaluator is verified; no retrieval run is)
Current trusted baseline: **CURRENT TRUSTED SCORE = UNKNOWN**
Target: ~0.20 NDCG@10
Baseline-v1: reported by the team as **running on the benchmark machine**; no artifacts have reached the repository yet.

## EXACT CODE STATE
Repository: https://github.com/ANUJ-DESHPANDE/ASTFLOW
Branch: `main`
HEAD: the commit that added this version of the file — `git log -1 -- ASTFLOW-HANDOFF.md`
Retrieval code (`backend/app/retrieval/`): unchanged since `fe1de96`, the commit baseline-v1 is expected to run on (check `git.commit` in its manifest)
Trusted baseline tag: **none**
Working tree: CLEAN after that commit

## TWO-MACHINE SETUP
- **Benchmark machine** (has Hugging Face): runs `verify_retrieval`, then `analyze_baseline pack`, commits artifacts.
- **Analysis machine** (no Hugging Face — never try to reach it): runs `analyze_baseline analyze` on committed artifacts only; designs experiments; can run fusion experiments offline.

## VERIFIED RETRIEVAL CONFIG (read from code, not docs)
Dataset: CoIR-Retrieval/apps (MTEB AppsRetrieval), pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`
Documents: 8,765 · Queries: 3,765 · Qrels: 3,765 pairs, exactly 1 relevant doc per query — per MTEB's own published stats; not yet confirmed from our own download
Embedding model: `sentence-transformers/all-MiniLM-L6-v2` · revision: will be in the baseline-v1 manifest (`model.commit_hash`)
Chunk/window: none on the official path (one vector per document, 256 word-piece limit, 23.5% of documents truncated per an older corpus analysis)
BM25: BM25Okapi k1 1.6, b 0.75, positive IDF, identifier splitting, English+code stopwords
Dense: normalized dot product, threshold 0.05
Hybrid: RRF k=60, weights 1/1 — exactly reconstructible offline from the frozen BM25 and Dense runs
Reranker: **ALIAS** — none executes; the disabled code has an invalid model id and swallows errors
Candidate depth: **1,000 on the benchmark**; 500 in the product app (which also enables boosts)

## TRUSTED METRICS
None. Do not use 0.0631, 0.0707, 0.089, 0.0894 or 0.1184 as current — see the RETRIEVAL-PROGRESS.md claims table.

## WHY WE TRUST / DO NOT TRUST THEM
ASTFLOW evaluator: PASS · trec_eval: PASS · ir_measures: PASS · MTEB: NOT RUN (its engine pytrec_eval PASS)
Cross-evaluator agreement: YES (synthetic golden + 1,000 randomized queries only)
Second-machine reproduction: NOT YET — `analyze_baseline analyze` will perform it on baseline-v1
Why no score: baseline-v1 artifacts not yet committed.

## CURRENT BOTTLENECK
**MEASUREMENT** — pending baseline-v1. The rule that will decide the next bottleneck is fixed in `benchmark/analyze_baseline.py::BOTTLENECK_RULES_V1` (written before any data).

## RETRIEVAL FORENSICS
Not yet measured on current code. Exact identity: with one relevant document per query, a perfect reranker over the top-k scores exactly Hit@k, and NDCG@10 ≤ Hit@10.
Hint from the OLD official Hybrid run (older code, not trusted): Oracle@20 0.176, Oracle@100 0.298, Oracle@1000 0.648; Hit@10 0.140.
Meaning, if this holds for current code: reranking only the top 20 can never reach 0.20; reranking the top 100 could only if it lifts the correct document to the top for about two-thirds of the questions where it is present.

## EXPERIMENT SCOREBOARD
| ID | Change | Before | After | Delta | Decision |
|---|---|---|---|---|---|
| BASE | Trusted baseline | — | not established | — | PENDING |

## IMPORTANT DISCOVERIES
- `0.0894` appears nowhere in the repo; the only `0.0707` is a 32-query Dense **MRR**.
- The `0.089` Hybrid result was produced by never-committed code.
- `benchmark/results/apps.md` (3,765 q) and `apps.json` (32 q) are from different runs.
- "Reranked" is Hybrid under another name; the disabled reranker code would not work if enabled.
- Benchmark depth is 1,000, not 500 (earlier docs were wrong); production uses 500 plus boosts.
- Oracle@k = Hit@k on this benchmark (one relevant doc per query); NDCG@10 ≤ Hit@10, so 0.20 needs ≥753 queries with the answer in the top 10.
- Hybrid = RRF of the frozen BM25 and Dense runs, exactly — fusion experiments need no model.
- MTEB/trec_eval re-sort tied scores by doc id descending; ASTFLOW sorts ascending. Frozen runs remove the ambiguity.
- The downloader now defaults to the pinned dataset revision (it used to fetch the latest).

## FAILED / DO NOT REPEAT
- Windowed dense via `apps_fixed.npy` without id alignment → Dense 0.0010. Reason: vector/document mismatch (fixed). Windowing itself is **unmeasured**, not failed.
- Contacting huggingface.co from the analysis machine. Reason: organisation policy denial; not needed.

## CURRENT ACTIVE EXPERIMENT
ID: BASE (baseline-v1) · Hypothesis: n/a (measurement) · Branch: `main` · Status: RUNNING on the benchmark machine (reported, not observed)

## EXACT NEXT ACTION
When baseline-v1 finishes on the benchmark machine, run `python -m benchmark.analyze_baseline pack --tag baseline-v1` there and commit the manifest, `apps.qrels`, per-query TSVs and `benchmark/verification/ranks/`; then on any machine run `python -m benchmark.analyze_baseline analyze --tag baseline-v1`.

## FILES THE NEXT AGENT SHOULD READ
1. /ASTFLOW-HANDOFF.md
2. /RETRIEVAL-PROGRESS.md
3. /benchmark/EXPERIMENTS.md (pre-registered queue E001–E003 with entry conditions)
4. /benchmark/VERIFICATION-MANIFEST.json
5. /benchmark/verification/manifest-baseline-v1.json and /benchmark/results/retrieval_forensics-baseline-v1.md, once they exist

---

## COPY THIS INTO THE NEXT AI SESSION

You are continuing ASTFLOW (https://github.com/ANUJ-DESHPANDE/ASTFLOW, branch `main`), a code-search system evaluated on MTEB AppsRetrieval (CoIR-Retrieval/apps, pinned revision `f22508f96b7a36c2415181ed8bb76f76e04ae2d5`; 8,765 documents, 3,765 queries, exactly one relevant document per query per MTEB's published stats). Primary metric: NDCG@10. Long-term target: about 0.20.

**Trust status: the evaluator is verified; there is NO trusted retrieval score yet.** Do not treat 0.0631, 0.0707, 0.089, 0.0894 or 0.1184 as current. No `retrieval-trusted-baseline-v1` tag exists.

**Two machines.** A benchmark machine with Hugging Face access runs `python -m benchmark.verify_retrieval --split all --tag baseline-v1` (reported running). If you are on the analysis machine, never contact huggingface.co and never download the dataset; work only from committed artifacts.

**Current pipeline (from code):** BM25 (k1 1.6, b 0.75, identifier splitting, code stopwords) + Dense (all-MiniLM-L6-v2, one normalized vector per document, threshold 0.05) merged by RRF (k 60, weights 1/1) at depth 1,000 on the benchmark (500 in the product app). No reranker executes. With boosts off, Hybrid is exactly RRF of the BM25 and Dense runs, so fusion can be studied offline.

**Tools:** `benchmark/verify_retrieval.py` (generate, freeze, cross-evaluate with ASTFLOW metrics, pytrec_eval, ir_measures, reference, NIST trec_eval). `benchmark/analyze_baseline.py`: `pack` (benchmark machine, ~8 MB/mode, checksum-verified) and `analyze` (any machine: rebuilds runs byte-for-byte against manifest checksums, re-scores with all evaluators, first-relevant-rank per query, BM25/Dense complementarity, oracle ceilings @10/20/50/100/500, Hybrid reconstruction check, pre-registered bottleneck rule BOTTLENECK_RULES_V1).

**Key facts:** Oracle@k = Hit@k and NDCG@10 ≤ Hit@10 on this benchmark. Old official Hybrid (older code, hint only): Hit@10 0.140, Oracle@20 0.176, Oracle@100 0.298.

**Do not repeat:** contacting huggingface.co from the analysis machine; windowed vectors without id alignment; calling "Reranked" a separate system; changing the evaluator or the bottleneck rule after seeing data; tuning on confirmation or full-test queries; changing retrieval code while baseline-v1 runs.

**Exact next action:** if `benchmark/verification/manifest-baseline-v1.json` and `benchmark/verification/ranks/` exist, run `python -m benchmark.analyze_baseline analyze --tag baseline-v1`. If every trust check passes, record Trusted Baseline V1 in RETRIEVAL-PROGRESS.md, benchmark/CURRENT_STATE.json and benchmark/EXPERIMENTS.md, create tag `retrieval-trusted-baseline-v1`, and start ONLY the experiment in benchmark/EXPERIMENTS.md whose entry condition matches the reported verdict (E001 fusion can run offline on the analysis machine; E002 reranker and E003 windows need the benchmark machine). If any trust check fails, stop and diagnose. If the artifacts do not exist yet, do not recreate them — wait.

Read first, in order: ASTFLOW-HANDOFF.md, RETRIEVAL-PROGRESS.md, benchmark/EXPERIMENTS.md, benchmark/VERIFICATION-MANIFEST.json. Keep the discipline: frozen data, frozen evaluator, one change per experiment, independent scoring, KEEP/REJECT, document. When finished, update ASTFLOW-HANDOFF.md, RETRIEVAL-PROGRESS.md and benchmark/CURRENT_STATE.json.

Do not trust this summary blindly. First verify that HEAD, Git status, and the referenced files still match this handoff. If they do, continue from the EXACT NEXT ACTION above rather than restarting the audit.

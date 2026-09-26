# ASTFLOW — 5-minute demo script

Hard limit: 5:00. Everything shown is the real product on a CPU laptop, running the frozen configuration. Queries and
their expected results come from [`DEMO-QUERIES.md`](DEMO-QUERIES.md), all checked in the clean-clone walkthrough
([`audit/JUDGE-WALKTHROUGH.md`](../audit/JUDGE-WALKTHROUGH.md)).

## Before the session (the day before; nothing here is faked)

1. `npm run setup` (downloads the model once, about 0.6 GB), then `npm run demo` once. Confirm the first log line
   reads `Retrieval: Alibaba-NLP/gte-modernbert-base · dense · CPU (frozen submission configuration)`.
2. Clone express and index the three versions once. This is the real, slow step: the first index embeds every chunk
   on CPU. The vectors are cached, so on demo day each version opens from its snapshot in seconds.

   ```sh
   git clone https://github.com/expressjs/express ~/express
   # with npm run demo running:
   for v in 4.18.2 4.19.2 4.21.2; do
     curl -s -X POST http://127.0.0.1:8000/api/index -H 'content-type: application/json' \
       -d "{\"repo_path\":\"$HOME/express\",\"version\":\"$v\",\"background\":false}" > /dev/null
   done
   ```

3. Restart `npm run demo`, open http://127.0.0.1:8000, open the repository dialog, enter the express path and version
   `4.21.2`, then **Open & index**. It returns at once because the snapshot is cached. Ask one warm-up question so the
   first on-stage query is not a cold start.
4. Keep a second browser tab on the demo repository (repository dialog → **Use demo repository**) as the fallback.

## Script

| Time | Show | Say (one breath each) |
|---|---|---|
| 0:00–0:25 | The express repository in the explorer: 152 files, 23k lines, three releases | "Finding where behaviour lives in a codebase you didn't write means grepping and file-hopping, and a repository this size doesn't fit in one LLM prompt." |
| 0:25–0:50 | The companion panel; open **How this works**; point at "Ranking: Alibaba-NLP/gte-modernbert-base · dense · CPU · frozen submission configuration" | "ASTFLOW indexes code semantically and structurally, so you can ask questions in plain English and jump straight to the implementation. This is the same frozen retriever we benchmarked, running on a laptop CPU." |
| 0:50–1:50 | **Primary query** (Q1, `where is the redirect location URL encoded` on 4.21.2). Point at the top result `location · lib/response.js:914–926`, the "ranked in N ms on CPU" line; click it and the exact lines open highlighted | "Plain English, no function names. The top result is the implementation, with its file and exact lines, ranked on CPU in the time shown." |
| 1:50–2:40 | **Usage** (Q2, `Where is compileQueryParser used?`): #2 is the caller `set` with "1 call hop(s)"; expand **Investigation**. If time allows, Q3 on the demo tab for call-order evidence | "Usage and structure come from the AST and a static call graph. Every edge has its call-site span, and the agent's plan, search, refine and rank steps are listed." |
| 2:40–3:30 | **Version intelligence** (Q4): switch the version selector to 4.18.2, 4.19.2 and 4.21.2; the question re-runs on each. `location` moves from 906–916 to 907–925 (the open-redirect fix) to 914–926, and the code changes | "Each release is its own index. The same question returns that release's code. A new release re-embeds only what changed: 4.19.2 reused 2,955 of 3,262 vectors and indexed in about a minute on 4 CPU cores." |
| 3:30–4:10 | One slide or the README architecture diagram | "GTE ModernBERT embeddings for retrieval; Tree-sitter AST and call graph for structure; content-addressed snapshots per Git revision; all on CPU, no GPU and no cloud API." |
| 4:10–4:40 | The release page with the MTEB JSON | "On the official MTEB AppsRetrieval evaluation, all 3,765 queries against 8,765 documents, the frozen retriever scores NDCG@10 0.5511 and MRR@10 0.5053, up from 0.0884 for our first system." |
| 4:40–5:00 | Back to the product | "Agentic code intelligence: ask in plain English, get exact code locations, follow the structure, and see how it changed between versions, locally on CPU." |

## If something goes wrong

| Failure | Response |
|---|---|
| Model not cached (setup never finished) | `npm run demo` refuses to start and prints the fix, so this surfaces during preparation, not on stage. Re-run `npm run setup` on a network. Do not switch to `ASTFLOW_SEMANTIC=off` for the demo: that is not the configuration being presented. |
| No internet | Nothing is needed once setup has run: the model, indexes and vectors are local. The release page (4:10) can be a screenshot. |
| Indexing not finished | Do not index live on stage: the first express index takes minutes on CPU (see the walkthrough timings). Use the pre-indexed snapshots. If express is not ready, run the whole demo on the demo repository (Q3, Q5 and the v1 → v2 version question). |
| Repository fails to load | Repository dialog → **Use demo repository** → Open & index (cached, seconds). |
| Graph slow or cluttered | Skip the Map; the Investigation steps and the result list carry the structural story. |
| Query latency spike | The first query after start-up loads caches; the warm-up question in step 3 absorbs it. The UI shows the real milliseconds; say so rather than hiding it. |
| A result is not the expected one | Use the fallback query in `DEMO-QUERIES.md`, and do not re-ask until it looks right. The honesty label ("closest matches by meaning") is itself part of the story. |

# ASTFLOW retrieval baseline — CLOSED at E023

The accepted retrieval system is `Alibaba-NLP/gte-modernbert-base`, model
revision `e7f32e3c00f91d699e8c43b53106206bcc72bb22`, on CPU in float32.
Both query and document embeddings are L2-normalized, and cosine similarity
is their dot product. Input is capped at 512 model tokens. The full corpus is
scored exactly and the benchmark returns its top 1,000. The default CPU cap
is eight threads, reduced to the machine's physical-core and PyTorch limits;
`ASTFLOW_THREADS` accepts a positive integer override subject to those caps.
The validated weight SHA-256 is
`3e85899d5728cb7de79781c0c3acfb91ccef9f875f1f7e0b3c9f3dd4b6a724ba`
([provenance](results/final-validation-20260928/provenance.json)).

BM25 is computed separately for keyword evidence, agent seed selection,
ranking agreement, and optional second-pass behavior. It contributes zero to
the accepted dense score. E019–E022 experimental rerankers, MMR, and BM25
fusion are disabled. The benchmark and snippet-search paths return dense
order exactly. Repository investigation starts with this dense first stage,
then its existing agent may add graph and second-pass evidence to the product
answer; that agent output is not the AppsRetrieval benchmark ranking.

## Validated full TEST

CoIR AppsRetrieval, 3,765 queries, 8,765 documents:

| Metric | Accepted result |
|---|---:|
| NDCG@10 | **0.5509** |
| MRR@10 | **0.5050** |
| Recall@10 | 0.6964 |
| Recall@50 | 0.8489 |
| Recall@100 | 0.8946 |
| Recall@500 | 0.9615 |
| Recall@1000 | 0.9782 |

[Clean validation](results/final-validation-20260928/README.md) records the
full float32 run, metrics, model provenance, and integrity checks. The earlier
official 0.5511/0.5053 result used native checkpoint precision; the small
difference was accepted. [Eight-thread equivalence](results/threads8-equivalence-20260929/README.md)
found identical top 10 for all 3,765 TEST queries and unchanged benchmark
metrics. Both prediction archives match the SHA-256 values in their provenance
records. No TEST benchmark was rerun for E023.

## Measured CPU performance

With eight threads, full encoding of 8,765 documents took 3,968 seconds
(about 66 minutes), versus 6,474 seconds at four threads. In the controlled
150-query encoding A/B, eight-thread p50/p95 were 229.5/295.8 ms versus
343.4/407.0 ms at four threads; eight threads won on 149/150 queries.
These controlled timings measure query encoding, not the whole API request.
The separate full-run query latency has different machine-load conditions and
must not be substituted for that paired speed comparison. Incremental
indexing reuses unchanged embeddings, but no accepted wall-time measurement
for it is recorded. See [latency evidence](results/threads8-equivalence-20260929/latency_ab.json).

## Reproduction

From the repository root on Windows PowerShell, use a separate benchmark
environment. The declared benchmark dependencies include `mteb==2.21.0` and
`pytrec-eval-terrier==0.5.10` in
[`requirements-mteb.txt`](requirements-mteb.txt):

```powershell
py -3.12 -m venv .eval-venv
.\.eval-venv\Scripts\python.exe -m pip install -c requirements.lock.txt -e '.[dev,semantic]' -r benchmark/requirements-mteb.txt
.\.eval-venv\Scripts\python.exe -m benchmark.run_mteb --mode dense --model Alibaba-NLP/gte-modernbert-base --download-model --diagnostics --output benchmark/results/reproduction/mteb
```

The accepted revision is pinned in `backend/app/config.py` for model
downloads. The runner checks the MTEB version and dataset revision before
evaluating. This is a full TEST reproduction command, **not** an E023 test
run. The validated artifact directories are
`benchmark/results/final-validation-20260928/` and
`benchmark/results/threads8-equivalence-20260929/`.

## Campaign decision

| Step | Dataset and result | Decision |
|---|---|---|
| E018 | 300 DEV: 55 recoverable ranking failures; 3 top-1000 misses | Diagnosis complete |
| E019 | 300 DEV: operator boost Δ NDCG@10 +0.002321, below +0.005 | Rejected |
| E020 | 300 DEV: learned feature reranker Δ NDCG@10 −0.041813 | Rejected |
| E021 | Held-out TRAIN-B: retained 45.45% of useful improvements, below 50% | Rejected before DEV |
| E022 | Fixed TRAIN CPU sample: selected joint reranker top-50 p50 29.56 s | Rejected before DEV |
| E023 | Accepted dense system frozen and documented | Campaign closed |

E022 did **not** evaluate broader reranker quality; its selected model failed
CPU feasibility first. The full [experiment ledger](results/campaign/LEDGER.md)
preserves commits, gates, and artifacts. Historical MiniLM and hybrid results
remain in the ledger as superseded experiments.

Retrieval optimization is **CLOSED** for this milestone. Reopen only when new
evidence or a changed constraint could materially alter the decision: for
example, a CPU-feasible stronger relevance model, acceptable GPU serving, a
substantially larger labeled dataset, a changed benchmark, or a demonstrated
production failure not represented by the validated task. Another fusion
weight or handcrafted boost is insufficient. Product work now returns to
reliable repository ingestion and incremental indexing using this stable
retrieval subsystem.

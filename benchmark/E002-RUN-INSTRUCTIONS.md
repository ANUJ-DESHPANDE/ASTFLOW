# E002 Cross-Encoder Reranker — Benchmark Machine Instructions

> **For the operator on the Hugging Face-enabled machine.**  
> Follow these steps in order. No manual tuning or search math required.

---

## 1. Sync Repository

```bash
git fetch origin
git checkout exp/E002-reranker
git pull origin exp/E002-reranker
```

Ensure dependencies are installed:
```bash
pip install sentence-transformers torch transformers
```

---

## 2. Model & Benchmark Configuration

* **Selected Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
  * Standard MTEB benchmark cross-encoder for sentence-transformers
  * Architecture: 6-layer BERT mini (22.7M parameters)
  * Max sequence length: 512 tokens
  * Joint format: `(query, document_code)`
  * Default batch size: 32
  * Device: `cpu` (or `cuda` if GPU available)

---

## 3. Run Development Split Sweep (Candidate Depths 20, 50, 100)

Run the three candidate depths on the development split (1,859 queries):

### Depth 20:
```bash
python -m benchmark.run_reranker_benchmark --depth 20 --split dev
```

### Depth 50:
```bash
python -m benchmark.run_reranker_benchmark --depth 50 --split dev
```

### Depth 100:
```bash
python -m benchmark.run_reranker_benchmark --depth 100 --split dev
```

---

## 4. Evaluate Confirmation Split on Dev Winner

Inspect the results printed at the end of each run in `benchmark/results/reranker_dev_d*.json`.  
Take the depth with the highest Development NDCG@10 (e.g. depth 100 or depth 50), and run it once on the **confirmation split** (1,906 queries):

```bash
python -m benchmark.run_reranker_benchmark --depth <WINNING_DEPTH> --split confirmation
```

And finally on the **full test set** (3,765 queries) to produce the official frozen run:

```bash
python -m benchmark.run_reranker_benchmark --depth <WINNING_DEPTH> --split all --tag e002-reranked-d<WINNING_DEPTH>
```

---

## 5. Pack and Commit Artifacts

Pack the resulting frozen run file byte-for-byte:
```bash
python -m benchmark.analyze_baseline pack --tag e002-reranked-d<WINNING_DEPTH>
```

Commit the generated artifacts and push:
```bash
git add benchmark/results/reranker_*.json \
        benchmark/verification/runs/e002-reranked-*.trec \
        benchmark/verification/ranks/e002-reranked-*.ranks.tsv.gz
git commit -m "benchmark(e002): record cross-encoder reranker run artifacts and scores"
git push origin exp/E002-reranker
```

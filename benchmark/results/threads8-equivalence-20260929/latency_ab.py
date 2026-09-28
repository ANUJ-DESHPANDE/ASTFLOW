"""Controlled single-query latency A/B: 4 vs 8 torch threads, same process, same queries, alternating order.

The two full runs were hours apart under different machine conditions, so their latency distributions are not a
fair comparison. Here each query is encoded under both settings back to back (order alternated per query) after a
warm-up. Writes latency_ab.json next to this file.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

import torch  # noqa: E402
from backend.app.config import Settings  # noqa: E402
from backend.app.retrieval.embeddings import Embedder  # noqa: E402
from benchmark.e005_screen import load_dataset_split  # noqa: E402

N = 150


def main():
    _, queries, qrels = load_dataset_split("test")
    qids = sorted(qrels)
    sample = [qids[i] for i in np.linspace(0, len(qids) - 1, N).astype(int)]
    emb = Embedder(Settings(model="Alibaba-NLP/gte-modernbert-base", semantic="auto"))
    emb.load()
    default_threads = torch.get_num_threads()  # what the product sets (THREADS, capped at physical cores)
    for q in sample[:5]:  # warm-up
        emb.encode([queries[q]], kind="query")
    times = {4: [], 8: []}
    for i, q in enumerate(sample):
        for n in ((4, 8) if i % 2 == 0 else (8, 4)):
            torch.set_num_threads(n)
            t = time.perf_counter()
            emb.encode([queries[q]], kind="query")
            times[n].append((time.perf_counter() - t) * 1000)
    a, b = np.array(times[4]), np.array(times[8])
    ratio = b / a
    report = {"queries": N, "product_default_threads": default_threads,
              "4_threads_ms": {"p50": float(np.median(a)), "p95": float(np.percentile(a, 95)), "mean": float(a.mean())},
              "8_threads_ms": {"p50": float(np.median(b)), "p95": float(np.percentile(b, 95)), "mean": float(b.mean())},
              "paired_ratio_8_over_4": {"median": float(np.median(ratio)), "p10": float(np.percentile(ratio, 10)),
                                        "p90": float(np.percentile(ratio, 90))},
              "8_faster_on": int((b < a).sum())}
    (HERE / "latency_ab.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

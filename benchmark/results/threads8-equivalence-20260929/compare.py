"""Equivalence check for the embedding thread-count change (4 -> 8 threads; speed only).

Compares this re-run of the official runner (8 threads) against the committed final validation run (4 threads,
benchmark/results/final-validation-20260928): corpus vectors, per-query rankings, the relevant document's rank and
the metrics (repo definitions, benchmark.campaign.metrics). Nothing is selected or tuned on this output.
Writes equivalence.json next to this file.
"""
import gzip
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.campaign import metrics  # noqa: E402
from benchmark.e005_screen import load_dataset_split  # noqa: E402

BASE = ROOT / "benchmark/results/final-validation-20260928"
NOT_FOUND = 10**9


def load(path):
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(raw)["default"]["test"]


def ordered(run):
    return {q: sorted(r, key=r.get, reverse=True) for q, r in run.items()}


def main():
    old = ordered(load(BASE / "mteb/predictions/AppsRetrieval_predictions.json.gz"))
    new_file = HERE / "mteb/predictions/AppsRetrieval_predictions.json"
    new = ordered(load(new_file if new_file.exists() else new_file.with_name(new_file.name + ".gz")))
    _, _, qrels = load_dataset_split("test")
    qids = sorted(qrels)
    assert set(old) == set(new) == set(qids), "query sets differ"

    def rank(run, q):
        rel = set(qrels[q])
        return next((i + 1 for i, d in enumerate(run[q]) if d in rel), NOT_FOUND)

    r_old, r_new = [rank(old, q) for q in qids], [rank(new, q) for q in qids]
    m_old, m_new = metrics(r_old), metrics(r_new)
    changed_rel = [(q, a, b) for q, a, b in zip(qids, r_old, r_new) if a != b]
    report = {
        "queries": len(qids),
        "identical_top10": sum(old[q][:10] == new[q][:10] for q in qids),
        "identical_top100": sum(old[q][:100] == new[q][:100] for q in qids),
        "identical_top1000": sum(old[q] == new[q] for q in qids),
        "relevant_rank_changed": len(changed_rel),
        "relevant_rank_changes": changed_rel[:50],
        "metrics_4_threads": m_old,
        "metrics_8_threads": m_new,
        "max_abs_metric_delta": max(abs(m_old[k] - m_new[k]) for k in m_old if k != "n"),
    }
    cache = ROOT / ".astflow"
    old_vec = next((cache / "vector-cache-4threads").glob("mteb-apps-*.npy"), None)
    new_vec = next((cache / "datasets").glob("mteb-apps-*.npy"), None)
    if old_vec and new_vec:
        a, b = np.load(old_vec), np.load(new_vec)
        report["corpus_vectors"] = {"shape": list(a.shape), "max_abs_diff": float(np.abs(a - b).max()),
                                    "min_cosine": float((a * b).sum(1).min()),
                                    "bit_identical_rows": int((a == b).all(1).sum())}
    meta_old = json.loads((BASE / "mteb/run_metadata.json").read_text(encoding="utf-8"))
    meta_new = json.loads((HERE / "mteb/run_metadata.json").read_text(encoding="utf-8"))
    lat = lambda m: {"p50": float(np.percentile(m["query_latencies_ms"], 50)),  # noqa: E731
                     "p95": float(np.percentile(m["query_latencies_ms"], 95)),
                     "mean": float(np.mean(m["query_latencies_ms"]))}
    report["timing"] = {
        "4_threads": {"corpus_index_s": meta_old["index_seconds"], "total_s": meta_old["total_seconds"],
                      "query_latency_ms": lat(meta_old)},
        "8_threads": {"corpus_index_s": meta_new["index_seconds"], "total_s": meta_new["total_seconds"],
                      "query_latency_ms": lat(meta_new)},
    }
    report["new_run_git_commit"] = meta_new["git_commit"]
    report["new_run_dirty_files"] = meta_new["git_dirty_files"]
    (HERE / "equivalence.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "relevant_rank_changes"}, indent=1))
    print("relevant rank changes (qid, 4 threads, 8 threads):", changed_rel[:20])


if __name__ == "__main__":
    main()

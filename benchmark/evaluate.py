"""Local graded retrieval evaluation. Labels are curated fixtures, not an official score."""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.app.agent.investigate import investigate
from backend.app.config import ROOT, Settings
from backend.app.indexing.service import IndexService
from benchmark.metrics import metrics


def evaluate(repo: Path, queries_path: Path, output: Path):
    service = IndexService()
    index = service.index(str(repo), "working-tree")
    queries = json.loads(queries_path.read_text(encoding="utf-8"))
    available = set(index.retriever.by_id)
    for q in queries:
        missing = set(q["relevant"]) - available
        if missing:
            raise ValueError(f"Invalid relevance labels in {q['id']}: {sorted(missing)}")
    modes = {"BM25 only": "bm25", "Dense only": "dense", "Hybrid": "hybrid", "Hybrid + structure": "hybrid_structure", "ASTFLOW full": "full"}
    report = {"dataset": "ASTFLOW local curated demo", "query_count": len(queries), "chunk_count": len(index.chunks),
              "source_hash": index.manifest["source_hash"], "generated_at": datetime.now(timezone.utc).isoformat(),
              "semantic": index.manifest["semantic"], "configuration_hash": service.settings.fingerprint(),
              "limitations": "Small handcrafted fixture; not a held-out or official MTEB/CoIR result. MRR is over at most 50 candidates.",
              "baselines": {}}
    # Warm up the model before measuring query latency.
    index.retriever.rank(queries[0]["query"])
    for label, mode in modes.items():
        if mode == "dense" and not index.manifest["semantic"]["available"]:
            report["baselines"][label] = {"status": "unavailable", "reason": "Semantic model not installed"}
            continue
        details, latencies = [], []
        for query in queries:
            started = time.perf_counter()
            response = investigate(index, query["query"], "working-tree", top_k=50, mode=mode)
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            ranked = [r["symbol_id"] for r in response["results"]]
            details.append({"id": query["id"], "category": query["category"], "query": query["query"],
                            **metrics(ranked, query["relevant"]), "latency_ms": round(latency, 2), "ranking": ranked})
        report["baselines"][label] = {"status": "evaluated", **{key: round(statistics.mean(d[key] for d in details), 4)
                                                              for key in ("ndcg@10", "mrr", "recall@10")},
                                       "latency_median_ms": round(statistics.median(latencies), 2),
                                       "latency_p95_ms": round(sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * .95))], 2),
                                       "queries": details}
    output.mkdir(parents=True, exist_ok=True)
    (output / "local.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# ASTFLOW local benchmark", "", report["limitations"], "",
             f"{len(queries)} queries · {len(index.chunks)} source chunks · model: {index.manifest['embedding_model'] or 'unavailable'}", "",
             "| System | NDCG@10 | MRR | Recall@10 | Median ms | p95 ms |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, result in report["baselines"].items():
        if result["status"] != "evaluated":
            lines.append(f"| {label} | unavailable | — | — | — | — |")
        else:
            lines.append(f"| {label} | {result['ndcg@10']:.4f} | {result['mrr']:.4f} | {result['recall@10']:.4f} | {result['latency_median_ms']:.2f} | {result['latency_p95_ms']:.2f} |")
    lines.extend(["", "Generated from an executed evaluation. Full per-query rankings are in `local.json`.", ""])
    (output / "local.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT / "examples/demo-repo")
    parser.add_argument("--queries", type=Path, default=ROOT / "benchmark/queries.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark/results")
    args = parser.parse_args(argv)
    evaluate(args.repo, args.queries, args.output)


if __name__ == "__main__":
    main()

"""E019: evaluate fixed operator evidence against frozen GTE dense retrieval.

Usage: python -m benchmark.e019_operator_rerank encode|evaluate
No TEST split is read. Document vectors are the published release asset.
"""

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.operator_evidence import rerank_operator_evidence
from benchmark.campaign import metrics, paired, ranks_from_scores
from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets, text_key


def load_docs(corpus, path):
    with np.load(path, allow_pickle=False) as asset:
        hashes = asset["hashes"].tolist()
        vectors = asset["vectors"].astype(np.float32)
    where = {h: i for i, h in enumerate(hashes)}
    ids = sorted(corpus)
    assert all(text_key(corpus[d]) in where for d in ids)
    return ids, np.ascontiguousarray(vectors[[where[text_key(corpus[d])] for d in ids]])


def encode(args):
    corpus, queries, qrels = load_dataset_split("train")
    sets = query_sets(qrels)
    ids = sets["dev"] + sets["confirmation"]
    model = Embedder(Settings())
    assert model.load(), model.reason
    start = time.perf_counter()
    vectors = model.encode([queries[q] for q in ids], kind="query")
    elapsed = time.perf_counter() - start
    Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.cache, ids=np.array(ids), hashes=np.array([text_key(queries[q]) for q in ids]),
                        vectors=vectors, elapsed_s=elapsed)
    print(json.dumps({"queries": len(ids), "encode_s": elapsed, "cache": args.cache}))


def evaluate(args):
    corpus, queries, qrels = load_dataset_split("train")
    ids, docs = load_docs(corpus, args.vectors)
    doc_pos = {d: i for i, d in enumerate(ids)}
    sets = query_sets(qrels)
    with np.load(args.cache, allow_pickle=False) as asset:
        qids = asset["ids"].tolist()
        assert qids == sets["dev"] + sets["confirmation"]
        assert asset["hashes"].tolist() == [text_key(queries[q]) for q in qids]
        query_vectors = {q: v for q, v in zip(qids, asset["vectors"])}
        encode_s = float(asset["elapsed_s"])
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    config = {"experiment": "E019", "hypothesis": "Explicit algorithm/operator words in problem statements help distinguish dense near-neighbor code solutions.",
              "depth": 50, "boost": 0.02, "features": ["xor", "gcd", "lcm", "modulo", "sort", "binary_search", "factorial", "prime", "palindrome"],
              "rule": "KEEP only if DEV delta NDCG@10 >= 0.005 and paired 95% bootstrap CI lower bound > 0, then confirmation delta > 0 with lower bound > 0; no material latency regression (>10% of 230ms query p50).",
              "dev_ids_sha256": hashlib.sha256("\n".join(sets["dev"]).encode()).hexdigest()}
    config_path = out / "config.json"
    if config_path.exists():
        assert json.loads(config_path.read_text(encoding="utf-8")) == config, "preregistered config changed"
    else:
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    report = {}
    for set_name in (args.set,):
        base_ranks, new_ranks, per_query = [], [], []
        base_ms, candidate_ms = [], []
        for q in sets[set_name]:
            t0 = time.perf_counter()
            dense = docs @ query_vectors[q]
            base_ms.append((time.perf_counter() - t0) * 1000)
            t1 = time.perf_counter()
            scores = rerank_operator_evidence(queries[q], ids, corpus, dense, depth=50, boost=0.02)
            candidate_ms.append((time.perf_counter() - t1) * 1000)
            rel = doc_pos[next(iter(qrels[q]))]
            br, nr = ranks_from_scores(dense, rel), ranks_from_scores(scores, rel)
            base_ranks.append(br)
            new_ranks.append(nr)
            per_query.append({"query_id": q, "baseline_rank": br, "experimental_rank": nr})
        base_metrics, new_metrics = metrics(base_ranks), metrics(new_ranks)
        base_metrics["r@20"] = sum(r <= 20 for r in base_ranks) / len(base_ranks)
        new_metrics["r@20"] = sum(r <= 20 for r in new_ranks) / len(new_ranks)
        report[set_name] = {"baseline": base_metrics, "experimental": new_metrics,
                            "paired_ndcg": paired(new_ranks, base_ranks),
                            "latency_ms": {"dense_score_p50": statistics.median(base_ms),
                                           "rerank_p50": statistics.median(candidate_ms),
                                           "rerank_p95": float(np.percentile(candidate_ms, 95))},
                            "per_query": per_query}
    report["query_encoding_s"] = encode_s
    if args.set == "dev":
        p = report["dev"]["paired_ndcg"]
        decision = "PROCEED_TO_CONFIRMATION" if p["delta"] >= 0.005 and p["ci"][0] > 0 else "REJECT"
    else:
        prior = json.loads((out / "dev.json").read_text(encoding="utf-8"))
        assert prior["decision"] == "PROCEED_TO_CONFIRMATION"
        c = report["confirmation"]["paired_ndcg"]
        decision = "KEEP" if c["delta"] > 0 and c["ci"][0] > 0 else "REJECT"
    report["decision"] = decision
    (out / f"{args.set}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({args.set: {k: report[args.set][k] for k in ("baseline", "experimental", "paired_ndcg", "latency_ms")},
                      "decision": decision}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("encode")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--set", choices=("dev", "confirmation"), required=True)
    parser.add_argument("--cache", default=".astflow/e019/query-vectors.npz")
    parser.add_argument("--vectors", default=".venv-gpu/apps-corpus-vectors-gte-modernbert-base.npz")
    parser.add_argument("--output", default="benchmark/results/E019-operator-evidence")
    args = parser.parse_args()
    {"encode": encode, "evaluate": evaluate}[args.command](args)


if __name__ == "__main__":
    main()

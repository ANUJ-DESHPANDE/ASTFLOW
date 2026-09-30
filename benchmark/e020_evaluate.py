"""Score preregistered E020 once on frozen DEV, then apply the decision gate."""

import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from benchmark.campaign import metrics, paired, ranks_from_scores
from benchmark.e005_screen import bootstrap, load_dataset_split
from benchmark.e019_operator_rerank import load_docs
from benchmark.e020_ranker import FEATURES, rank_top50
from benchmark.final_retrieval import query_sets, text_key

OUT = Path("benchmark/results/E020-hard-negative-ranking")


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    prereg = json.loads((OUT / "preregister.json").read_text())
    model_path = OUT / "model.json"
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == prereg["model_sha256"]
    model = json.loads(model_path.read_text())
    idf = json.loads((OUT / "idf.json").read_text())
    assert model["features"] == list(FEATURES)
    mean, scale, coef = (np.array(model[k], dtype=np.float64) for k in ("mean", "scale", "coef"))
    corpus, queries, qrels = load_dataset_split("train")
    qids = query_sets(qrels)["dev"]
    assert hashlib.sha256("\n".join(qids).encode()).hexdigest() == prereg["dev_ids_sha256"]
    ids, docs = load_docs(corpus, ".venv-gpu/apps-corpus-vectors-gte-modernbert-base.npz")
    positions = {d: i for i, d in enumerate(ids)}
    with np.load(".astflow/e019/query-vectors.npz", allow_pickle=False) as asset:
        vectors = dict(zip(asset["ids"].tolist(), asset["vectors"]))
        assert all(text_key(queries[q]) == h for q, h in zip(asset["ids"].tolist(), asset["hashes"].tolist()))
    base, candidate, per_query = [], [], []
    for q in qids:
        dense = docs @ vectors[q]
        positive = positions[next(iter(qrels[q]))]
        br = ranks_from_scores(dense, positive)
        order = rank_top50(queries[q], ids, corpus, dense, idf, mean, scale, coef)
        nr = order.index(positive) + 1
        base.append(br)
        candidate.append(nr)
        per_query.append({"query_id": q, "baseline_rank": br, "e020_rank": nr})
    bm, cm = metrics(base), metrics(candidate)
    for m, ranks in ((bm, base), (cm, candidate)):
        m["r@20"] = sum(r <= 20 for r in ranks) / len(ranks)
    ndcg = paired(candidate, base)
    mrr_d = np.array([1/r if r <= 10 else 0 for r in candidate]) - np.array([1/r if r <= 10 else 0 for r in base])
    mrr_ci = bootstrap(mrr_d)
    target = [x for x in per_query if 10 < x["baseline_rank"] <= 50]
    assert len(target) == 32
    bucket = {"moved_into_top10": sum(x["e020_rank"] <= 10 for x in target),
              "improved_still_over10": sum(10 < x["e020_rank"] < x["baseline_rank"] for x in target),
              "unchanged": sum(x["e020_rank"] == x["baseline_rank"] for x in target),
              "worsened": sum(x["e020_rank"] > x["baseline_rank"] for x in target)}
    dump("metrics.json", {"baseline": bm, "e020": cm, "e019_rejected": {"ndcg@10": 0.6990360866242341, "mrr@10": 0.6639325396825396}})
    dump("paired_comparison.json", {"ndcg@10": ndcg, "mrr@10": {"delta": float(mrr_d.mean()), "ci": mrr_ci},
                                    "improved": sum(x["e020_rank"] < x["baseline_rank"] for x in per_query),
                                    "unchanged": sum(x["e020_rank"] == x["baseline_rank"] for x in per_query),
                                    "regressed": sum(x["e020_rank"] > x["baseline_rank"] for x in per_query),
                                    "per_query": per_query})
    dump("target_bucket_analysis.json", bucket)

    sample = random.Random(20260929).sample(qids, 50)
    embedder = Embedder(Settings())
    assert embedder.load(), embedder.reason
    embedder.encode([queries[sample[0]]], kind="query")
    base_ms, new_ms = [], []
    for q in sample:
        t0 = time.perf_counter()
        vector = embedder.encode([queries[q]], kind="query")[0]
        dense = docs @ vector
        t1 = time.perf_counter()
        rank_top50(queries[q], ids, corpus, dense, idf, mean, scale, coef)
        t2 = time.perf_counter()
        base_ms.append((t1-t0)*1000)
        new_ms.append((t2-t0)*1000)
    latency = {"sample": "same 50 fixed DEV IDs as E019, seed 20260929, one warmup, CPU float32",
               "query_ids_sha256": hashlib.sha256("\n".join(sample).encode()).hexdigest(),
               "baseline_p50_ms": float(np.percentile(base_ms, 50)), "baseline_p95_ms": float(np.percentile(base_ms, 95)),
               "e020_p50_ms": float(np.percentile(new_ms, 50)), "e020_p95_ms": float(np.percentile(new_ms, 95))}
    dump("latency.json", latency)
    pass_dev = (ndcg["delta"] >= 0.005 and ndcg["ci"][0] > 0 and
                cm["mrr@10"] >= bm["mrr@10"] - 0.005 and cm["r@1000"] == bm["r@1000"])
    dump("decision.json", {"decision": "PROCEED_TO_CONFIRMATION" if pass_dev else "REJECT",
                           "reason": "Preregistered DEV quality and uncertainty gate " + ("passed" if pass_dev else "failed"),
                           "test_scored": False, "confirmation_scored": False})
    print(json.dumps({"baseline": bm, "e020": cm, "paired_ndcg": ndcg, "bucket": bucket,
                      "latency": latency, "decision": "PROCEED_TO_CONFIRMATION" if pass_dev else "REJECT"}, indent=2))


if __name__ == "__main__":
    main()

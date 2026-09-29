"""Choose and validate a small dense-margin gate entirely on held-out TRAIN."""

import hashlib
import json
from pathlib import Path

import numpy as np

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from benchmark.campaign import metrics, ranks_from_scores
from benchmark.e017_train import train_data
from benchmark.e019_operator_rerank import load_docs
from benchmark.e020_ranker import FEATURES, rank_top50
from benchmark.e021_gate import MEASURES, margins

OUT = Path("benchmark/results/E021-confidence-gated-rerank")
QUANTILES = (10, 20, 30, 40, 50)


def dump(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256("\n".join(value).encode()).hexdigest()


def distribution(values):
    return {"count": len(values), "mean": float(np.mean(values)), "median": float(np.median(values)),
            "p25": float(np.percentile(values, 25)), "p75": float(np.percentile(values, 75)),
            "p90": float(np.percentile(values, 90))}


def summarize_gate(rows, measure, threshold):
    broad_improved = sum(r["broad_rank"] < r["dense_rank"] for r in rows)
    broad_worsened = sum(r["broad_rank"] > r["dense_rank"] for r in rows)
    gated = [r for r in rows if r["margins"][measure] <= threshold]
    avoided = sum(r["broad_rank"] > r["dense_rank"] and r["margins"][measure] > threshold for r in rows)
    retained = sum(r["broad_rank"] < r["dense_rank"] for r in gated)
    ranks = [r["broad_rank"] if r["margins"][measure] <= threshold else r["dense_rank"] for r in rows]
    m = metrics(ranks)
    return {"confidence_metric": measure, "threshold": float(threshold), "queries_gated": len(gated),
            "queries_improved": sum(r["broad_rank"] < r["dense_rank"] for r in gated),
            "queries_worsened": sum(r["broad_rank"] > r["dense_rank"] for r in gated),
            "broad_improved": broad_improved, "broad_worsened": broad_worsened,
            "useful_recoveries_retained": retained,
            "useful_recoveries_retained_fraction": retained / broad_improved if broad_improved else 0,
            "harmful_interventions_avoided": avoided,
            "harmful_interventions_avoided_fraction": avoided / broad_worsened if broad_worsened else 0,
            "ndcg@10": m["ndcg@10"], "mrr@10": m["mrr@10"],
            "condition_a": avoided * 2 >= broad_worsened and broad_worsened > 0,
            "condition_b": retained * 2 >= broad_improved and broad_improved > 0}


def main():
    source = Path("benchmark/results/E020-hard-negative-ranking")
    manifest = json.loads((source / "artifact_hashes.json").read_text(encoding="utf-8-sig"))
    for name in ("model.json", "idf.json", "preregister.json"):
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == manifest[name]
    e020 = json.loads((source / "model.json").read_text())
    assert e020["features"] == list(FEATURES)
    idf = json.loads((source / "idf.json").read_text())
    mean, scale, coef = (np.asarray(e020[k]) for k in ("mean", "scale", "coef"))
    corpus, queries, qrels, train_ids = train_data()
    selection, validation = train_ids[300:500], train_ids[500:700]
    assert len(set(train_ids[:300]) & (set(selection) | set(validation))) == 0
    ids, docs = load_docs(corpus, ".venv-gpu/apps-corpus-vectors-gte-modernbert-base.npz")
    doc_pos = {d: i for i, d in enumerate(ids)}
    model = Embedder(Settings())
    assert model.load(), model.reason
    qids = selection + validation
    vectors = model.encode([queries[q] for q in qids], kind="query")
    rows = []
    for q, vector in zip(qids, vectors):
        dense = docs @ vector
        positive = doc_pos[next(iter(qrels[q]))]
        br = ranks_from_scores(dense, positive)
        broad_order = rank_top50(queries[q], ids, corpus, dense, idf, mean, scale, coef)
        er = broad_order.index(positive) + 1
        rows.append({"query_id": q, "dense_rank": br, "broad_rank": er, "margins": margins(dense)})
    dump("train_ranks.json", {"selection_ids_sha256": digest(selection),
                              "validation_ids_sha256": digest(validation), "rows": rows})
    populations = {}
    for measure in MEASURES:
        populations[measure] = {}
        for group, predicate in (("improved", lambda r: r["broad_rank"] < r["dense_rank"]),
                                 ("worsened", lambda r: r["broad_rank"] > r["dense_rank"]),
                                 ("unchanged", lambda r: r["broad_rank"] == r["dense_rank"])):
            vals = [r["margins"][measure] for r in rows if predicate(r)]
            populations[measure][group] = distribution(vals)
    dump("train_margin_analysis.json", {"queries": len(rows), "selection_queries": len(selection),
                                        "validation_queries": len(validation), "groups": populations})
    select_rows, validate_rows = rows[:len(selection)], rows[len(selection):]
    search = []
    for measure in MEASURES:
        values = [r["margins"][measure] for r in select_rows]
        for percentile in QUANTILES:
            threshold = float(np.percentile(values, percentile))
            result = summarize_gate(select_rows, measure, threshold)
            result["train_a_quantile"] = percentile
            search.append(result)
    eligible = [r for r in search if r["condition_a"] and r["condition_b"]]
    chosen = max(eligible, key=lambda r: (r["ndcg@10"], r["mrr@10"], -r["queries_gated"])) if eligible else None
    dump("gate_search_train.json", {"selection_queries": len(selection), "selection_ids_sha256": digest(selection),
                                    "selection_rule": "highest TRAIN-A NDCG@10 among gates passing both 50/50 conditions; then MRR@10; then fewer triggered",
                                    "metrics": list(MEASURES), "quantiles": QUANTILES,
                                    "candidates": search, "selected": chosen})
    if chosen:
        validation_result = summarize_gate(validate_rows, chosen["confidence_metric"], chosen["threshold"])
        passed = validation_result["condition_a"] and validation_result["condition_b"]
    else:
        validation_result = None
        passed = False
    dump("gate_validation_train.json", {"validation_queries": len(validation),
                                        "validation_ids_sha256": digest(validation),
                                        "selected_gate": chosen, "result": validation_result,
                                        "train_gate_pass": passed})
    if not passed:
        dump("train_gate_rejection.json", {"reason": "No selected simple margin gate passed both 50/50 conditions on independent TRAIN-B" if chosen else
                                           "No tested simple margin gate passed both 50/50 conditions on TRAIN-A",
                                           "dev_consumed": False, "candidates_tried": len(search)})
    print(json.dumps({"selection": chosen, "validation": validation_result, "train_gate_pass": passed,
                      "margin_analysis": populations}, indent=2))


if __name__ == "__main__":
    main()

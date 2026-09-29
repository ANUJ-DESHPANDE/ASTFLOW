"""Final validation run (2026-09-28), step 3: sanity-check the official runner's output and derive the reported metrics.

Read-only with respect to the retrieval system. Inputs are the files `benchmark/run_mteb.py` wrote under ./mteb:
  predictions/AppsRetrieval_predictions.json  the exact rankings MTEB scored (qid -> {doc_id: score});
                                              committed gzipped as AppsRetrieval_predictions.json.gz
  appsretrieval_results.json                  MTEB 2.21.0's own scores
  run_metadata.json                           runner provenance (model, depth, corpus hash, git commit)

Metrics use the repository's existing definitions (benchmark.campaign.metrics: one relevant document per query, so
Recall@k = Hit@k; NDCG@10 = 1/log2(rank+1); MRR@10 = 1/rank within the top 10). They are cross-checked against MTEB's
scores and against pytrec_eval on the same run. Writes validation.json and metrics.json next to this file.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from benchmark.campaign import metrics  # noqa: E402
from benchmark.e005_screen import load_dataset_split  # noqa: E402

NOT_FOUND = 10**9  # relevant document absent from the returned top-1000


def load_pairs(path):
    """JSON load that also reports duplicate keys (json.load silently keeps the last one)."""
    import gzip
    dups = []

    def hook(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                dups.append(k)
            seen.add(k)
        return dict(pairs)

    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(raw.decode("utf-8"), object_pairs_hook=hook), dups


def main():
    out = HERE / "mteb"
    preds_file = out / "predictions" / "AppsRetrieval_predictions.json"
    if not preds_file.exists():  # committed form: gzip of the file MTEB wrote (SHA-256 of both in provenance.json)
        preds_file = preds_file.with_name(preds_file.name + ".gz")
    preds_all, dup_keys = load_pairs(preds_file)
    subsets = [k for k in preds_all if k != "mteb_model_meta"]
    run = preds_all["default"]["test"]
    mteb_scores = json.loads((out / "appsretrieval_results.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    corpus, queries, qrels = load_dataset_split("test")
    _, _, train = load_dataset_split("train")

    depths = [len(r) for r in run.values()]
    all_scores = [s for r in run.values() for s in r.values()]
    ordered = {q: sorted(r, key=r.get, reverse=True) for q, r in run.items()}
    strictly_decreasing = all(all(a > b for a, b in zip(v, v[1:])) for v in
                              ([r[d] for d in ordered[q]] for q, r in run.items()))
    checks = {
        "prediction_file": str(preds_file.relative_to(HERE.parents[2])),
        "prediction_subsets_splits": {s: sorted(preds_all[s]) for s in subsets},
        "mteb_model_meta": preds_all.get("mteb_model_meta"),
        "duplicate_json_keys": len(dup_keys),
        "queries_predicted": len(run),
        "test_queries_expected": len(qrels),
        "missing_predictions": sorted(set(qrels) - set(run)),
        "unexpected_query_ids": sorted(set(run) - set(qrels)),
        "train_query_ids_in_run": len(set(run) & set(train)),
        "empty_rankings": sum(1 for d in depths if d == 0),
        "depth_min": min(depths), "depth_max": max(depths),
        "depth_below_1000": sum(1 for d in depths if d < 1000),
        "invalid_document_ids": sum(1 for r in run.values() for d in r if d not in corpus),
        "non_finite_scores": sum(1 for s in all_scores if not math.isfinite(s)),
        "scores_strictly_decreasing": strictly_decreasing,
        "run_metadata_query_count": meta.get("query_count"),
        "run_metadata_ranking_depth": meta.get("ranking_depth"),
        "run_metadata_corpus_count": meta.get("corpus_count"),
        "run_metadata_mode": meta.get("mode"),
        "run_metadata_model": meta.get("model"),
        "run_metadata_model_profile": meta.get("model_profile"),
        "run_metadata_precomputed": any(k.startswith("precomputed") for k in meta),
        "mteb_eval_splits_scored": sorted(mteb_scores["scores"]),
        "mteb_dataset_revision": mteb_scores.get("dataset_revision"),
    }

    ranks = []
    for q in sorted(qrels):
        rel = set(qrels[q])
        ranks.append(next((i + 1 for i, d in enumerate(ordered.get(q, [])) if d in rel), NOT_FOUND))
    ours = metrics(ranks)

    import pytrec_eval
    ev = pytrec_eval.RelevanceEvaluator(qrels, {"ndcg_cut_10", "recall_10", "recall_100", "recall_1000"}).evaluate(run)
    top10 = {q: {d: r[d] for d in ordered[q][:10]} for q, r in run.items()}
    rr10 = pytrec_eval.RelevanceEvaluator(qrels, {"recip_rank"}).evaluate(top10)
    mean = lambda ev_, key: sum(v[key] for v in ev_.values()) / len(qrels)  # noqa: E731
    pytrec = {"ndcg@10": mean(ev, "ndcg_cut_10"), "mrr@10": mean(rr10, "recip_rank"), "r@10": mean(ev, "recall_10"),
              "r@100": mean(ev, "recall_100"), "r@1000": mean(ev, "recall_1000")}
    m = mteb_scores["scores"]["test"][0]
    mteb = {"ndcg@10": m["ndcg_at_10"], "mrr@10": m["mrr_at_10"], "r@10": m["recall_at_10"],
            "r@100": m["recall_at_100"], "r@1000": m["recall_at_1000"], "main_score": m["main_score"]}
    diag = meta.get("diagnostic_recall", {})
    agree = {k: {"repo": ours[k], "pytrec_eval": pytrec[k], "mteb": mteb[k],
                 "max_abs_diff_rounded5": round(max(abs(round(ours[k], 5) - mteb[k]), abs(ours[k] - pytrec[k])), 6)}
             for k in ("ndcg@10", "mrr@10", "r@10", "r@100", "r@1000")}
    agree["r@50"] = {"repo": ours["r@50"], "runner_diagnostic": diag.get("r@50"),
                     "max_abs_diff": abs(ours["r@50"] - diag.get("r@50", float("nan")))}

    final = {k: ours[k] for k in ("ndcg@10", "mrr@10", "r@10", "r@50", "r@100", "r@500", "r@1000")}
    final.update(n=ours["n"], found_in_top1000=sum(r <= 1000 for r in ranks), rank1=sum(r == 1 for r in ranks))
    (HERE / "metrics.json").write_text(json.dumps({"split": "test", "metrics": final, "agreement": agree}, indent=1),
                                       encoding="utf-8")

    # A few query-level outputs for manual inspection.
    samples = []
    for q in sorted(qrels)[:: len(qrels) // 4][:4]:
        rel = next(iter(qrels[q]))
        samples.append({"qid": q, "query_head": queries[q][:160].replace("\n", " "), "relevant": rel,
                        "relevant_rank": ranks[sorted(qrels).index(q)],
                        "top5": [(d, run[q][d], corpus[d][:70].replace("\n", " ")) for d in ordered[q][:5]]})
    checks["samples"] = samples
    (HERE / "validation.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    print(json.dumps({"checks": {k: v for k, v in checks.items() if k != "samples"}, "metrics": final,
                      "agreement": agree}, indent=1))
    for s in samples:
        print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()

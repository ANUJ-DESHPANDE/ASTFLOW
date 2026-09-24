"""Independent scoring of the frozen E002 reranker run (ledger rule 3).

    python -m benchmark.score_e002 --tag e002-reranked-d20 --depth 20

Reads only committed artifacts: the frozen baseline and reranked rank files, the qrels,
the dev/confirmation split, and the dev-sweep results written by run_reranker_benchmark.
Both runs are re-frozen to TREC files and scored by every available evaluator
(`evaluation.cross_check`); per-split deltas use `forensics.paired_bootstrap`.
Writes benchmark/experiments/E002.json. Exits non-zero on any evaluator disagreement.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks
from benchmark.trust import evaluation
from benchmark.trust.forensics import paired_bootstrap

VERIFICATION = ROOT / "benchmark" / "verification"
RESULTS = ROOT / "benchmark" / "results"
METRICS = ("ndcg@10", "mrr@10", "recall@10", "recall@20", "recall@50", "recall@100")


def per_query(run, qrels, qids):
    out = {}
    for q in qids:
        row = evaluation.reference_metrics(run.get(q, []), qrels[q])
        positives = {d for d, g in qrels[q].items() if g > 0}
        row["recall@20"] = len(set(run.get(q, [])[:20]) & positives) / len(positives)
        out[q] = row
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--trec-eval", default=None)
    args = parser.parse_args()

    qrels_path = VERIFICATION / "apps.qrels"
    qrels = evaluation.read_qrels(qrels_path)
    splits = json.loads((ROOT / "benchmark" / "dev_split.json").read_text())
    groups = {"dev": splits["dev_query_ids"], "confirmation": splits["confirmation_query_ids"]}
    groups["all"] = groups["dev"] + groups["confirmation"]

    baseline = load_ranks(VERIFICATION / "ranks" / "baseline-v1-hybrid.ranks.tsv.gz")
    candidate = load_ranks(VERIFICATION / "ranks" / f"{args.tag}.ranks.tsv.gz")
    if set(candidate) != set(groups["all"]):
        sys.exit(f"{args.tag}: run covers {len(candidate)} queries, expected {len(groups['all'])}")

    # Integrity: reranking only permutes the top-`depth` candidates; the tail is untouched.
    permuted = sum(1 for q in candidate if sorted(candidate[q][:args.depth]) != sorted(baseline[q][:args.depth]))
    tail = sum(1 for q in candidate if candidate[q][args.depth:] != baseline[q][args.depth:])

    # Determinism: the separately frozen dev run must match the full run on dev queries.
    dev_file = VERIFICATION / "ranks" / f"e002-reranked-d{args.depth}-dev.ranks.tsv.gz"
    dev_match = None
    if dev_file.exists():
        dev_run = load_ranks(dev_file)
        dev_match = sum(1 for q in groups["dev"] if dev_run[q] == candidate[q])

    work = Path(tempfile.mkdtemp())
    checks = {}
    for name, run in (("baseline-v1-hybrid", baseline), (args.tag, candidate)):
        path = work / f"{name}.trec"
        sha = evaluation.write_run(run, path, tag=name)
        report = evaluation.cross_check(run, qrels, path, qrels_path, trec_eval=args.trec_eval)
        checks[name] = {"run_sha256": sha, "agree": report["agree"], "disagreements": len(report["disagreements"]),
                        "evaluators": report["evaluators"]}
        print(f"{name}: evaluators {sorted(report['evaluators'])} agree={report['agree']}")

    splits_out = {}
    for split, qids in groups.items():
        base_pq, cand_pq = per_query(baseline, qrels, qids), per_query(candidate, qrels, qids)
        mean = lambda pq, m: sum(pq[q][m] for q in qids) / len(qids)
        row = {"queries": len(qids),
               "baseline": {m: mean(base_pq, m) for m in METRICS},
               "reranked": {m: mean(cand_pq, m) for m in METRICS}}
        row["delta"] = {m: row["reranked"][m] - row["baseline"][m] for m in METRICS}
        for m in ("ndcg@10", "mrr@10"):
            bs = paired_bootstrap({q: base_pq[q][m] for q in qids}, {q: cand_pq[q][m] for q in qids})
            row[f"bootstrap_{m}"] = {k: bs[k] for k in ("mean_delta", "ci95", "improved", "worsened", "seed")}
            row[f"bootstrap_{m}"]["excludes_zero"] = bs["ci95"][0] > 0 or bs["ci95"][1] < 0
        splits_out[split] = row
        print(f"{split:12s} n={len(qids)} NDCG@10 {row['baseline']['ndcg@10']:.5f} -> {row['reranked']['ndcg@10']:.5f} "
              f"({row['delta']['ndcg@10']:+.5f}, CI95 [{row['bootstrap_ndcg@10']['ci95'][0]:+.5f}, "
              f"{row['bootstrap_ndcg@10']['ci95'][1]:+.5f}])")

    sweep = {}
    for depth in (20, 50, 100):
        f = RESULTS / f"reranker_dev_d{depth}.json"
        if f.exists():
            r = json.loads(f.read_text())
            sweep[f"d{depth}"] = {"ndcg@10": r["reranked_metrics"]["ndcg@10"], "delta": r["deltas"]["ndcg@10"],
                                 "ci95": r["bootstrap_ndcg10_ci95"], "device": r["device"], "runtime_s": r["runtime_s"]}

    conf = splits_out["confirmation"]["bootstrap_ndcg@10"]
    keep = conf["excludes_zero"] and conf["mean_delta"] > 0
    record = {
        "id": "E002-reranker",
        "hypothesis": "The Hybrid candidate pool contains relevant documents ranked too low; a cross-encoder "
                      "that jointly reads query and candidate code can reorder them better than RRF.",
        "change": "Rerank frozen baseline-v1 Hybrid top-k with a cross-encoder; candidates beyond k keep their order. "
                  "Tie-break: score descending, doc id ascending.",
        "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "model_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "input": "[query_text, document_text] only; qrels read only after rankings are frozen",
        "dataset_revision": splits["dataset_revision"],
        "qrels_sha256": evaluation.sha256_file(qrels_path),
        "dev_sweep": sweep,
        "selected_depth": args.depth,
        "tag": args.tag,
        "integrity": {"top_k_not_a_permutation": permuted, "tail_changed": tail,
                      "dev_run_matches_full_run_on_dev": dev_match},
        "cross_check": checks,
        "splits": splits_out,
        "decision": "KEEP" if keep else "REJECT",
        "decision_rule": "KEEP needs a positive confirmation NDCG@10 delta whose paired-bootstrap 95% CI excludes 0",
    }
    out = ROOT / "benchmark" / "experiments" / "E002.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"decision: {record['decision']} -> {out}")
    if not all(c["agree"] for c in checks.values()) or permuted or tail:
        sys.exit("integrity or evaluator check FAILED")


if __name__ == "__main__":
    main()

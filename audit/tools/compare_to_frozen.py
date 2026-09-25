"""Compare a regenerated verify_retrieval run with the frozen baseline-v1 rank files, query by query.

    python audit/tools/compare_to_frozen.py --out <verify_retrieval --out dir> --tag repro-baseline

Reports, per mode: queries with identical rankings (depth 1000 and top 100), queries where any metric changes,
and aggregate metrics for both. Writes audit/evidence/repro-vs-frozen.json.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.analyze_baseline import load_ranks  # noqa: E402
from benchmark.trust import evaluation  # noqa: E402

V = Path("benchmark/verification")
METRICS = ("ndcg@10", "mrr@10", "recall@10", "recall@50", "recall@100")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    qrels = evaluation.read_qrels(V / "apps.qrels")
    manifest = json.loads((args.out / f"manifest-{args.tag}.json").read_text())
    report = {"tag": args.tag, "git": manifest["git"], "environment": manifest["environment"], "modes": {}}
    for mode in manifest["run_sha256"]:
        fresh = evaluation.read_run(args.out / "runs" / f"{args.tag}-{mode}.trec")
        frozen = load_ranks(V / "ranks" / f"baseline-v1-{mode}.ranks.tsv.gz")
        qids = sorted(fresh)
        pf = {q: evaluation.reference_metrics(fresh[q], qrels[q]) for q in qids}
        pz = {q: evaluation.reference_metrics(frozen[q], qrels[q]) for q in qids}
        changed = [q for q in qids if any(abs(pf[q][m] - pz[q][m]) > 1e-12 for m in METRICS)]
        row = {"queries": len(qids),
               "identical_depth_1000": sum(fresh[q] == frozen[q] for q in qids),
               "identical_top_100": sum(fresh[q][:100] == frozen[q][:100] for q in qids),
               "queries_with_any_metric_change": len(changed), "changed_sample": changed[:10],
               "reproduced": {m: sum(pf[q][m] for q in qids) / len(qids) for m in METRICS},
               "frozen": {m: sum(pz[q][m] for q in qids) / len(qids) for m in METRICS}}
        report["modes"][mode] = row
        print(f"{mode:7s} identical {row['identical_depth_1000']}/{len(qids)} (top-100 {row['identical_top_100']}), "
              f"metric changes {len(changed)}; NDCG@10 {row['reproduced']['ndcg@10']:.5f} vs {row['frozen']['ndcg@10']:.5f}")
    Path("audit/evidence/repro-vs-frozen.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

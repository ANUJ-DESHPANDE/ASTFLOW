"""Freeze and score E003-dense-windows runs against the frozen baseline-v1 runs.

    python -m benchmark.score_e003 freeze --out <verify_retrieval --out dir> --tag e003-windows-dev
    python -m benchmark.score_e003 control --out <dir> --tag control-baseline-dev
    python -m benchmark.score_e003 score

`freeze` copies a finished `verify_retrieval --dense-windows` run into benchmark/verification: each
runs/<tag>-<mode>.trec is packed to ranks/<tag>-<mode>.ranks.tsv.gz and must rebuild the manifest's SHA-256.
(Runs are generated into a separate --out directory because verify_retrieval rewrites <out>/apps.qrels
for the selected split, and the committed qrels must not change.)
`control` checks that an unchanged-harness regeneration of baseline dense/hybrid matches the frozen
baseline-v1 rank files query by query. `score` compares every frozen E003 run with baseline-v1 on the
queries it covers, with paired-bootstrap CIs, and writes benchmark/experiments/E003.json.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from backend.app.config import ROOT
from benchmark.analyze_baseline import load_ranks, unpack
from benchmark.trust import evaluation
from benchmark.trust.forensics import paired_bootstrap

VERIFICATION = ROOT / "benchmark" / "verification"
EXPERIMENT = ROOT / "benchmark" / "experiments" / "E003.json"
MODES = ("dense", "hybrid")
METRICS = ("ndcg@10", "mrr@10", "recall@10", "recall@100")
SPLITS = {"dev": "e003-windows-dev", "confirmation": "e003-windows-confirmation", "all": "e003-windows"}


def freeze(out: Path, tag: str) -> None:
    manifest = json.loads((out / f"manifest-{tag}.json").read_text())
    if not all(manifest["evaluators"][m]["agree"] for m in manifest["run_sha256"]):
        sys.exit(f"{tag}: evaluators disagree; refusing to freeze")
    for mode, sha in manifest["run_sha256"].items():
        run_path = out / "runs" / f"{tag}-{mode}.trec"
        if evaluation.sha256_file(run_path) != sha:
            sys.exit(f"{run_path} does not match the manifest checksum")
        run = evaluation.read_run(run_path)
        target = VERIFICATION / "ranks" / f"{tag}-{mode}.ranks.tsv.gz"
        import gzip
        with gzip.open(target, "wt", encoding="utf-8", compresslevel=9) as stream:
            for qid in sorted(run):
                stream.write(qid + "\t" + " ".join(run[qid]) + "\n")
        rebuilt = unpack(target, mode, Path(tempfile.mkdtemp()) / "check.trec")
        if rebuilt != sha:
            sys.exit(f"{target} does not rebuild the original run")
        shutil.copyfile(out / f"per-query-{tag}-{mode}.tsv", VERIFICATION / f"per-query-{tag}-{mode}.tsv")
        print(f"{mode}: {target.name} ({target.stat().st_size / 1e6:.1f} MB) rebuild checksum OK")
    shutil.copyfile(out / f"manifest-{tag}.json", VERIFICATION / f"manifest-{tag}.json")


def control(out: Path, tag: str) -> dict:
    manifest = json.loads((out / f"manifest-{tag}.json").read_text())
    qrels = evaluation.read_qrels(VERIFICATION / "apps.qrels")
    result = {"tag": tag, "queries": manifest["dataset"]["evaluated_queries"], "modes": {}}
    for mode in manifest["run_sha256"]:
        fresh = evaluation.read_run(out / "runs" / f"{tag}-{mode}.trec")
        frozen = load_ranks(VERIFICATION / "ranks" / f"baseline-v1-{mode}.ranks.tsv.gz")
        qids = sorted(fresh)
        identical = sum(1 for q in qids if fresh[q] == frozen[q])
        top100 = sum(1 for q in qids if fresh[q][:100] == frozen[q][:100])
        pf, pz = per_query(fresh, qrels, qids), per_query(frozen, qrels, qids)
        metrics = {m: {"control": sum(pf[q][m] for q in qids) / len(qids), "frozen": sum(pz[q][m] for q in qids) / len(qids)}
                   for m in METRICS}
        metric_changed = sum(1 for q in qids if any(abs(pf[q][m] - pz[q][m]) > 1e-12 for m in METRICS))
        result["modes"][mode] = {"queries_identical_depth_1000": identical, "queries_identical_top_100": top100,
                                 "queries_with_any_metric_change": metric_changed, "queries": len(qids), "metrics": metrics}
        print(f"control {mode}: identical rankings {identical}/{len(qids)} (top-100 {top100}/{len(qids)}), "
              f"queries with any metric change {metric_changed}; "
              + ", ".join(f"{m} {v['control']:.5f} vs {v['frozen']:.5f}" for m, v in metrics.items()))
    result["git"] = manifest["git"]
    return result


def per_query(run, qrels, qids):
    return {q: evaluation.reference_metrics(run.get(q, []), qrels[q]) for q in qids}


def score() -> dict:
    qrels = evaluation.read_qrels(VERIFICATION / "apps.qrels")
    splits = json.loads((ROOT / "benchmark" / "dev_split.json").read_text())
    groups = {"dev": splits["dev_query_ids"], "confirmation": splits["confirmation_query_ids"]}
    groups["all"] = groups["dev"] + groups["confirmation"]
    record = json.loads(EXPERIMENT.read_text()) if EXPERIMENT.exists() else {}
    record["splits"] = {}
    for split, tag in SPLITS.items():
        manifest_path = VERIFICATION / f"manifest-{tag}.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        qids = groups[split]
        row = {"tag": tag, "queries": len(qids), "git": manifest["git"], "environment": manifest["environment"],
               "vectors": manifest["vectors"], "latency": manifest["latency"], "run_sha256": manifest["run_sha256"],
               "evaluators_agree": {m: manifest["evaluators"][m]["agree"] for m in manifest["evaluators"]},
               "evaluators": {m: sorted(manifest["evaluators"][m]["aggregates"]) for m in manifest["evaluators"]},
               "modes": {}}
        for mode in MODES:
            base = per_query(load_ranks(VERIFICATION / "ranks" / f"baseline-v1-{mode}.ranks.tsv.gz"), qrels, qids)
            cand_run = load_ranks(VERIFICATION / "ranks" / f"{tag}-{mode}.ranks.tsv.gz")
            if set(cand_run) != set(qids):
                sys.exit(f"{tag}-{mode}: covers {len(cand_run)} queries, expected {len(qids)}")
            cand = per_query(cand_run, qrels, qids)
            mean = lambda pq, m: sum(pq[q][m] for q in qids) / len(qids)
            m_row = {"baseline": {m: mean(base, m) for m in METRICS}, "e003": {m: mean(cand, m) for m in METRICS}}
            m_row["delta"] = {m: m_row["e003"][m] - m_row["baseline"][m] for m in METRICS}
            m_row["hits@100"] = {"baseline": sum(base[q]["recall@100"] > 0 for q in qids),
                                 "e003": sum(cand[q]["recall@100"] > 0 for q in qids)}
            for m in ("ndcg@10", "recall@100"):
                bs = paired_bootstrap({q: base[q][m] for q in qids}, {q: cand[q][m] for q in qids})
                m_row[f"bootstrap_{m}"] = {k: bs[k] for k in ("mean_delta", "ci95", "improved", "worsened", "seed")}
                m_row[f"bootstrap_{m}"]["excludes_zero"] = bs["ci95"][0] > 0 or bs["ci95"][1] < 0
            row["modes"][mode] = m_row
            ci = m_row["bootstrap_ndcg@10"]["ci95"]
            print(f"{split:12s} {mode:6s} NDCG@10 {m_row['baseline']['ndcg@10']:.5f} -> {m_row['e003']['ndcg@10']:.5f} "
                  f"({m_row['delta']['ndcg@10']:+.5f}, CI [{ci[0]:+.5f}, {ci[1]:+.5f}])  "
                  f"MRR@10 {m_row['delta']['mrr@10']:+.5f}  R@10 {m_row['delta']['recall@10']:+.5f}  "
                  f"Hit@100 {m_row['hits@100']['baseline']} -> {m_row['hits@100']['e003']}")
        record["splits"][split] = row

    def passes(split):
        s = record["splits"].get(split)
        if not s:
            return None
        b = s["modes"]["hybrid"]["bootstrap_ndcg@10"]
        return b["mean_delta"] > 0 and b["excludes_zero"]
    dev_ok, conf_ok = passes("dev"), passes("confirmation")
    record["decision"] = "KEEP" if dev_ok and conf_ok else "REJECT" if dev_ok is not None else "PENDING"
    record["decision_rule"] = ("KEEP needs a positive Hybrid NDCG@10 delta whose paired-bootstrap 95% CI excludes 0 on dev, "
                               "confirmed the same way on confirmation (pre-registered in benchmark/EXPERIMENTS.md)")
    EXPERIMENT.parent.mkdir(exist_ok=True)
    EXPERIMENT.write_text(json.dumps(record, indent=2) + "\n")
    print(f"decision: {record['decision']} -> {EXPERIMENT}")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["freeze", "control", "score"])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.out, args.tag)
    elif args.command == "control":
        result = control(args.out, args.tag)
        record = json.loads(EXPERIMENT.read_text()) if EXPERIMENT.exists() else {}
        record["environment_control"] = result
        EXPERIMENT.parent.mkdir(exist_ok=True)
        EXPERIMENT.write_text(json.dumps(record, indent=2) + "\n")
    else:
        score()


if __name__ == "__main__":
    main()

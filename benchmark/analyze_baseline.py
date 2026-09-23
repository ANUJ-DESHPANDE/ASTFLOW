"""Offline analysis of a frozen verification run. Needs NO model, NO dataset download.

On the benchmark machine, after verify_retrieval finishes:
    python -m benchmark.analyze_baseline pack --tag baseline-v1
        Packs each gitignored runs/<tag>-<mode>.trec into a small, committable
        ranks/<tag>-<mode>.ranks.tsv.gz (ordered doc ids per query).

On any machine, from committed artifacts only:
    python -m benchmark.analyze_baseline analyze --tag baseline-v1
        Rebuilds each TREC run byte-for-byte and checks its SHA-256 against the
        manifest, re-scores it with every available evaluator, and writes
        forensics, oracle reranking ceilings, BM25/Dense complementarity and an
        exact offline reconstruction of Hybrid (RRF over the frozen BM25 and Dense
        runs) to benchmark/results/retrieval_forensics-<tag>.{md,json}.

Qrels are used only to measure. Nothing here feeds back into retrieval.
"""
import argparse
import gzip
import json
import math
import sys
import tempfile
from pathlib import Path

from backend.app.config import ROOT, Settings
from benchmark.trust import evaluation, forensics

VERIFICATION = ROOT / "benchmark" / "verification"
TARGET_NDCG10 = 0.20
CUTOFFS = (1, 10, 20, 50, 100, 500, 1000)

# Pre-registered on 2026-09-23, before any baseline-v1 data was seen. Do not edit
# after looking at results; add a new rule version instead.
BOTTLENECK_RULES_V1 = """
1. MEASUREMENT if any run checksum, integrity check or evaluator comparison fails.
2. Otherwise CANDIDATE RETRIEVAL if Hybrid Oracle@100 < 0.20: even a perfect reranker
   over the top 100 cannot reach the target, so the right documents must be found first.
3. Otherwise FUSION if the BM25-or-Dense union reaches at least 0.03 more Recall@100
   than Hybrid itself: both lists already contain answers that the merge loses.
4. Otherwise RANKING: the answers are in the top 100 but not near the top.
""".strip()


def pack(tag: str) -> None:
    manifest = json.loads((VERIFICATION / f"manifest-{tag}.json").read_text())
    out = VERIFICATION / "ranks"
    out.mkdir(exist_ok=True)
    for mode in manifest["run_sha256"]:
        run_path = VERIFICATION / "runs" / f"{tag}-{mode}.trec"
        if evaluation.sha256_file(run_path) != manifest["run_sha256"][mode]:
            sys.exit(f"{run_path} does not match the manifest checksum; refusing to pack")
        run = evaluation.read_run(run_path)
        target = out / f"{tag}-{mode}.ranks.tsv.gz"
        with gzip.open(target, "wt", encoding="utf-8", compresslevel=9) as stream:
            for qid in sorted(run):
                stream.write(qid + "\t" + " ".join(run[qid]) + "\n")
        rebuilt = unpack(target, mode, Path(tempfile.mkdtemp()) / "check.trec")
        assert rebuilt == manifest["run_sha256"][mode], "packed file does not rebuild the original run"
        print(f"{mode}: {target} ({target.stat().st_size / 1e6:.1f} MB), rebuild checksum OK")


def load_ranks(path: Path) -> dict[str, list[str]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return {qid: docs.split() for qid, _, docs in (line.rstrip("\n").partition("\t") for line in stream)}


def unpack(path: Path, mode: str, trec_out: Path) -> str:
    return evaluation.write_run(load_ranks(path), trec_out, tag=f"astflow-{mode}")


def load_verified_run(tag: str, mode: str, expected_sha: str, workdir: Path) -> tuple[dict, Path, str]:
    raw = VERIFICATION / "runs" / f"{tag}-{mode}.trec"
    packed = VERIFICATION / "ranks" / f"{tag}-{mode}.ranks.tsv.gz"
    if raw.exists():
        path, source = raw, "runs/*.trec"
    elif packed.exists():
        path, source = workdir / f"{tag}-{mode}.trec", "ranks/*.ranks.tsv.gz (rebuilt)"
        unpack(packed, mode, path)
    else:
        raise FileNotFoundError(f"No frozen run for {mode}: expected {raw} or {packed}")
    actual = evaluation.sha256_file(path)
    if actual != expected_sha:
        raise AssertionError(f"{mode} run checksum {actual} != manifest {expected_sha}")
    return evaluation.read_run(path), path, source


def extra_metrics(run_path: Path, qrels_path: Path) -> dict:
    """Deep-cutoff metrics the frozen protocol does not include, via two libraries."""
    import ir_measures
    import pytrec_eval
    from ir_measures import R, RR
    qrels, run = evaluation.read_qrels(qrels_path), evaluation.read_run(run_path)
    judged = evaluation.judged_queries(qrels)
    scored = {q: {d: float(len(r) - i) for i, d in enumerate(r)} for q, r in run.items() if r}
    pt = pytrec_eval.RelevanceEvaluator(qrels, {"recall.500,1000", "recip_rank"}).evaluate(scored)
    irm = {}
    names = {R @ 500: "recall@500", R @ 1000: "recall@1000", RR: "mrr@1000"}
    for m in ir_measures.iter_calc(list(names), list(ir_measures.read_trec_qrels(str(qrels_path))),
                                   list(ir_measures.read_trec_run(str(run_path)))):
        irm.setdefault(m.query_id, {})[names[m.measure]] = float(m.value)
    avg = lambda rows: sum(rows) / len(judged) if judged else 0.0
    out = {"pytrec_eval": {"recall@500": avg(pt.get(q, {}).get("recall_500", 0.0) for q in judged),
                           "recall@1000": avg(pt.get(q, {}).get("recall_1000", 0.0) for q in judged),
                           "mrr@1000": avg(pt.get(q, {}).get("recip_rank", 0.0) for q in judged)},
           "ir_measures": {k: avg(irm.get(q, {}).get(k, 0.0) for q in judged) for k in names.values()}}
    out["agree"] = all(abs(out["pytrec_eval"][k] - out["ir_measures"][k]) < 1e-9 for k in names.values())
    return out


def rrf(bm25: dict, dense: dict, k: int = 60, w_lex: float = 1.0, w_sem: float = 1.0, depth: int = 1000) -> dict:
    """Hybrid as search.py computes it with boosts off, rebuilt from the two frozen lists."""
    fused = {}
    for qid in set(bm25) | set(dense):
        scores = {}
        for w, ranked in ((w_lex, bm25.get(qid, [])), (w_sem, dense.get(qid, []))):
            for rank, did in enumerate(ranked[:depth], 1):
                scores[did] = scores.get(did, 0.0) + w / (k + rank)
        fused[qid] = [d for d, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))][:depth]
    return fused


def analyze(tag: str) -> dict:
    manifest = json.loads((VERIFICATION / f"manifest-{tag}.json").read_text())
    qrels_path = VERIFICATION / "apps.qrels"
    trust = {"manifest": f"benchmark/verification/manifest-{tag}.json", "checks": {}, "problems": []}
    check = lambda name, ok, detail="": (trust["checks"].__setitem__(name, {"ok": bool(ok), "detail": detail}),
                                         None if ok else trust["problems"].append(name))
    ds = manifest["dataset"]
    check("dataset revision pinned", ds.get("revision") == "f22508f96b7a36c2415181ed8bb76f76e04ae2d5", ds.get("revision"))
    check("8,765 documents", ds.get("documents") == 8765, ds.get("documents"))
    check("3,765 judged queries evaluated", ds.get("evaluated_queries") == 3765 and ds.get("query_selection") == "all",
          f"{ds.get('evaluated_queries')} ({ds.get('query_selection')})")
    check("3,765 positive qrels, one per query", ds.get("positive_pairs") == 3765 and ds.get("binary_relevance"),
          f"{ds.get('positive_pairs')} positive, grades {ds.get('relevance_grades')}")
    check("qrels file matches manifest", evaluation.sha256_file(qrels_path) == ds.get("qrels_file_sha256"))
    check("corpus identical to historical official runs",
          ds.get("corpus_sha256_run_mteb_formula") == "ce25930a1a449256589e9e064e5568de35e2397ce32d963739c22c126c115021",
          ds.get("corpus_sha256_run_mteb_formula"))
    vec = manifest.get("vectors") or {}
    check("vector/document alignment probe", (vec.get("alignment_probe") or {}).get("min_cosine", 0) > 0.999,
          (vec.get("alignment_probe") or {}).get("aligned"))
    check("vectors finite and normalized", vec.get("nan") == 0 and vec.get("inf") == 0 and vec.get("zero_vectors") == 0,
          f"norm {vec.get('norm_min')}..{vec.get('norm_max')}")
    check("model revision recorded", bool((manifest.get("model") or {}).get("commit_hash")), (manifest.get("model") or {}).get("commit_hash"))
    check("benchmark ran on a clean commit", not manifest["git"]["dirty"], manifest["git"]["commit"])

    qrels = evaluation.read_qrels(qrels_path)
    judged = evaluation.judged_queries(qrels)
    workdir = Path(tempfile.mkdtemp())
    runs, metrics = {}, {}
    for mode, sha in manifest["run_sha256"].items():
        run, path, source = load_verified_run(tag, mode, sha, workdir)
        check(f"{mode} run checksum matches manifest", True, source)
        runs[mode] = run
        rep = evaluation.cross_check(run, qrels, path, qrels_path)
        extra = extra_metrics(path, qrels_path)
        check(f"{mode}: evaluators agree (this machine)", rep["agree"] and extra["agree"], f"{len(rep['disagreements'])} disagreements")
        before = manifest["evaluators"][mode]["aggregates"]["reference"]["ndcg@10"]
        now = rep["evaluators"]["reference"]["ndcg@10"]
        check(f"{mode}: NDCG@10 reproduces benchmark-machine value", abs(before - now) < 1e-12, f"{before} vs {now}")
        metrics[mode] = {"by_evaluator": rep["evaluators"], "deep": extra, "trec_eval": rep.get("trec_eval_binary")}

    per_query = {m: {q: forensics.first_relevant_rank(r.get(q, []), qrels[q]) for q in judged} for m, r in runs.items()}
    out = {"tag": tag, "trust": trust, "metrics": metrics, "rules": BOTTLENECK_RULES_V1,
           "cumulative_hit_rate": {m: {k: sum(1 for q in judged if (r := per_query[m][q]) and r <= k) / len(judged)
                                       for k in CUTOFFS} for m in runs},
           "oracle_ceiling": {m: {k: forensics.oracle_ceiling(r, qrels, judged, k) for k in (10, 20, 50, 100, 500)}
                              for m, r in runs.items()}}
    single = all(sum(1 for g in qrels[q].values() if g > 0) == 1 for q in judged)
    if single:  # with one relevant doc per query, a perfect reranker over top-k scores exactly Recall@k
        for m in runs:
            for k in (10, 20, 50, 100, 500):
                assert math.isclose(out["oracle_ceiling"][m][k], out["cumulative_hit_rate"][m][k]), (m, k)
    if {"bm25", "dense", "hybrid"} <= set(runs):
        b, d, h = per_query["bm25"], per_query["dense"], per_query["hybrid"]
        inf = float("inf")
        rk = lambda x: x if x is not None else inf
        out["comparison"] = {k: {"bm25_only": sum(1 for q in judged if rk(b[q]) <= k < rk(d[q])),
                                 "dense_only": sum(1 for q in judged if rk(d[q]) <= k < rk(b[q])),
                                 "both": sum(1 for q in judged if rk(b[q]) <= k and rk(d[q]) <= k),
                                 "neither": sum(1 for q in judged if rk(b[q]) > k and rk(d[q]) > k),
                                 "union_hit_rate": sum(1 for q in judged if min(rk(b[q]), rk(d[q])) <= k) / len(judged),
                                 "hybrid_hit_rate": out["cumulative_hit_rate"]["hybrid"].get(k)}
                             for k in (10, 20, 50, 100, 500)}
        out["head_to_head"] = {"bm25_ranks_relevant_higher": sum(1 for q in judged if rk(b[q]) < rk(d[q])),
                               "dense_ranks_relevant_higher": sum(1 for q in judged if rk(d[q]) < rk(b[q])),
                               "same_rank_or_both_missing": sum(1 for q in judged if rk(b[q]) == rk(d[q])),
                               "hybrid_beats_both": sum(1 for q in judged if rk(h[q]) < min(rk(b[q]), rk(d[q]))),
                               "hybrid_worse_than_best_single": sum(1 for q in judged if rk(h[q]) > min(rk(b[q]), rk(d[q]))),
                               "all_three_miss_top100": sum(1 for q in judged if min(rk(b[q]), rk(d[q]), rk(h[q])) > 100)}
        s = Settings()
        rebuilt = rrf(runs["bm25"], runs["dense"], s.rrf_k, s.lexical_weight, s.semantic_weight)
        exact = sum(1 for q in judged if rebuilt.get(q, []) == runs["hybrid"].get(q, []))
        check("hybrid is exactly RRF of the frozen BM25 and Dense runs", exact == len(judged), f"{exact}/{len(judged)} queries identical")
        dense_only_in_hybrid_top10 = sum(1 for q in judged
                                         if set(runs["hybrid"].get(q, [])[:10]) - set(runs["bm25"].get(q, [])))
        out["hybrid_uses_dense"] = {"queries_where_hybrid_top10_contains_docs_BM25_never_returned": dense_only_in_hybrid_top10}

    hyb = out["oracle_ceiling"].get("hybrid", {})
    union_gain = (out.get("comparison", {}).get(100, {}).get("union_hit_rate", 0) - out["cumulative_hit_rate"].get("hybrid", {}).get(100, 0))
    if trust["problems"]:
        verdict = "MEASUREMENT"
    elif hyb.get(100, 0) < TARGET_NDCG10:
        verdict = "CANDIDATE RETRIEVAL"
    elif union_gain >= 0.03:
        verdict = "FUSION"
    else:
        verdict = "RANKING"
    out["bottleneck"] = {"verdict": verdict, "hybrid_oracle@100": hyb.get(100), "union_minus_hybrid_recall@100": union_gain,
                         "rule_version": "BOTTLENECK_RULES_V1"}
    out["per_query_first_relevant_rank"] = per_query
    write_report(out)
    return out


def write_report(out: dict) -> None:
    tag = out["tag"]
    results = ROOT / "benchmark" / "results"
    (results / f"retrieval_forensics-{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    modes = list(out["metrics"])
    lines = [f"# Retrieval forensics — {tag}", "",
             f"Generated by `python -m benchmark.analyze_baseline analyze --tag {tag}` from committed artifacts only.",
             f"Source: `benchmark/verification/manifest-{tag}.json`, `apps.qrels`, frozen runs (checksums verified).", "",
             "## Trust checks", "", "| Check | OK | Detail |", "|---|---|---|"]
    lines += [f"| {k} | {'yes' if v['ok'] else '**NO**'} | {v['detail']} |" for k, v in out["trust"]["checks"].items()]
    lines += ["", "## Metrics (reference evaluator; all evaluators compared per query)", "",
              "| Mode | NDCG@10 | MRR@10 | MRR@1000 | R@10 | R@50 | R@100 | R@500 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for m in modes:
        a, deep = out["metrics"][m]["by_evaluator"]["reference"], out["metrics"][m]["deep"]["pytrec_eval"]
        lines.append(f"| {m} | {a['ndcg@10']:.5f} | {a['mrr@10']:.5f} | {deep['mrr@1000']:.5f} | {a['recall@10']:.5f} | "
                     f"{a['recall@50']:.5f} | {a['recall@100']:.5f} | {deep['recall@500']:.5f} |")
    lines += ["", "## Where is the relevant document? (share of queries, cumulative)", "",
              "| Mode | " + " | ".join(f"top {k}" for k in CUTOFFS) + " | not in top 1000 |",
              "|---|" + "---:|" * (len(CUTOFFS) + 1)]
    for m in modes:
        c = out["cumulative_hit_rate"][m]
        lines.append(f"| {m} | " + " | ".join(f"{c[k]:.3f}" for k in CUTOFFS) + f" | {1 - c[1000]:.3f} |")
    lines += ["", "## Oracle reranking ceiling (best NDCG@10 from reordering the top-k only)", "",
              "| Mode | actual | @10 | @20 | @50 | @100 | @500 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for m in modes:
        o = out["oracle_ceiling"][m]
        lines.append(f"| {m} | {out['metrics'][m]['by_evaluator']['reference']['ndcg@10']:.4f} | "
                     + " | ".join(f"{o[k]:.4f}" for k in (10, 20, 50, 100, 500)) + " |")
    if "comparison" in out:
        lines += ["", "## BM25 vs Dense complementarity (queries whose relevant doc is within top-k)", "",
                  "| k | BM25 only | Dense only | both | neither | union hit rate | Hybrid hit rate |", "|---:|---:|---:|---:|---:|---:|---:|"]
        for k, c in out["comparison"].items():
            lines.append(f"| {k} | {c['bm25_only']} | {c['dense_only']} | {c['both']} | {c['neither']} | "
                         f"{c['union_hit_rate']:.3f} | {c['hybrid_hit_rate']:.3f} |")
        lines += ["", "Head to head: " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in out["head_to_head"].items()) + ".",
                  f"Hybrid top-10 contains a document BM25 never returned for "
                  f"{out['hybrid_uses_dense']['queries_where_hybrid_top10_contains_docs_BM25_never_returned']} queries."]
    b = out["bottleneck"]
    lines += ["", "## Bottleneck", "", f"**{b['verdict']}** (rule {b['rule_version']}, pre-registered before data was seen)", "",
              "```", out["rules"], "```", "",
              f"Hybrid Oracle@100 = {b['hybrid_oracle@100']}; union minus Hybrid Recall@100 = {b['union_minus_hybrid_recall@100']:.4f}.", ""]
    (results / f"retrieval_forensics-{tag}.md").write_text("\n".join(lines))
    ranks = out["per_query_first_relevant_rank"]
    queries = sorted(next(iter(ranks.values())))
    (results / f"first-relevant-rank-{tag}.tsv").write_text(
        "query\t" + "\t".join(ranks) + "\n" + "\n".join(q + "\t" + "\t".join(str(ranks[m][q] or "") for m in ranks) for q in queries) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["pack", "analyze"])
    parser.add_argument("--tag", default="baseline-v1")
    args = parser.parse_args()
    if args.command == "pack":
        pack(args.tag)
    else:
        out = analyze(args.tag)
        print("trust problems:", out["trust"]["problems"] or "none")
        for m, v in out["metrics"].items():
            print(f"{m:7s} NDCG@10={v['by_evaluator']['reference']['ndcg@10']:.5f}  Oracle@100={out['oracle_ceiling'][m][100]:.4f}")
        print("bottleneck:", out["bottleneck"]["verdict"])
        print("report:", ROOT / "benchmark" / "results" / f"retrieval_forensics-{args.tag}.md")
        sys.exit(1 if out["trust"]["problems"] else 0)


if __name__ == "__main__":
    main()

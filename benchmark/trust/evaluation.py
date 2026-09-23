"""Freeze rankings to TREC files and score them with independent evaluators.

Protocol (the "frozen evaluator"), chosen to match NIST trec_eval with -c:
- Every query that has at least one positive qrel is in the denominator. A query
  that returned nothing, or is missing from the run, contributes 0.
- Order is the retriever's final list. It is written with a unique, strictly
  descending canonical score (n - rank + 1) so every evaluator sees exactly one
  unambiguous order; raw retrieval scores are kept elsewhere and never used for
  ordering here.
- NDCG uses trec_eval semantics: linear gain (gain = relevance grade),
  log2(rank + 1) discount. On binary qrels this equals the exponential-gain form.
- MRR@10 is reciprocal rank of the first relevant document within the top 10.
"""
import hashlib
import math
import shutil
import subprocess
from pathlib import Path

METRICS = ("ndcg@10", "mrr@10", "recall@10", "recall@50", "recall@100")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_qrels(qrels: dict[str, dict[str, int]], path: Path) -> str:
    lines = [f"{qid} 0 {did} {grade}" for qid in sorted(qrels) for did, grade in sorted(qrels[qid].items())]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sha256_file(path)


def write_run(rankings: dict[str, list[str]], path: Path, tag: str = "astflow") -> str:
    lines = []
    for qid in sorted(rankings):
        ranked = rankings[qid]
        if len(set(ranked)) != len(ranked):
            raise ValueError(f"Duplicate document in ranking for query {qid}")
        for rank, did in enumerate(ranked, 1):
            if not did or any(ch.isspace() for ch in did):
                raise ValueError(f"Invalid document id {did!r} for query {qid}")
            lines.append(f"{qid} Q0 {did} {rank} {len(ranked) - rank + 1} {tag}")
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return sha256_file(path)


def read_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            qid, _, did, grade = line.split()
            qrels.setdefault(qid, {})[did] = int(grade)
    return qrels


def read_run(path: Path) -> dict[str, list[str]]:
    rows: dict[str, list[tuple[int, str]]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            qid, _, did, rank, _score, _tag = line.split()
            rows.setdefault(qid, []).append((int(rank), did))
    return {qid: [did for _, did in sorted(items)] for qid, items in rows.items()}


def judged_queries(qrels) -> list[str]:
    return sorted(q for q, docs in qrels.items() if any(g > 0 for g in docs.values()))


def reference_metrics(ranked: list[str], rels: dict[str, int]) -> dict[str, float]:
    """Plain-Python statement of the protocol, used as the readable reference."""
    top = ranked[:10]
    dcg = sum(rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(top))
    ideal = sorted((g for g in rels.values() if g > 0), reverse=True)[:10]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    positives = {d for d, g in rels.items() if g > 0}
    rr = next((1 / (i + 1) for i, d in enumerate(top) if d in positives), 0.0)
    out = {"ndcg@10": dcg / idcg if idcg else 0.0, "mrr@10": rr}
    for k in (10, 50, 100):
        out[f"recall@{k}"] = len(set(ranked[:k]) & positives) / len(positives) if positives else 0.0
    return out


def eval_astflow(rankings, qrels):
    """ASTFLOW's historical evaluator (benchmark/metrics.py), mapped onto the protocol."""
    from benchmark.metrics import metrics
    per = {}
    for qid in judged_queries(qrels):
        ranked = rankings.get(qid, [])
        m10 = metrics(ranked, qrels[qid], k=10)
        per[qid] = {"ndcg@10": m10["ndcg@10"], "mrr@10": metrics(ranked[:10], qrels[qid], k=10)["mrr"],
                    "recall@10": m10["recall@10"],
                    "recall@50": metrics(ranked, qrels[qid], k=50)["recall@50"],
                    "recall@100": metrics(ranked, qrels[qid], k=100)["recall@100"]}
    return per


def eval_reference(rankings, qrels):
    return {qid: reference_metrics(rankings.get(qid, []), qrels[qid]) for qid in judged_queries(qrels)}


def eval_pytrec(run_path: Path, qrels_path: Path):
    """pytrec_eval: the trec_eval C engine that MTEB itself calls."""
    import pytrec_eval
    qrels, run = read_qrels(qrels_path), read_run(run_path)
    as_scores = {q: {d: float(len(r) - i) for i, d in enumerate(r)} for q, r in run.items() if r}
    full = pytrec_eval.RelevanceEvaluator(qrels, {"ndcg_cut.10", "recall.10,50,100"}).evaluate(as_scores)
    top10 = {q: dict(list(s.items())[:10]) for q, s in as_scores.items()}
    rr = pytrec_eval.RelevanceEvaluator(qrels, {"recip_rank"}).evaluate(top10)
    per = {}
    for qid in judged_queries(qrels):  # missing/empty runs -> 0, as trec_eval -c
        f, r = full.get(qid, {}), rr.get(qid, {})
        per[qid] = {"ndcg@10": f.get("ndcg_cut_10", 0.0), "mrr@10": r.get("recip_rank", 0.0),
                    "recall@10": f.get("recall_10", 0.0), "recall@50": f.get("recall_50", 0.0),
                    "recall@100": f.get("recall_100", 0.0)}
    return per


def eval_ir_measures(run_path: Path, qrels_path: Path):
    import ir_measures
    from ir_measures import nDCG, RR, R
    qrels = list(ir_measures.read_trec_qrels(str(qrels_path)))
    run = list(ir_measures.read_trec_run(str(run_path)))
    names = {nDCG @ 10: "ndcg@10", RR @ 10: "mrr@10", R @ 10: "recall@10", R @ 50: "recall@50", R @ 100: "recall@100"}
    got: dict[str, dict[str, float]] = {}
    for m in ir_measures.iter_calc(list(names), qrels, run):
        got.setdefault(m.query_id, {})[names[m.measure]] = float(m.value)
    judged = judged_queries(read_qrels(qrels_path))
    return {q: {k: got.get(q, {}).get(k, 0.0) for k in METRICS} for q in judged}


def find_trec_eval(explicit: str | None = None) -> str | None:
    for candidate in (explicit, shutil.which("trec_eval"), "/tmp/trec_eval/trec_eval"):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def eval_trec_eval_binary(run_path: Path, qrels_path: Path, binary: str):
    """NIST trec_eval with -c (all judged queries in the denominator) and -q (per query)."""
    def call(extra):
        out = subprocess.run([binary, "-c", "-q", *extra, str(qrels_path), str(run_path)],
                             capture_output=True, text=True, check=True, timeout=600).stdout
        rows = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3:
                rows.setdefault(parts[1], {})[parts[0]] = float(parts[2])
        return rows
    full = call(["-m", "ndcg_cut.10", "-m", "recall.10,50,100"])
    rr = call(["-M", "10", "-m", "recip_rank"])
    per = {}
    for qid in judged_queries(read_qrels(qrels_path)):
        f, r = full.get(qid, {}), rr.get(qid, {})
        per[qid] = {"ndcg@10": f.get("ndcg_cut_10", 0.0), "mrr@10": r.get("recip_rank", 0.0),
                    "recall@10": f.get("recall_10", 0.0), "recall@50": f.get("recall_50", 0.0),
                    "recall@100": f.get("recall_100", 0.0)}
    aggregate = {"ndcg@10": full.get("all", {}).get("ndcg_cut_10"), "mrr@10": rr.get("all", {}).get("recip_rank"),
                 "recall@10": full.get("all", {}).get("recall_10"), "recall@50": full.get("all", {}).get("recall_50"),
                 "recall@100": full.get("all", {}).get("recall_100")}
    return per, aggregate


def mean(per: dict[str, dict[str, float]]) -> dict[str, float]:
    n = len(per)
    return {k: (sum(v[k] for v in per.values()) / n if n else 0.0) for k in METRICS}


def cross_check(rankings, qrels, run_path: Path, qrels_path: Path, trec_eval: str | None = None,
                tol: float = 1e-9, trec_tol: float = 5e-5) -> dict:
    """Score the same frozen files with every available evaluator and compare per query.

    trec_eval prints 4 decimal places, so its per-query tolerance is 5e-5; all
    full-precision evaluators must agree to within `tol`.
    """
    frozen_run = read_run(run_path)
    if frozen_run != {q: r for q, r in rankings.items() if r}:
        raise ValueError("Frozen run file does not reproduce the in-memory rankings")
    results = {"reference": eval_reference(frozen_run, qrels), "astflow": eval_astflow(frozen_run, qrels),
               "pytrec_eval": eval_pytrec(run_path, qrels_path), "ir_measures": eval_ir_measures(run_path, qrels_path)}
    report = {"evaluators": {}, "disagreements": [], "binary_qrels": all(g in (0, 1) for d in qrels.values() for g in d.values())}
    binary = find_trec_eval(trec_eval)
    if binary:
        per, agg = eval_trec_eval_binary(run_path, qrels_path, binary)
        results["trec_eval"] = per
        report["trec_eval_aggregate_as_printed"] = agg
        report["trec_eval_binary"] = binary
    base = results["reference"]
    for name, per in results.items():
        report["evaluators"][name] = mean(per)
        limit = trec_tol if name == "trec_eval" else tol
        if name == "astflow" and not report["binary_qrels"]:
            continue  # exponential vs linear gain differ by design on graded qrels; reported, not compared
        for qid, row in base.items():
            for metric, value in row.items():
                if abs(per[qid][metric] - value) > limit:
                    report["disagreements"].append({"evaluator": name, "query": qid, "metric": metric,
                                                    "reference": value, "value": per[qid][metric]})
    report["agree"] = not report["disagreements"]
    report["per_query"] = results
    return report

"""Retrieval-metric campaign (2026-09-27): diagnostics and offline experiments on cached vectors.

Nothing is re-embedded: document, train dev/confirmation and test query vectors come from the frozen run's shard
artifacts (final_retrieval.py embed). Selection uses DEV only; CONFIRMATION must agree; TEST is evaluated for the
baseline reproduction and, once, for a kept configuration (`--final`).

Decision rule (pre-registered): KEEP iff dev ΔNDCG@10 >= +0.005 with 95% bootstrap CI > 0 AND confirmation ΔNDCG@10 > 0
with CI > 0, both paired against the baseline (GTE dense).
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import Retriever, tokenize
from benchmark.e005_screen import bootstrap, load_dataset_split
from benchmark.final_retrieval import load_shards, query_sets, text_key

KS = (10, 50, 100, 200, 500, 1000)


def ranks_from_scores(scores: np.ndarray, rel_idx: int) -> int:
    """1-based rank of the relevant document under a stable descending sort (ties: lower index first)."""
    s = scores[rel_idx]
    return int((scores > s).sum() + (scores[:rel_idx] == s).sum() + 1)


def metrics(ranks):
    r = np.asarray(ranks, dtype=np.float64)
    out = {"n": len(r), "ndcg@10": float(np.where(r <= 10, 1 / np.log2(r + 1), 0).mean()),
           "mrr@10": float(np.where(r <= 10, 1 / r, 0).mean()), "mrr": float((1 / r).mean())}
    out.update({f"r@{k}": float((r <= k).mean()) for k in KS})
    return out


def per_query_ndcg(ranks):
    r = np.asarray(ranks, dtype=np.float64)
    return np.where(r <= 10, 1 / np.log2(r + 1), 0)


def paired(cand, base):
    d = per_query_ndcg(cand) - per_query_ndcg(base)
    lo, hi = bootstrap(d)
    return {"delta": float(d.mean()), "ci": [lo, hi], "wins": int((d > 0).sum()), "losses": int((d < 0).sum())}


def generic_tokenize(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1]


class Data:
    def __init__(self, shards: Path, test_shards: Path):
        t0 = time.perf_counter()
        corpus, queries, qrels = load_dataset_split("train")
        _, _, test_qrels = load_dataset_split("test")
        self.corpus, self.queries = corpus, queries
        sets = query_sets(qrels)
        self.sets = {"dev": sets["dev"], "confirmation": sets["confirmation"], "test": sorted(test_qrels)}
        self.qrels = {**{q: qrels[q] for q in sets["dev"] + sets["confirmation"]}, **{q: test_qrels[q] for q in self.sets["test"]}}
        assert all(len(rel) == 1 for rel in self.qrels.values()), "expected exactly one relevant document per query"
        self.doc_ids = sorted(corpus)
        self.pos = {d: i for i, d in enumerate(self.doc_ids)}
        d_ids, d_keys, d_mat, *_ = load_shards(shards, "docs")
        assert sorted(d_ids) == self.doc_ids and all(text_key(corpus[d]) == k for d, k in zip(d_ids, d_keys))
        where = {d: i for i, d in enumerate(d_ids)}
        self.D = np.ascontiguousarray(d_mat[[where[d] for d in self.doc_ids]], dtype=np.float32)
        self.Q = {}
        for directory, what, want in ((shards, "queries", sets["dev"] + sets["confirmation"]), (test_shards, "test", self.sets["test"])):
            q_ids, q_keys, q_mat, *_ = load_shards(directory, what)
            assert sorted(q_ids) == sorted(want) and all(text_key(queries[q]) == k for q, k in zip(q_ids, q_keys)), what
            self.Q.update({q: v.astype(np.float32) for q, v in zip(q_ids, q_mat)})
        print(f"data ready in {time.perf_counter() - t0:.0f} s: {len(self.doc_ids)} docs, "
              + ", ".join(f"{k} {len(v)}" for k, v in self.sets.items()), flush=True)
        self._bm25 = {}

    def rel(self, q):
        return self.pos[next(iter(self.qrels[q]))]

    def dense(self, q):
        return self.D @ self.Q[q]

    def bm25_index(self, name):
        if name not in self._bm25:
            t0 = time.perf_counter()
            tok = {"code": tokenize, "generic": generic_tokenize}[name]
            chunks = [Chunk(d, d, "", d, "dataset_document", 1, 1, self.corpus[d], self.corpus[d],
                            hashlib.sha256(self.corpus[d].encode()).hexdigest()) for d in self.doc_ids]
            self._bm25[name] = (Retriever(chunks, None, None, Settings(semantic="off"), tokenizer=tok), tok)
            print(f"BM25[{name}] index in {time.perf_counter() - t0:.0f} s", flush=True)
        return self._bm25[name]

    def bm25(self, q, name="code"):
        retriever, tok = self.bm25_index(name)
        return np.asarray(retriever.lexical_scores(tok(self.queries[q])), dtype=np.float64)


def rank_positions(scores):
    """0-based position of every document in the stable descending order."""
    order = np.argsort(-scores, kind="stable")
    pos = np.empty(len(scores), dtype=np.int64)
    pos[order] = np.arange(len(scores))
    return pos


def rrf(pos_a, pos_b, wa, wb, k, depth=1000):
    a = np.where(pos_a < depth, wa / (k + pos_a + 1), 0.0)
    b = np.where(pos_b < depth, wb / (k + pos_b + 1), 0.0)
    return a + b


def pytrec_check(data, qids, scores_fn):
    """Rule 29: our NDCG@10 / MRR against pytrec_eval on the same top-1000 run."""
    import pytrec_eval
    run, ours = {}, []
    for q in qids:
        s = scores_fn(q)
        top = np.argsort(-s, kind="stable")[:1000]
        # strictly decreasing pseudo-scores keep pytrec_eval's order identical to ours (it re-sorts by score, then id)
        run[q] = {data.doc_ids[i]: float(1000 - n) for n, i in enumerate(top)}
        ours.append(ranks_from_scores(s, data.rel(q)))
    qrels = {q: data.qrels[q] for q in qids}
    ev = pytrec_eval.RelevanceEvaluator(qrels, {"ndcg_cut_10", "recip_rank"}).evaluate(run)
    mine = metrics(ours)
    # our MRR is over the full ranking; pytrec's recip_rank only over the 1000 returned, so compare on queries found
    found = [q for q, r in zip(qids, ours) if r <= 1000]
    return {"ours_ndcg@10": mine["ndcg@10"], "pytrec_ndcg@10": float(np.mean([ev[q]["ndcg_cut_10"] for q in qids])),
            "ours_mrr_top1000": float(np.mean([1 / r if r <= 1000 else 0 for r in ours])),
            "pytrec_recip_rank": float(np.mean([ev[q]["recip_rank"] for q in qids])), "queries_found": len(found)}


def run(args):
    data = Data(Path(args.shards), Path(args.test_shards))
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    report = {"baseline": "GTE dense (frozen submission)", "rule": __doc__.split("Decision rule")[1].strip(), "sets": {}}
    cache = {}
    for name in ("dev", "confirmation"):
        t0 = time.perf_counter()
        qids = data.sets[name]
        dense = {q: data.dense(q) for q in qids}
        bm25 = {q: data.bm25(q, "code") for q in qids}
        bm25g = {q: data.bm25(q, "generic") for q in qids}
        pos_d = {q: rank_positions(dense[q]) for q in qids}
        pos_b = {q: rank_positions(bm25[q]) for q in qids}
        rel = {q: data.rel(q) for q in qids}
        R = lambda f: [ranks_from_scores(f(q), rel[q]) for q in qids]
        base = R(lambda q: dense[q])
        systems = {"dense": base, "bm25_code": R(lambda q: bm25[q]), "bm25_generic": R(lambda q: bm25g[q]),
                   "hybrid_rrf_equal_k60": R(lambda q: rrf(pos_d[q], pos_b[q], 1, 1, 60))}
        # E009: weighted RRF and linear score fusion (BM25 max-normalised per query), dense-dominant grids.
        for wd in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
            for k in (10, 30, 60, 100):
                systems[f"e009_rrf_wd{wd}_k{k}"] = R(lambda q, wd=wd, k=k: rrf(pos_d[q], pos_b[q], wd, 1 - wd, k))
        for lam in (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5):
            systems[f"e009_lin_l{lam}"] = R(lambda q, lam=lam: dense[q] + lam * bm25[q] / max(bm25[q].max(), 1e-9))
            systems[f"e004_lin_generic_l{lam}"] = R(lambda q, lam=lam: dense[q] + lam * bm25g[q] / max(bm25g[q].max(), 1e-9))
        res = {k: {**metrics(v), "vs_dense": paired(v, base)} for k, v in systems.items()}
        rb = np.array(systems["bm25_code"]); rd = np.array(base)
        overlap = {f"top{n}": {"both": int(((rd <= n) & (rb <= n)).sum()), "dense_only": int(((rd <= n) & (rb > n)).sum()),
                               "bm25_only": int(((rd > n) & (rb <= n)).sum()), "neither": int(((rd > n) & (rb > n)).sum())}
                   for n in (10, 100, 1000)}
        oracle = {f"oracle_ndcg@10_depth{n}": float((rd <= n).mean()) for n in (20, 50, 100, 200)}
        report["sets"][name] = {"systems": res, "overlap_dense_vs_bm25code": overlap, "oracle_dense": oracle,
                                "seconds": round(time.perf_counter() - t0, 1)}
        cache[name] = {"dense_top200": {q: [data.doc_ids[i] for i in np.argsort(-dense[q], kind="stable")[:200]] for q in qids}}
        print(f"{name}: {len(systems)} systems in {time.perf_counter() - t0:.0f} s", flush=True)
    report["pytrec_check_dev_dense"] = pytrec_check(data, data.sets["dev"], data.dense)
    # Baseline reproduction on TEST (frozen system only): must equal the official MTEB NDCG@10 0.5511.
    tq = data.sets["test"]
    test_ranks = [ranks_from_scores(data.dense(q), data.rel(q)) for q in tq]
    report["test_baseline_dense"] = metrics(test_ranks)
    cache["test"] = {"dense_top200": {q: [data.doc_ids[i] for i in np.argsort(-data.dense(q), kind="stable")[:200]] for q in tq}}
    (out / "campaign.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps(cache), encoding="utf-8")
    summary(report, out)


def run_round2(args):
    """E015 dense pseudo-relevance feedback and E005 BM25 k1/b inside the kept fusion, each against the current best
    (dense + 0.05 * max-normalised generic BM25, k1 1.6, b 0.75). DEV selects; CONFIRMATION must agree."""
    data = Data(Path(args.shards), Path(args.test_shards))
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    report = {"current_best": "dense + 0.05 * bm25_generic(k1 1.6, b 0.75)", "sets": {}}
    grids = [(k1, b) for k1 in (0.5, 0.9, 1.2, 1.6, 2.0) for b in (0.3, 0.5, 0.75, 0.9)]
    bm_by = {}
    for k1, b in grids:
        tok = generic_tokenize
        chunks = [Chunk(d, d, "", d, "dataset_document", 1, 1, data.corpus[d], data.corpus[d], "") for d in data.doc_ids]
        bm_by[(k1, b)] = Retriever(chunks, None, None, Settings(semantic="off"), tokenizer=tok, k1=k1, b=b)
    for name in ("dev", "confirmation"):
        qids = data.sets[name]
        rel = {q: data.rel(q) for q in qids}
        dense = {q: data.dense(q) for q in qids}
        norm = lambda v: v / max(v.max(), 1e-9)
        bm = {kb: {q: norm(np.asarray(r.lexical_scores(generic_tokenize(data.queries[q])), dtype=np.float64)) for q in qids}
              for kb, r in bm_by.items()}
        R = lambda f: [ranks_from_scores(f(q), rel[q]) for q in qids]
        best = R(lambda q: dense[q] + 0.05 * bm[(1.6, 0.75)][q])
        systems = {"current_best": best}
        for (k1, b) in grids:
            for lam in (0.03, 0.05, 0.08):
                systems[f"e005_k1{k1}_b{b}_l{lam}"] = R(lambda q, kb=(k1, b), lam=lam: dense[q] + lam * bm[kb][q])
        for k in (1, 3, 5, 10):
            for beta in (0.1, 0.2, 0.3, 0.5):
                def prf(q, k=k, beta=beta):
                    top = np.argsort(-dense[q], kind="stable")[:k]
                    v = data.Q[q] + beta * data.D[top].mean(axis=0)
                    return data.D @ (v / np.linalg.norm(v)) + 0.05 * bm[(1.6, 0.75)][q]
                systems[f"e015_prf_k{k}_b{beta}"] = R(prf)
        report["sets"][name] = {k: {**metrics(v), "vs_best": paired(v, best)} for k, v in systems.items()}
        print(f"{name}: {len(systems)} systems", flush=True)
    (out / "round2.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    dev, conf = report["sets"]["dev"], report["sets"]["confirmation"]
    lines = ["# Campaign round 2: E015 dense PRF, E005 BM25 k1/b in the kept fusion (vs current best)", ""]
    for prefix in ("e005", "e015"):
        top = sorted((k for k in dev if k.startswith(prefix)), key=lambda k: -dev[k]["ndcg@10"])[:5]
        lines += [f"## {prefix}: top 5 by DEV NDCG@10", "", "| Variant | dev NDCG@10 | Δ vs best [CI] | conf NDCG@10 | Δ vs best [CI] |",
                  "|---|---:|---|---:|---|"]
        for k in top:
            d, c = dev[k]["vs_best"], conf[k]["vs_best"]
            lines.append(f"| {k} | {dev[k]['ndcg@10']:.4f} | {d['delta']:+.4f} [{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}] | "
                         f"{conf[k]['ndcg@10']:.4f} | {c['delta']:+.4f} [{c['ci'][0]:+.4f}, {c['ci'][1]:+.4f}] |")
        lines.append("")
    lines.append(f"Current best: dev {dev['current_best']['ndcg@10']:.4f} / MRR {dev['current_best']['mrr@10']:.4f}; "
                 f"confirmation {conf['current_best']['ndcg@10']:.4f} / MRR {conf['current_best']['mrr@10']:.4f}")
    text = "\n".join(lines) + "\n"
    (out / "round2.md").write_text(text, encoding="utf-8")
    print(text)
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8").write(text)


def fmt(m):
    return " | ".join(f"{m[k]:.4f}" for k in ("ndcg@10", "mrr@10", "r@10", "r@50", "r@100", "r@200", "r@500", "r@1000"))


def summary(report, out):
    lines = ["# Retrieval campaign — diagnostics, E004, E009 (train dev / confirmation; GTE vectors from the frozen run)", "",
             f"Baseline reproduction on TEST (GTE dense, 3,765 q): NDCG@10 {report['test_baseline_dense']['ndcg@10']:.4f}, "
             f"MRR@10 {report['test_baseline_dense']['mrr@10']:.4f}, R@100 {report['test_baseline_dense']['r@100']:.4f} "
             "(official MTEB: 0.5511 / 0.5053 / 0.8943)", "",
             f"pytrec_eval check (dev, dense): {json.dumps(report['pytrec_check_dev_dense'])}", ""]
    head = "| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | R@200 | R@500 | R@1000 | ΔNDCG vs dense [95% CI] | W/L |"
    for name, s in report["sets"].items():
        res = s["systems"]
        best = max((k for k in res if k.startswith("e0")), key=lambda k: res[k]["ndcg@10"])
        show = ["dense", "bm25_code", "bm25_generic", "hybrid_rrf_equal_k60", best]
        lines += [f"## {name} (n={res['dense']['n']}; {s['seconds']} s)", "", head, "|---|" + "---:|" * 10]
        for k in show:
            v = res[k]["vs_dense"]
            lines.append(f"| {k} | {fmt(res[k])} | {v['delta']:+.4f} [{v['ci'][0]:+.4f}, {v['ci'][1]:+.4f}] | {v['wins']}/{v['losses']} |")
        lines += ["", f"Best E00x on {name}: `{best}`", f"Overlap dense vs BM25(code): {json.dumps(s['overlap_dense_vs_bm25code'])}",
                  f"Oracle (dense candidates, perfect rerank): {json.dumps(s['oracle_dense'])}", ""]
    text = "\n".join(lines) + "\n"
    (out / "campaign.md").write_text(text, encoding="utf-8")
    print(text, flush=True)
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8").write(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shards", required=True, help="docs-*/queries-* shards (final-retrieval run)")
    p.add_argument("--test-shards", required=True, help="test-* shards (official-final run)")
    p.add_argument("--output", required=True)
    p.add_argument("--round", type=int, default=1)
    args = p.parse_args()
    (run_round2 if args.round == 2 else run)(args)


if __name__ == "__main__":
    main()

"""E011: cross-encoder reranking of the frozen GTE dense candidates (campaign 2026-09-27).

  preflight   load the reranker, check pairs/s at two max lengths on a few dev queries (projects full-run time)
  score       score (query, doc) pairs for dense top-N of one shard of a query set; writes per-query scores
  evaluate    combine shards; rerank top-N (pure reranker, and rank fusion with dense) on dev/confirmation

Candidates come from benchmark/campaign.py (`candidates.json`, dense top-200 per query). The corpus is not re-embedded.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.campaign import metrics, paired
from benchmark.e005_screen import load_dataset_split

RERANKER = "Alibaba-NLP/gte-reranker-modernbert-base"


def load_model(max_length):
    import torch
    from sentence_transformers import CrossEncoder
    torch.set_num_threads(os.cpu_count() or 4)
    model = CrossEncoder(RERANKER, max_length=max_length, device="cpu", trust_remote_code=False)
    model.model.to(torch.float32)
    return model


def texts(split_needed=("train",)):
    corpus, queries, _ = load_dataset_split("train")
    return corpus, queries


def preflight(args):
    corpus, queries = texts()
    cands = json.loads(Path(args.candidates).read_text())
    qids = cands["dev"]["dense_top200"]
    sample = sorted(qids)[:4]
    for max_length in (512, 1024):
        t0 = time.perf_counter()
        model = load_model(max_length)
        load_s = time.perf_counter() - t0
        pairs = [(queries[q], corpus[d]) for q in sample for d in qids[q][:10]]
        model.predict(pairs[:4], batch_size=4)  # warm-up
        t0 = time.perf_counter()
        model.predict(pairs, batch_size=8, show_progress_bar=False)
        s = time.perf_counter() - t0
        rate = len(pairs) / s
        print(f"max_length {max_length}: load {load_s:.0f} s · {len(pairs)} pairs in {s:.1f} s = {rate:.2f} pairs/s · "
              f"projected 600 dev+conf queries x top-20: {600 * 20 / rate / 60:.0f} runner-min; "
              f"test 3765 x top-20: {3765 * 20 / rate / 60:.0f} runner-min", flush=True)


def score(args):
    corpus, queries = texts()
    cands = json.loads(Path(args.candidates).read_text())
    model = load_model(args.max_length)
    out = {}
    for name in args.sets.split(","):
        qids = sorted(cands[name]["dense_top200"])[args.shard::args.of]
        t0 = time.perf_counter()
        for q in qids:
            docs = cands[name]["dense_top200"][q][:args.depth]
            out.setdefault(name, {})[q] = [float(x) for x in model.predict([(queries[q], corpus[d]) for d in docs], batch_size=8,
                                                                             show_progress_bar=False)]
        print(f"{name} shard {args.shard}/{args.of}: {len(qids)} queries x {args.depth} in {time.perf_counter() - t0:.0f} s", flush=True)
    path = Path(args.output); path.mkdir(parents=True, exist_ok=True)
    (path / f"rerank-{args.shard:02d}.json").write_text(json.dumps({"depth": args.depth, "max_length": args.max_length,
                                                                     "scores": out}), encoding="utf-8")


def evaluate(args):
    _, _, qrels = load_dataset_split("train")
    cands = json.loads(Path(args.candidates).read_text())
    scores, depth, max_length = {}, None, None
    for f in sorted(Path(args.scores).rglob("rerank-*.json")):
        data = json.loads(f.read_text())
        depth, max_length = data["depth"], data["max_length"]
        for name, per in data["scores"].items():
            scores.setdefault(name, {}).update(per)
    report = {"reranker": RERANKER, "depth": depth, "max_length": max_length, "sets": {}}
    lines = [f"# E011 reranker `{RERANKER}` on dense top-{depth} (max_length {max_length})", ""]
    for name in ("dev", "confirmation"):
        per = scores.get(name, {})
        qids = sorted(per)
        top = cands[name]["dense_top200"]
        rel = {q: next(iter(qrels[q])) for q in qids}

        def rank(order_ids, q):
            full = order_ids + [d for d in top[q] if d not in set(order_ids)]
            return full.index(rel[q]) + 1 if rel[q] in full else 10**6  # outside top-200: beyond every cutoff used

        base = [rank(top[q], q) for q in qids]
        systems = {"dense": base}
        systems["rerank_pure"] = [rank([top[q][i] for i in np.argsort(-np.array(per[q]), kind="stable")], q) for q in qids]
        for w in (0.3, 0.5, 0.7):  # weighted RRF of reranker rank and dense rank over the reranked depth
            fused = []
            for q in qids:
                rr = np.argsort(np.argsort(-np.array(per[q]), kind="stable"))
                s = w / (60 + rr + 1) + (1 - w) / (60 + np.arange(len(rr)) + 1)
                fused.append(rank([top[q][i] for i in np.argsort(-s, kind="stable")], q))
            systems[f"rerank_rrf_w{w}"] = fused
        res = {k: {**metrics(v), "vs_dense": paired(v, base)} for k, v in systems.items()}
        report["sets"][name] = res
        lines += [f"## {name} (n={len(qids)})", "", "| System | NDCG@10 | MRR@10 | R@10 | R@50 | ΔNDCG vs dense [95% CI] | W/L |",
                  "|---|---:|---:|---:|---:|---|---|"]
        for k, m in res.items():
            v = m["vs_dense"]
            lines.append(f"| {k} | {m['ndcg@10']:.4f} | {m['mrr@10']:.4f} | {m['r@10']:.4f} | {m['r@50']:.4f} | "
                         f"{v['delta']:+.4f} [{v['ci'][0]:+.4f}, {v['ci'][1]:+.4f}] | {v['wins']}/{v['losses']} |")
        lines.append("")
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    (out / "e011.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    text = "\n".join(lines) + "\n"
    (out / "e011.md").write_text(text, encoding="utf-8")
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8").write(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("preflight"); a.add_argument("--candidates", required=True)
    a = sub.add_parser("score"); a.add_argument("--candidates", required=True); a.add_argument("--sets", default="dev,confirmation")
    a.add_argument("--shard", type=int, required=True); a.add_argument("--of", type=int, required=True)
    a.add_argument("--depth", type=int, default=20); a.add_argument("--max-length", type=int, default=1024)
    a.add_argument("--output", required=True)
    a = sub.add_parser("evaluate"); a.add_argument("--candidates", required=True); a.add_argument("--scores", required=True)
    a.add_argument("--output", required=True)
    args = p.parse_args()
    {"preflight": preflight, "score": score, "evaluate": evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()

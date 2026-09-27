"""E016 (campaign 2026-09-27): encode queries with a longer window; documents stay the cached 512-token vectors.

  embed      one shard of dev+confirmation queries at 512 and at each longer length, same model load and precision
  evaluate   dense and current-best fusion (dense + 0.05 * generic BM25) per length, paired against 512 on dev/confirmation
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

from benchmark.campaign import Data, metrics, paired, ranks_from_scores
from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import GTE, query_sets

LENGTHS = (512, 1024, 2048)


def embed(args):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(os.cpu_count() or 4)
    _, queries, qrels = load_dataset_split("train")
    sets = query_sets(qrels)
    qids = sorted(sets["dev"] + sets["confirmation"])[args.shard::args.of]
    model = SentenceTransformer(GTE, device="cpu")
    model.to(torch.float32)
    lengths = [len(model.tokenizer(queries[q], add_special_tokens=True)["input_ids"]) for q in qids]
    out = {"ids": qids, "token_lengths": lengths, "vectors": {}, "seconds": {}}
    for L in LENGTHS:
        model.max_seq_length = L
        t0 = time.perf_counter()
        v = model.encode([queries[q] for q in qids], batch_size=8, normalize_embeddings=True, convert_to_numpy=True,
                         show_progress_bar=False)
        out["seconds"][L] = time.perf_counter() - t0
        out["vectors"][L] = v.astype(np.float32).tolist()
        print(f"shard {args.shard}: {len(qids)} queries at {L} tokens in {out['seconds'][L]:.0f} s", flush=True)
    path = Path(args.output); path.mkdir(parents=True, exist_ok=True)
    (path / f"qlen-{args.shard:02d}.json").write_text(json.dumps(out), encoding="utf-8")


def evaluate(args):
    data = Data(Path(args.shards), Path(args.test_shards))
    vecs, lengths = {L: {} for L in LENGTHS}, {}
    for f in sorted(Path(args.vectors).rglob("qlen-*.json")):
        d = json.loads(f.read_text())
        for i, q in enumerate(d["ids"]):
            lengths[q] = d["token_lengths"][i]
            for L in LENGTHS:
                vecs[L][q] = np.asarray(d["vectors"][str(L)][i], dtype=np.float32)
    report = {"lengths": LENGTHS, "sets": {}}
    lines = ["# E016: query encoding window (documents fixed at 512)", ""]
    for name in ("dev", "confirmation"):
        qids = data.sets[name]
        tl = np.array([lengths[q] for q in qids])
        bm = {q: data.bm25(q, "generic") for q in qids}
        rel = {q: data.rel(q) for q in qids}
        systems = {}
        for L in LENGTHS:
            dense = {q: data.D @ vecs[L][q] for q in qids}
            systems[f"dense_q{L}"] = [ranks_from_scores(dense[q], rel[q]) for q in qids]
            systems[f"best_fusion_q{L}"] = [ranks_from_scores(dense[q] + 0.05 * bm[q] / max(bm[q].max(), 1e-9), rel[q]) for q in qids]
        cached = [ranks_from_scores(data.dense(q), rel[q]) for q in qids]
        res = {"dense_cached512_fp16": metrics(cached)}
        for k, v in systems.items():
            ref = systems["dense_q512"] if k.startswith("dense") else systems["best_fusion_q512"]
            res[k] = {**metrics(v), "vs_512": paired(v, ref)}
        long = tl > 512
        res["queries_over_512_tokens"] = float(long.mean())
        report["sets"][name] = res
        lines += [f"## {name} (n={len(qids)}; queries > 512 tokens: {long.mean():.0%}; median {int(np.median(tl))} tokens)", "",
                  "| System | NDCG@10 | MRR@10 | R@10 | R@100 | ΔNDCG vs same system at 512 [95% CI] | W/L |", "|---|---:|---:|---:|---:|---|---|",
                  f"| dense, cached (official vectors) | {res['dense_cached512_fp16']['ndcg@10']:.4f} | {res['dense_cached512_fp16']['mrr@10']:.4f} | "
                  f"{res['dense_cached512_fp16']['r@10']:.4f} | {res['dense_cached512_fp16']['r@100']:.4f} | — | — |"]
        for k in systems:
            m, v = res[k], res[k]["vs_512"]
            lines.append(f"| {k} | {m['ndcg@10']:.4f} | {m['mrr@10']:.4f} | {m['r@10']:.4f} | {m['r@100']:.4f} | "
                         f"{v['delta']:+.4f} [{v['ci'][0]:+.4f}, {v['ci'][1]:+.4f}] | {v['wins']}/{v['losses']} |")
        lines.append("")
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    (out / "e016.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    text = "\n".join(lines) + "\n"
    (out / "e016.md").write_text(text, encoding="utf-8")
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8").write(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("embed"); a.add_argument("--shard", type=int, required=True); a.add_argument("--of", type=int, required=True)
    a.add_argument("--output", required=True)
    a = sub.add_parser("evaluate"); a.add_argument("--shards", required=True); a.add_argument("--test-shards", required=True)
    a.add_argument("--vectors", required=True); a.add_argument("--output", required=True)
    args = p.parse_args()
    {"embed": embed, "evaluate": evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()

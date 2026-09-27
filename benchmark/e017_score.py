"""E017 scoring on frozen dense top-20 and paired DEV/CONFIRMATION evaluation."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from benchmark.campaign import metrics, paired
from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets


def score(args):
    import torch
    from sentence_transformers import CrossEncoder

    if args.set not in {"dev", "confirmation"}:
        raise ValueError("score accepts only dev or confirmation; TEST requires a separate frozen final run")
    torch.set_num_threads(4)
    corpus, queries, qrels = load_dataset_split("train")
    expected = set(query_sets(qrels)[args.set])
    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))[args.set]["dense_top200"]
    assert set(candidates) == expected
    qids = sorted(expected)[args.shard::args.of]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{args.set}-{args.shard:02d}-of-{args.of:02d}.json"
    prior = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    assert prior.get("batch", args.batch) == args.batch, "cannot resume with a different inference batch"
    scores = prior.get("scores", {})
    assert set(scores).issubset(set(qids))
    model = CrossEncoder(args.checkpoint, max_length=512, device="cuda", local_files_only=True)
    start = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    for index, q in enumerate(qids):
        if q in scores:
            continue
        docs = candidates[q][:20]
        assert len(docs) == 20 and len(set(docs)) == 20
        pairs = [(queries[q], corpus[d]) for d in docs]
        with torch.amp.autocast("cuda", dtype=torch.float16):
            prediction = model.predict(pairs, batch_size=args.batch, show_progress_bar=False)
        values = [float(v) for v in np.asarray(prediction).reshape(-1)]
        assert len(values) == 20 and all(np.isfinite(values))
        scores[q] = values
        if (index + 1) % 20 == 0 or index + 1 == len(qids):
            path.write_text(json.dumps({"set": args.set, "shard": args.shard,
                                        "of": args.of, "depth": 20, "batch": args.batch,
                                        "scores": scores}), encoding="utf-8")
            elapsed = time.perf_counter() - start
            print(f"score {args.set} {args.shard}/{args.of} {len(scores)}/{len(qids)} "
                  f"elapsed={elapsed:.0f}s peak_gib={torch.cuda.max_memory_allocated()/1024**3:.2f}", flush=True)
            if elapsed > 42 * 60 and len(scores) < len(qids):
                raise TimeoutError("Scoring shard exceeded 42 minutes; saved partial scores")
    print(f"saved={path} queries={len(scores)} seconds={time.perf_counter()-start:.1f}", flush=True)


def evaluate(args):
    _, _, qrels = load_dataset_split("train")
    expected = set(query_sets(qrels)[args.set])
    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))[args.set]["dense_top200"]
    all_scores = {}
    batch_size = None
    for shard in range(args.of):
        path = Path(args.scores) / f"{args.set}-{shard:02d}-of-{args.of:02d}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["set"] == args.set and data["depth"] == 20
        assert data["shard"] == shard and data["of"] == args.of
        if batch_size is None:
            batch_size = data.get("batch")
        else:
            assert data.get("batch") == batch_size, "inference batches differ between shards"
        assert not set(all_scores).intersection(data["scores"])
        all_scores.update(data["scores"])
    assert set(all_scores) == expected and set(candidates) == expected
    base, trained = [], []
    for q in sorted(expected):
        docs = candidates[q]
        rel = next(iter(qrels[q]))
        base.append(docs.index(rel) + 1 if rel in docs else 10**6)
        ranking = np.argsort(-np.asarray(all_scores[q], dtype=np.float64), kind="stable")
        order = [docs[i] for i in ranking] + docs[20:]
        trained.append(order.index(rel) + 1 if rel in order else 10**6)
    result = {"set": args.set, "queries": len(expected), "depth": 20,
              "baseline": metrics(base), "trained": metrics(trained),
              "paired_ndcg": paired(trained, base)}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{args.set}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score")
    p.add_argument("--candidates", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--set", choices=("dev", "confirmation"), required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--of", type=int, default=3)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--output", required=True)
    p = sub.add_parser("evaluate")
    p.add_argument("--candidates", required=True)
    p.add_argument("--set", choices=("dev", "confirmation"), required=True)
    p.add_argument("--of", type=int, default=3)
    p.add_argument("--scores", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    {"score": score, "evaluate": evaluate}[args.command](args)


if __name__ == "__main__":
    main()

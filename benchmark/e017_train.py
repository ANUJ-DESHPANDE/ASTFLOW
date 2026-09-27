"""E017 TRAIN-only hard-negative mining and bounded reranker fine-tuning.

Uses the published GTE document vectors; it never embeds corpus documents.
DEV and CONFIRMATION query IDs are excluded before mining or training.
"""

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np

from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets, text_key

SEED = 20260926
GTE = "Alibaba-NLP/gte-modernbert-base"
RERANKER = "Alibaba-NLP/gte-reranker-modernbert-base"


def train_data():
    corpus, queries, qrels = load_dataset_split("train")
    sets = query_sets(qrels)
    excluded = set(sets["dev"]) | set(sets["confirmation"])
    qids = sorted(set(qrels) - excluded)
    assert len(qids) == 4400 and len(excluded) == 600
    assert all(len(qrels[q]) == 1 for q in qids)
    random.Random(SEED + 17).shuffle(qids)
    return corpus, queries, qrels, qids


def mine(args):
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(4)
    corpus, queries, qrels, qids = train_data()
    doc_ids = sorted(corpus)
    with np.load(args.vectors, allow_pickle=False) as asset:
        assert str(asset["model"]) == GTE
        hashes = [str(h) for h in asset["hashes"]]
        vectors = np.asarray(asset["vectors"], dtype=np.float32)
    assert len(set(hashes)) == len(hashes)
    positions = {h: i for i, h in enumerate(hashes)}
    assert all(text_key(corpus[d]) in positions for d in doc_ids)
    docs = np.ascontiguousarray(vectors[[positions[text_key(corpus[d])] for d in doc_ids]])
    shard_ids = qids[args.shard::args.of]
    model = SentenceTransformer(GTE, device="cuda", local_files_only=True)
    model.max_seq_length = 512
    start = time.perf_counter()
    result = {}
    torch.cuda.reset_peak_memory_stats()
    for at in range(0, len(shard_ids), args.batch):
        batch_ids = shard_ids[at:at + args.batch]
        qvec = model.encode(
            [queries[q] for q in batch_ids], batch_size=args.batch,
            normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)
        score = qvec @ docs.T
        for q, row in zip(batch_ids, score):
            top = np.argsort(-row, kind="stable")[:20]
            result[q] = [doc_ids[i] for i in top]
        if at == 0 or (at // args.batch + 1) % 20 == 0:
            elapsed = time.perf_counter() - start
            print(f"mine shard={args.shard}/{args.of} {at + len(batch_ids)}/{len(shard_ids)} "
                  f"elapsed={elapsed:.0f}s peak_gib={torch.cuda.max_memory_allocated()/1024**3:.2f}", flush=True)
        if time.perf_counter() - start > 42 * 60:
            raise TimeoutError("Mining shard exceeded 42 minutes; reduce --of before retrying")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"train-top20-{args.shard:02d}-of-{args.of:02d}.json"
    path.write_text(json.dumps({"model": GTE, "max_seq": 512, "seed": SEED,
                                "shard": args.shard, "of": args.of, "top20": result}), encoding="utf-8")
    print(f"saved={path} queries={len(result)} seconds={time.perf_counter()-start:.1f}", flush=True)


def load_mined(directory, qids, of):
    found = {}
    for shard in range(of):
        path = Path(directory) / f"train-top20-{shard:02d}-of-{of:02d}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["model"] == GTE and data["max_seq"] == 512
        assert data["shard"] == shard and data["of"] == of
        assert not set(found).intersection(data["top20"])
        found.update(data["top20"])
    assert set(found) == set(qids)
    return found


def fit(args):
    import torch
    from sentence_transformers import CrossEncoder
    from sentence_transformers.cross_encoder.losses import RankNetLoss
    from transformers.optimization import Adafactor

    torch.set_num_threads(4)
    torch.manual_seed(SEED + 18)
    corpus, queries, qrels, qids = train_data()
    mined = load_mined(args.mined, qids, args.of)
    chosen = qids[:args.queries]
    groups = []
    for q in chosen:
        positive = next(iter(qrels[q]))
        positive_key = text_key(corpus[positive])
        seen = {positive_key}
        negatives = []
        for d in mined[q]:
            key = text_key(corpus[d])
            if key not in seen:
                negatives.append(d)
                seen.add(key)
        assert len(negatives) >= 4
        groups.append((q, [positive, *negatives[:4]]))
    random.Random(SEED + 18).shuffle(groups)
    assert len(groups) == args.queries
    model = CrossEncoder(RERANKER, max_length=512, device="cuda", local_files_only=True)
    net = model.model
    net.gradient_checkpointing_enable()
    net.train()
    optimizer = Adafactor(net.parameters(), lr=1e-5, relative_step=False, scale_parameter=False)
    scaler = torch.amp.GradScaler("cuda")
    loss_fn = RankNetLoss(model, mini_batch_size=2)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = {"model": RERANKER, "max_length": 512, "queries": args.queries,
              "pairs": 5 * len(groups), "negatives_per_query": 4, "seed": SEED,
              "model_mini_batch_size": 2, "optimizer": "Adafactor", "lr": 1e-5,
              "objective": "RankNetLoss", "gradient_checkpointing": True,
              "fp16_autocast": True, "train_qids_sha256": hashlib.sha256("\n".join(chosen).encode()).hexdigest()}
    (output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    start = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    step = 0
    losses = []
    labels = torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0], device="cuda")
    for q, docs in groups:
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda", dtype=torch.float16):
            loss = loss_fn([[queries[q]], [[corpus[d] for d in docs]]], [labels])
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        step += 1
        losses.append(float(loss.detach().cpu()))
        if step == len(groups) // 2:
            checkpoint(model, output / "partial", config, step)
        if step % 20 == 0:
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            rate = 5 * step / max(elapsed, 1)
            print(f"fit step={step}/{len(groups)} pairs={5*step}/{5*len(groups)} elapsed={elapsed:.0f}s "
                  f"pairs_per_s={rate:.3f} loss20={np.mean(losses[-20:]):.4f} "
                  f"peak_gib={torch.cuda.max_memory_allocated()/1024**3:.2f}", flush=True)
            if elapsed > 39 * 60 and step < len(groups):
                checkpoint(model, output / "partial", config, step)
                raise TimeoutError("Training stopped at 39 minutes; partial checkpoint saved")
    checkpoint(model, output / "final", config, step)
    summary = {**config, "steps": step, "train_seconds": time.perf_counter()-start,
               "peak_gib": torch.cuda.max_memory_allocated()/1024**3,
               "last_20_loss": float(np.mean(losses[-20:]))}
    (output / "train-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def checkpoint(model, path, config, step):
    path.mkdir(parents=True, exist_ok=True)
    model.model.save_pretrained(path, safe_serialization=True)
    model.tokenizer.save_pretrained(path)
    (path / "e017.json").write_text(json.dumps({**config, "steps": step}, indent=2), encoding="utf-8")
    print(f"checkpoint={path} step={step}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("mine")
    p.add_argument("--vectors", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--of", type=int, default=4)
    p.add_argument("--batch", type=int, default=8)
    p = sub.add_parser("fit")
    p.add_argument("--mined", required=True)
    p.add_argument("--of", type=int, default=4)
    p.add_argument("--queries", type=int, default=300)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    {"mine": mine, "fit": fit}[args.command](args)


if __name__ == "__main__":
    main()

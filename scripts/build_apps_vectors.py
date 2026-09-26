"""Assemble the official run's AppsRetrieval document vectors into the file `astflow snippets` downloads.

Input: the `gte-*` shard artifacts of the final-retrieval workflow (docs-NN.npy + docs-NN.json with content keys).
Checks: frozen model, every CoIR Apps corpus document exactly once with a matching content hash, and live
re-encoding of 16 documents through the product's own embedder (min cosine >= 0.995). Output: one .npz.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from backend.app.config import FROZEN_MODEL, Settings
from backend.app.corpus import PROBE_COS, read_corpus, resolve
from backend.app.retrieval.embeddings import Embedder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    keys, mats = [], []
    for meta_path in sorted(Path(args.shards).rglob("docs-*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["model"] == FROZEN_MODEL and meta["max_seq"] == 512, meta_path
        keys += meta["keys"]
        mats.append(np.load(meta_path.with_suffix(".npy")))
    vectors = np.vstack(mats).astype(np.float32)
    corpus = read_corpus(resolve("apps")[1])
    texts = {hashlib.sha256(t.encode()).hexdigest(): t for t in corpus.values()}
    assert len(keys) == len(vectors) == len(corpus), "misaligned shard rows"
    # Identical document texts (the corpus has some) share one content key: keep one vector per key.
    first = {}
    for i, k in enumerate(keys):
        first.setdefault(k, i)
    print(f"{len(keys)} shard rows, {len(first)} distinct texts")
    keys, vectors = list(first), vectors[list(first.values())]
    assert set(keys) == set(texts), f"shards cover {len(set(keys) & set(texts))} of {len(texts)} corpus texts"
    settings = Settings()
    assert settings.model == FROZEN_MODEL
    embedder = Embedder(settings)
    assert embedder.load(download=True) is not None, embedder.reason
    probe = list(range(0, len(keys), len(keys) // 16))[:16]
    live = embedder.encode([texts[keys[i]] for i in probe])
    cos = (live * vectors[probe]).sum(axis=1)
    print(f"{len(keys)} documents · live probe min cos {cos.min():.5f} over {len(probe)}")
    assert cos.min() >= PROBE_COS
    np.savez_compressed(args.output, model=np.array(FROZEN_MODEL), hashes=np.array(keys), vectors=vectors)
    print(f"wrote {args.output} ({Path(args.output).stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

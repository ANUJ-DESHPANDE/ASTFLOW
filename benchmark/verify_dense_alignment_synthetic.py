"""Post-fix mechanism verification for the dense-retrieval id-alignment fix, without
requiring network access or the real MiniLM model / CoIR-Retrieval/apps corpus.

See docs/audit/POST-FIX-RETRIEVAL-VERIFICATION.md for the full write-up and results.
This does NOT measure real semantic retrieval quality -- it proves the pipeline
mechanics (id alignment, window->parent aggregation, ranking direction, embedding
numerics) are correct, using a deterministic hash-based bag-of-words proxy encoder
run through the real Embedder/Retriever/precompute_embeddings.py/mteb_appretrieval.py
code. Run with: python3 -m benchmark.verify_dense_alignment_synthetic
"""
import csv
import hashlib
import json
import random
import re
import shutil
from pathlib import Path

import numpy as np

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever
from benchmark import mteb_appretrieval, precompute_embeddings
from benchmark.metrics import metrics

DIM = 64
N_DOCS = 500
TOPICS = {
    "sort": "sort array ascending order comparator quicksort mergesort pivot swap elements",
    "database": "database connection pool retry logic transaction commit rollback query cursor",
    "image": "resize image crop thumbnail pixel width height scale interpolation",
    "http": "http request authenticate header token bearer client response status",
    "graph": "graph traversal breadth depth first search node edge visited queue",
    "string": "string parse tokenize split trim substring regex pattern match",
    "cache": "cache eviction least recently used lru ttl expire key value store",
    "auth": "authenticate session login password hash salt verify credentials token",
}


def bow_vector(text: str, dim: int = DIM) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()):
        vec[int(hashlib.sha256(token.encode()).hexdigest(), 16) % dim] += 1.0
    return vec


def normalize_rows(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vecs / norms).astype(np.float32)


def fake_encode(self, texts, use_windows=False, window_size=256, overlap=64):
    if not use_windows:
        return normalize_rows(np.array([bow_vector(t) for t in texts], dtype=np.float32))
    results = []
    for text in texts:
        words = text.split()
        window_texts = [text] if len(words) <= window_size else \
            [" ".join(words[s:s + window_size]) for s in range(0, len(words), window_size - overlap)]
        results.append(normalize_rows(np.array([bow_vector(w) for w in window_texts], dtype=np.float32)))
    return results


def build_synthetic_corpus(seed: int = 1234):
    random.seed(seed)
    topic_names = list(TOPICS.keys())
    docs = []
    for i in range(N_DOCS):
        topic = topic_names[i % len(topic_names)]
        filler = (TOPICS[topic] + " ") * (60 if i % 7 == 0 else 3)
        docs.append((f"d{i}", f"def handle_{topic}_{i}():\n    # {TOPICS[topic]}\n    {filler}"))
    shuffled = docs[:]
    random.shuffle(shuffled)  # deliberately NOT id-sorted, like the real corpus.jsonl export
    queries = [(f"q{i}", topic) for i, topic in enumerate(topic_names)]
    return docs, shuffled, queries


def main():
    work = Path("/tmp/verify_dense_alignment_synthetic")
    shutil.rmtree(work, ignore_errors=True)
    export_dir, cache_dir = work / "export", work / "cache"
    (cache_dir / "datasets" / "apps").mkdir(parents=True)
    export_dir.mkdir(parents=True)

    docs, shuffled, queries = build_synthetic_corpus()
    with (export_dir / "corpus.jsonl").open("w") as f:
        for doc_id, text in shuffled:
            f.write(json.dumps({"_id": doc_id, "title": "", "text": text}) + "\n")
    (cache_dir / "datasets" / "apps" / "corpus.jsonl").write_text((export_dir / "corpus.jsonl").read_text())
    with (export_dir / "queries.jsonl").open("w") as f:
        for qid, topic in queries:
            f.write(json.dumps({"_id": qid, "text": "how do I " + " ".join(TOPICS[topic].split()[:4])}) + "\n")
    relevance = {qid: {did: 1 for did, t in docs if f"handle_{topic}_" in t} for qid, topic in queries}
    (export_dir / "qrels").mkdir()
    with (export_dir / "qrels" / "test.tsv").open("w", newline="") as f:
        writer = csv.DictWriter(f, ["query-id", "corpus-id", "score"], delimiter="\t")
        writer.writeheader()
        for qid, rel in relevance.items():
            for did in rel:
                writer.writerow({"query-id": qid, "corpus-id": did, "score": 1})

    Embedder.load = lambda self, download=False: setattr(self, "model", object()) or self.model
    Embedder.encode = fake_encode
    fixed_settings = Settings(cache=cache_dir)
    precompute_embeddings.Settings = lambda: fixed_settings
    mteb_appretrieval.Settings = lambda: fixed_settings

    precompute_embeddings.precompute()
    meta = json.loads((cache_dir / "datasets" / "apps_fixed.meta.json").read_text())
    fixed_array = np.load(cache_dir / "datasets" / "apps_fixed.npy", allow_pickle=True)
    by_id_current = dict(zip(meta["ids"], fixed_array))

    checked = mismatched = 0
    for doc_id, text in docs:
        checked += 1
        fresh = fake_encode(None, [text], use_windows=True)[0]
        windows = by_id_current.get(doc_id)
        if windows is None or windows.shape != fresh.shape or not np.allclose(windows, fresh, atol=1e-6):
            mismatched += 1
    print(f"[id integrity] {checked} checked, {checked - mismatched} correctly mapped, {mismatched} mismatched")

    chunks_sorted = [Chunk(did, did, "", did, "dataset_document", 1, len(t.splitlines()), t, t,
                     hashlib.sha256(t.encode()).hexdigest()) for did, t in sorted(docs)]
    file_order_ids = meta["ids"]
    agree = sum(1 for i in range(len(chunks_sorted)) if chunks_sorted[i].chunk_id == file_order_ids[i])
    print(f"[before/after] file order vs sorted order agreement: {agree}/{len(chunks_sorted)} ({100*agree/len(chunks_sorted):.1f}%)")

    embedder = Embedder(fixed_settings)
    embedder.load()
    retriever_broken = Retriever(chunks_sorted, list(fixed_array), embedder, fixed_settings)
    retriever_fixed = Retriever(chunks_sorted, [by_id_current[c.chunk_id] for c in chunks_sorted], embedder, fixed_settings)
    for label, retriever in [("BROKEN (positional, pre-fix)", retriever_broken), ("FIXED (id-aligned, post-fix)", retriever_fixed)]:
        per_query = []
        for qid, topic in queries:
            qtext = "how do I " + " ".join(TOPICS[topic].split()[:4])
            rows, _ = retriever.rank(qtext, mode="dense", boosts=False)
            ranking = [r["chunk"].chunk_id for r in rows]
            per_query.append(metrics(ranking, relevance[qid]))
        ndcg = sum(s["ndcg@10"] for s in per_query) / len(per_query)
        mrr = sum(s["mrr"] for s in per_query) / len(per_query)
        recall = sum(s["recall@10"] for s in per_query) / len(per_query)
        print(f"{label:32s} Dense NDCG@10={ndcg:.4f}  MRR={mrr:.4f}  Recall@10={recall:.4f}")

    report = mteb_appretrieval.evaluate_export(export_dir, "test", 0, work / "out")
    print("\n[synthetic diagnostic, all modes]")
    for mode, result in report["baselines"].items():
        if result.get("status") == "evaluated":
            print(f"  {mode:9s} ndcg@10={result['ndcg@10']:.4f} mrr={result['mrr']:.4f} recall@10={result['recall@10']:.4f}")


if __name__ == "__main__":
    main()

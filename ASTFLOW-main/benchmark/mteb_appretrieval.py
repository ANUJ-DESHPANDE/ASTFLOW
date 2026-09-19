"""Evaluate retrieval over the real CoIR Apps corpus used by MTEB AppsRetrieval.

This is a direct dataset adapter, not a submission to the official MTEB runner.
The corpus contains standalone Python solutions: graph signals do not apply.
Dataset configurations and fields are validated before use.
"""
import argparse
import csv
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever
from benchmark.metrics import metrics

DATASET = "CoIR-Retrieval/apps"


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def load_export(directory: Path, split: str = "test"):
    corpus = {str(row["_id"]): (row.get("title", "") + "\n" + row["text"]).strip() for row in read_jsonl(directory / "corpus.jsonl")}
    queries = {str(row["_id"]): row["text"] for row in read_jsonl(directory / "queries.jsonl")}
    relevance = {}
    with (directory / "qrels" / f"{split}.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            qid, did = str(row["query-id"]), str(row["corpus-id"])
            score = int(row["score"])
            if score > 0:
                if qid not in queries or did not in corpus:
                    raise ValueError(f"Qrels reference a missing query/document: {qid}/{did}")
                relevance.setdefault(qid, {})[did] = score
    if not corpus or not relevance:
        raise ValueError("Dataset needs a nonempty corpus and positive relevance judgments")
    return corpus, queries, relevance


def download_export(directory: Path, split: str):
    try:
        import datasets
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("Install the optional adapter: python -m pip install -e '.[benchmark]'") from exc
    revision = HfApi().dataset_info(DATASET).sha
    configs = datasets.get_dataset_config_names(DATASET, revision=revision)
    if not {"corpus", "queries", "default"} <= set(configs):
        raise ValueError(f"Dataset configuration changed: found {configs}")
    directory.mkdir(parents=True, exist_ok=True)
    cache = ROOT / ".astflow" / "datasets" / "hub"
    for config, filename, required in [("corpus", "corpus.jsonl", {"_id", "text"}), ("queries", "queries.jsonl", {"_id", "text"})]:
        splits = datasets.get_dataset_split_names(DATASET, config, revision=revision)
        selected = config if config in splits else splits[0] if len(splits) == 1 else None
        if not selected:
            raise ValueError(f"Ambiguous {config} splits: {splits}")
        rows = datasets.load_dataset(DATASET, config, split=selected, revision=revision, cache_dir=str(cache))
        if not required <= set(rows.column_names):
            raise ValueError(f"Unexpected {config} fields: {rows.column_names}")
        with (directory / filename).open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    splits = datasets.get_dataset_split_names(DATASET, "default", revision=revision)
    if split not in splits:
        raise ValueError(f"Split {split!r} not found; available: {splits}")
    rows = datasets.load_dataset(DATASET, "default", split=split, revision=revision, cache_dir=str(cache))
    if not {"query-id", "corpus-id", "score"} <= set(rows.column_names):
        raise ValueError(f"Unexpected qrels fields: {rows.column_names}")
    (directory / "qrels").mkdir(exist_ok=True)
    with (directory / "qrels" / f"{split}.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["query-id", "corpus-id", "score"], delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (directory / "metadata.json").write_text(json.dumps({"dataset": DATASET, "revision": revision, "datasets_version": datasets.__version__, "split": split}, indent=2), encoding="utf-8")


def evaluate_export(directory: Path, split: str, max_queries: int, output: Path):
    corpus, queries, relevance = load_export(directory, split)
    query_ids = sorted(relevance)
    if max_queries > 0:
        query_ids = query_ids[:max_queries]
    settings = Settings()
    embedder = Embedder(settings)
    embedder.load()
    chunks = [Chunk(did, did, "", did, "dataset_document", 1, len(text.splitlines()), text, text,
                    hashlib.sha256(text.encode()).hexdigest()) for did, text in sorted(corpus.items())]
    identity = hashlib.sha256((settings.model + "\n" + "\n".join(c.chunk_id + ":" + c.content_hash for c in chunks)).encode()).hexdigest()[:24]
    vector_path = settings.cache / "datasets" / f"apps-{identity}.npy"
    if embedder.model is None:
        embeddings = None
    elif vector_path.exists():
        embeddings = np.load(vector_path, allow_pickle=False)
    else:
        print(f"Embedding {len(chunks)} public dataset documents on CPU…", flush=True)
        embeddings = embedder.encode([c.text for c in chunks])
        vector_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(vector_path, embeddings, allow_pickle=False)
    retriever = Retriever(chunks, embeddings, embedder, settings)
    report = {"dataset": DATASET, "split": split, "query_count": len(query_ids), "corpus_count": len(corpus),
              "model": embedder.status, "official_mteb_run": False,
              "scope": "query subset against full corpus" if len(query_ids) < len(relevance) else "all split queries against full corpus",
              "limits": "No JavaScript structural evidence; standalone Python documents. MRR uses at most 50 candidates. This direct adapter is not the official MTEB harness.",
              "baselines": {}}
    metadata_path = directory / "metadata.json"
    if metadata_path.exists():
        report["dataset_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
    for mode in ["bm25", "dense", "hybrid"]:
        if mode == "dense" and embeddings is None:
            report["baselines"][mode] = {"status": "unavailable"}
            continue
        measured = []
        for qid in query_ids:
            started = time.perf_counter()
            rows, _ = retriever.rank(queries[qid], mode=mode, boosts=False)
            ranking = [r["chunk"].chunk_id for r in rows]
            measured.append({"query_id": qid, **metrics(ranking, relevance[qid]), "latency_ms": (time.perf_counter() - started) * 1000, "ranking": ranking})
        report["baselines"][mode] = {"status": "evaluated", **{key: round(statistics.mean(r[key] for r in measured), 4) for key in ("ndcg@10", "mrr", "recall@10")},
                                       "latency_median_ms": round(statistics.median(r["latency_ms"] for r in measured), 2), "queries": measured}
    output.mkdir(parents=True, exist_ok=True)
    (output / "apps.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# CoIR AppsRetrieval adapter run", "", f"{report['query_count']} queries / {report['corpus_count']} documents · {report['scope']}", "", report["limits"], "",
             "| Baseline | NDCG@10 | MRR (top 50) | Recall@10 | Median ms |", "| --- | ---: | ---: | ---: | ---: |"]
    for mode, result in report["baselines"].items():
        if result["status"] == "evaluated":
            lines.append(f"| {mode} | {result['ndcg@10']:.4f} | {result['mrr']:.4f} | {result['recall@10']:.4f} | {result['latency_median_ms']:.2f} |")
    (output / "apps.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / ".astflow/datasets/apps")
    parser.add_argument("--split", default="test")
    parser.add_argument("--download", action="store_true", help="Explicitly download the public CoIR dataset")
    parser.add_argument("--max-queries", type=int, default=32, help="0 runs all queries; default is an adapter smoke run")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark/results")
    args = parser.parse_args()
    if args.download:
        download_export(args.data, args.split)
    evaluate_export(args.data, args.split, args.max_queries, args.output)


if __name__ == "__main__":
    main()

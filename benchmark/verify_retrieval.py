"""One-command retrieval verification: generate -> freeze -> cross-evaluate -> diagnose.

  python -m benchmark.verify_retrieval --self-test
      Fast: golden cases through every evaluator. No dataset or model needed.

  python -m benchmark.verify_retrieval --data .astflow/datasets/apps --split all
      Full: integrity-check the exported AppsRetrieval data, rank every judged query
      with the UNCHANGED production Retriever (bm25, dense, hybrid), freeze each run
      to a TREC file, score the same bytes with ASTFLOW's evaluator, pytrec_eval,
      ir_measures and (if built) NIST trec_eval, then write forensics and a manifest.

Representation matches benchmark/run_mteb.py (the official path): documents sorted by
id, text = title + newline + text, one normalized MiniLM vector per document, ranking
depth 1000, boosts off. `--dense-windows 256:64` (E003) swaps the single vector for id-aligned
sliding-window vectors, max-pooled per document, and proves their alignment before ranking.
There is no "reranked" mode: the E002 cross-encoder was rejected and is not part of the
product (Retriever.rank accepts only bm25, dense, hybrid).
Exits non-zero on any integrity failure or evaluator disagreement.
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from benchmark.mteb_appretrieval import load_export
from benchmark.trust import evaluation, forensics, integrity

EXPECTED_DATASET_REVISION = "f22508f96b7a36c2415181ed8bb76f76e04ae2d5"
DEPTH = 1000


def git_state() -> dict:
    run = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()
    dirty = run("status", "--porcelain")
    return {"commit": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current"),
            "dirty": bool(dirty), "dirty_files": dirty.splitlines()[:50]}


def self_test(trec_eval: str | None) -> bool:
    import random
    import tempfile
    rng = random.Random(20260923)
    pool = [f"d{i}" for i in range(300)]
    rankings, qrels = {"golden-perfect": ["a", "b"], "golden-absent": ["b"], "golden-empty": []}, \
        {"golden-perfect": {"a": 1}, "golden-absent": {"a": 1}, "golden-empty": {"a": 1}}
    for q in range(300):
        qrels[f"r{q}"] = {d: 1 for d in rng.sample(pool, rng.randint(1, 3))}
        rankings[f"r{q}"] = rng.sample(pool, rng.randint(0, 100))
    tmp = Path(tempfile.mkdtemp())
    evaluation.write_run(rankings, tmp / "run.trec")
    evaluation.write_qrels(qrels, tmp / "qrels.txt")
    report = evaluation.cross_check(rankings, qrels, tmp / "run.trec", tmp / "qrels.txt", trec_eval)
    for name, agg in report["evaluators"].items():
        print(f"  {name:12s} ndcg@10={agg['ndcg@10']:.10f}")
    print("  trec_eval:", report.get("trec_eval_binary") or "NOT AVAILABLE (build https://github.com/usnistgov/trec_eval)")
    print("  agreement:", "PASS" if report["agree"] else f"FAIL {report['disagreements'][:3]}")
    return report["agree"]


def mteb_published_stats() -> dict | None:
    try:
        import mteb
        path = Path(mteb.__file__).parent / "descriptive_stats" / "Retrieval" / "AppsRetrieval.json"
        stats = json.loads(path.read_text())
        return stats.get("test", stats)
    except (ImportError, OSError, ValueError):
        return None


def model_identity(embedder, settings) -> dict:
    info = {"name": settings.model, "commit_hash": None, "weights_sha256": None, "max_seq_length": None}
    try:
        first = embedder.model[0]
        info["commit_hash"] = getattr(first.auto_model.config, "_commit_hash", None)
        info["max_seq_length"] = int(embedder.model.max_seq_length)
    except Exception:
        pass
    weights = settings.cache / "models" / settings.model.replace("/", "--") / "model.safetensors"
    if weights.exists():
        info["weights_sha256"] = hashlib.sha256(weights.read_bytes()).hexdigest()
    return info


def load_vectors(chunks, embedder, settings, model_info) -> tuple[np.ndarray, dict]:
    identity = hashlib.sha256(json.dumps([model_info["name"], model_info["weights_sha256"],
                                          [c.chunk_id + ":" + c.content_hash for c in chunks]]).encode()).hexdigest()[:24]
    path = settings.cache / "datasets" / f"trust-apps-{identity}.npy"
    meta_path = path.with_suffix(".meta.json")
    ids = [c.chunk_id for c in chunks]
    started, status = time.perf_counter(), "computed"
    if path.exists() and meta_path.exists() and json.loads(meta_path.read_text())["ids"] == ids:
        vectors, status = np.load(path, allow_pickle=False), "reused (ids verified identical)"
    else:
        vectors = embedder.encode([c.text for c in chunks])
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors, allow_pickle=False)
        meta_path.write_text(json.dumps({"ids": ids, "model": model_info}), encoding="utf-8")
    stats = integrity.check_vectors(vectors, len(chunks))
    # Alignment proof against the real model: row i must be the embedding of chunk i's own text.
    probe = sorted({int(i) for i in np.linspace(0, len(chunks) - 1, 20)})
    fresh = embedder.encode([chunks[i].text for i in probe])
    cosines = [float(vectors[i] @ fresh[j]) for j, i in enumerate(probe)]
    integrity._check(min(cosines) > 0.999, f"Cached vectors misaligned with documents: min cosine {min(cosines)}")
    stats.update(cache_file=str(path), cache_status=status, seconds=round(time.perf_counter() - started, 2),
                 alignment_probe={"documents": len(probe), "ids": [chunks[i].chunk_id for i in probe],
                                  "min_cosine": min(cosines), "aligned": f"{len(probe)}/{len(probe)}"})
    return vectors, stats


def load_window_vectors(chunks, embedder, settings, model_info, whole, window: int, overlap: int) -> tuple[list, dict]:
    """E003: id-aligned sliding-window vectors, one (windows x dim) array per document, in chunk order."""
    identity = hashlib.sha256(json.dumps([model_info["name"], model_info["weights_sha256"], window, overlap,
                                          [c.chunk_id + ":" + c.content_hash for c in chunks]]).encode()).hexdigest()[:24]
    path = settings.cache / "datasets" / f"trust-apps-windows-{identity}.npz"
    ids = [c.chunk_id for c in chunks]
    started, status = time.perf_counter(), "computed"
    if path.exists() and [str(i) for i in np.load(path, allow_pickle=False)["ids"]] == ids:
        stored = np.load(path, allow_pickle=False)
        flat, counts, status = stored["vectors"], stored["counts"], "reused (ids verified identical)"
    else:
        grouped = embedder.encode([c.text for c in chunks], use_windows=True, window_size=window, overlap=overlap)
        flat, counts = np.concatenate(grouped).astype(np.float32), np.array([len(g) for g in grouped])
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, vectors=flat, counts=counts, ids=np.array(ids))
    integrity._check(len(counts) == len(chunks) and counts.min() >= 1, "Every document needs at least one window")
    integrity._check(int(counts.sum()) == len(flat), "Window count does not match stored vectors")
    grouped = np.split(flat, np.cumsum(counts)[:-1])
    # Expected windows per document straight from the tokenizer, independent of the cached arrays.
    stride = window - overlap
    lengths = [len(embedder.model.tokenizer.tokenize(c.text)) for c in chunks]
    expected = [1 if n <= window else len(range(0, n, stride)) for n in lengths]
    integrity._check(expected == counts.tolist(), "Window counts differ from tokenizer-derived counts")
    stats = integrity.check_vectors(flat, int(counts.sum()))
    # Alignment proof 1: a single-window document is embedded from its full text, so it must equal its whole-doc vector.
    single = [i for i, n in enumerate(counts) if n == 1]
    single_cos = np.einsum("ij,ij->i", np.stack([grouped[i][0] for i in single]), whole[single])
    integrity._check(float(single_cos.min()) > 0.999, f"Single-window vectors misaligned: min cosine {single_cos.min()}")
    # Alignment proof 2: re-embed probe documents one at a time; every window must match its stored row.
    probe = sorted({int(i) for i in np.linspace(0, len(chunks) - 1, 20)} | set([i for i, n in enumerate(counts) if n > 1][::400]))
    fresh = embedder.encode([chunks[i].text for i in probe], use_windows=True, window_size=window, overlap=overlap)
    cosines = [float(np.min(np.einsum("ij,ij->i", grouped[i], f))) for i, f in zip(probe, fresh)]
    integrity._check(min(cosines) > 0.999, f"Window vectors misaligned with documents: min cosine {min(cosines)}")
    stats.update(documents=len(chunks), windows=int(counts.sum()), multi_window_documents=int((counts > 1).sum()),
                 max_windows=int(counts.max()), window=window, overlap=overlap, cache_file=str(path), cache_status=status,
                 seconds=round(time.perf_counter() - started, 2),
                 alignment_single_window={"documents": len(single), "min_cosine_vs_whole_doc": float(single_cos.min())},
                 alignment_probe={"documents": len(probe), "ids": [chunks[i].chunk_id for i in probe], "min_cosine": min(cosines)})
    return list(grouped), stats


def full_run(args) -> int:
    # Record the code state the run starts from; a long run can outlive later commits.
    git_at_start = git_state()
    from backend.app.retrieval.embeddings import Embedder
    from backend.app.retrieval.search import Retriever
    out = Path(args.out)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    data = Path(args.data)
    corpus, queries, qrels = load_export(data, "test")
    data_stats = integrity.check_dataset(data, corpus, queries, qrels)
    meta = json.loads((data / "metadata.json").read_text()) if (data / "metadata.json").exists() else {}
    revision = meta.get("revision")
    if revision != EXPECTED_DATASET_REVISION and not args.allow_unknown_revision:
        raise integrity.IntegrityError(f"Dataset revision {revision!r} != expected {EXPECTED_DATASET_REVISION}")
    judged = evaluation.judged_queries(qrels)
    published = mteb_published_stats()
    if published and not getattr(args, "skip_published_count_check", False):  # independent check: MTEB ships its own counts for this task
        rel = published["relevant_docs_statistics"]
        integrity._check(data_stats["documents"] == published["num_documents"], f"Documents {data_stats['documents']} != MTEB's {published['num_documents']}")
        integrity._check(len(judged) == published["num_queries"], f"Judged queries {len(judged)} != MTEB's {published['num_queries']}")
        integrity._check(data_stats["positive_pairs"] == rel["num_relevant_docs"], f"Positive qrels {data_stats['positive_pairs']} != MTEB's {rel['num_relevant_docs']}")
    if args.split != "all":
        split = json.loads((ROOT / "benchmark/dev_split.json").read_text())
        keep = set(split["dev_query_ids" if args.split == "dev" else "confirmation_query_ids"])
        judged = [q for q in judged if q in keep]
    if args.max_queries:
        judged = judged[:args.max_queries]
    qrels_eval = {q: qrels[q] for q in judged}

    settings = Settings(ts_enrich=False)
    modes = args.modes.split(",")
    embedder, vectors, vector_stats, model_info = None, None, None, {"name": None}
    if set(modes) - {"bm25"}:
        embedder = Embedder(settings)
        if embedder.load() is None:
            raise integrity.IntegrityError(f"Dense/hybrid requested but model unavailable: {embedder.reason}")
        model_info = model_identity(embedder, settings)
    chunks = sorted((Chunk(d, d, "", d, "dataset_document", 1, max(1, len(t.splitlines())), t, t,
                           hashlib.sha256(t.encode()).hexdigest()) for d, t in corpus.items()), key=lambda c: c.chunk_id)
    integrity._check([c.chunk_id for c in chunks] == sorted(corpus), "Chunk order is not the sorted document id order")
    dense_windows = getattr(args, "dense_windows", None)  # callers that build their own Namespace predate E003
    if embedder:
        vectors, vector_stats = load_vectors(chunks, embedder, settings, model_info)
        if dense_windows:
            window, overlap = (int(x) for x in dense_windows.split(":"))
            vectors, window_stats = load_window_vectors(chunks, embedder, settings, model_info, vectors, window, overlap)
            vector_stats = {"whole_document": vector_stats, "windows": window_stats}
    retriever = Retriever(chunks, vectors, embedder, settings)
    corpus_ids = set(corpus)

    qrels_path = out / "apps.qrels"
    qrels_sha = evaluation.write_qrels(qrels_eval, qrels_path)
    runs, reports, run_hashes, latency = {}, {}, {}, {}
    for mode in modes:
        rankings, times = {}, []
        for qid in judged:
            started = time.perf_counter()
            rows, _ = retriever.rank(queries[qid], mode=mode, boosts=False, limit=DEPTH)
            times.append((time.perf_counter() - started) * 1000)
            rankings[qid] = [r["chunk"].chunk_id for r in rows[:DEPTH]]
        integrity.check_rankings(rankings, corpus_ids, judged, DEPTH)
        run_path = out / "runs" / f"{args.tag}-{mode}.trec"
        run_hashes[mode] = evaluation.write_run(rankings, run_path, tag=f"astflow-{mode}")
        reports[mode] = evaluation.cross_check(rankings, qrels_eval, run_path, qrels_path, args.trec_eval)
        runs[mode] = rankings
        latency[mode] = {"median_ms": statistics.median(times), "mean_ms": statistics.fmean(times),
                         "p95_ms": float(np.percentile(times, 95))}
        agg = reports[mode]["evaluators"]["reference"]
        print(f"{mode:7s} ndcg@10={agg['ndcg@10']:.5f} mrr@10={agg['mrr@10']:.5f} r@10={agg['recall@10']:.5f} "
              f"r@100={agg['recall@100']:.5f} agree={reports[mode]['agree']}")

    diag = {"buckets": {m: forensics.rank_buckets(r, qrels_eval, judged) for m, r in runs.items()},
            "mode_comparison": forensics.mode_comparison(runs, qrels_eval, judged)}
    if "hybrid" in runs:
        diag["oracle_ceiling_hybrid"] = {f"top{k}": forensics.oracle_ceiling(runs["hybrid"], qrels_eval, judged, k)
                                         for k in (10, 20, 50, 100, 500, 1000)}
    for mode, rep in reports.items():
        lines = [f"{q}\t" + "\t".join(f"{rep['per_query'][ev][q]['ndcg@10']:.6f}" for ev in rep["per_query"]) for q in judged]
        (out / f"per-query-{args.tag}-{mode}.tsv").write_text("query\t" + "\t".join(rep["per_query"]) + "\n" + "\n".join(lines) + "\n")

    manifest = {
        "generated_by": "benchmark/verify_retrieval.py", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": git_at_start, "environment": integrity.environment(),
        "dataset": {"name": "CoIR-Retrieval/apps (MTEB AppsRetrieval)", "revision": revision, "split": "test",
                    "query_selection": args.split, "evaluated_queries": len(judged), **data_stats,
                    **integrity.fingerprint(corpus, queries, qrels), "qrels_file_sha256": qrels_sha},
        "retrieval_config": {"representation": (f"id-aligned sliding windows {dense_windows} (window:overlap word-pieces), max over windows, title\\ntext"
                                                if dense_windows else "one vector per document (no windows), title\\ntext"), "depth": DEPTH,
                             "candidates": settings.candidates, "rrf_k": settings.rrf_k,
                             "lexical_weight": settings.lexical_weight, "semantic_weight": settings.semantic_weight,
                             "bm25_k1": retriever.bm25.k1, "bm25_b": retriever.bm25.b, "dense_threshold": 0.05,
                             "boosts": False, "reranker": "none"},
        "model": model_info, "vectors": vector_stats, "run_sha256": run_hashes, "latency": latency,
        "evaluation_protocol": "trec_eval -c semantics; canonical scores n-rank+1; linear gain NDCG; MRR@10 = RR within top 10",
        "evaluators": {m: {"aggregates": r["evaluators"], "agree": r["agree"], "disagreements": r["disagreements"][:20],
                           "trec_eval_binary": r.get("trec_eval_binary")} for m, r in reports.items()},
        "forensics": diag,
    }
    (out / f"manifest-{args.tag}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    ok = all(r["agree"] for r in reports.values())
    print("EVALUATOR AGREEMENT:", "PASS" if ok else "FAIL")
    print("manifest:", out / f"manifest-{args.tag}.json")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--data", default=str(ROOT / ".astflow/datasets/apps"))
    parser.add_argument("--out", default=str(ROOT / "benchmark/verification"))
    parser.add_argument("--split", choices=["all", "dev", "confirmation"], default="all")
    parser.add_argument("--modes", default="bm25,dense,hybrid")
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--tag", default="baseline")
    parser.add_argument("--trec-eval", default=None, help="Path to a NIST trec_eval binary")
    parser.add_argument("--allow-unknown-revision", action="store_true")
    parser.add_argument("--dense-windows", default=None, metavar="WINDOW:OVERLAP",
                        help="E003: embed documents as id-aligned sliding windows (e.g. 256:64) and max-pool; default one vector")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test(args.trec_eval) else 1)
    sys.exit(full_run(args))


if __name__ == "__main__":
    main()

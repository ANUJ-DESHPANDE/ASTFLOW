"""Indexing / query / memory measurements on real repositories (audit only).

    .venv/Scripts/python.exe audit/tools/scale_perf.py <repo> [<repo> ...] --out audit/evidence/perf-scale.json

For each repository, with the embedding model already loaded: cold index (fresh cache), cached re-index, process RSS,
search latency through investigate() (P50/P95/P99 over 3 x 10 questions), and Retriever.rank latency per mode.
"""
import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.agent.investigate import investigate  # noqa: E402
from backend.app.config import Settings  # noqa: E402
from backend.app.indexing.service import IndexService  # noqa: E402

QUESTIONS = ["Where is the main entry point?", "How are errors handled?", "Where is input validated?",
             "Which function parses the options?", "How is a response sent?", "Where are settings stored?",
             "How does routing work?", "Where is the cache cleared?", "How are files read?", "What calls the logger?"]


def pct(v, p):
    v = sorted(v); k = (len(v) - 1) * p / 100; lo = int(k); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("repos", nargs="+"); ap.add_argument("--out", required=True)
    args = ap.parse_args()
    proc = psutil.Process()
    out = {"rss_start_mb": round(proc.memory_info().rss / 2**20)}
    for repo in args.repos:
        # The model is looked up inside the cache folder, so a fresh cache must be given the model by local path;
        # otherwise ASTFLOW falls back to lexical-only search (an earlier run of this script measured exactly that).
        model = str(Path(__file__).resolve().parents[2] / ".astflow" / "models" / "sentence-transformers--all-MiniLM-L6-v2")
        service = IndexService(Settings(cache=Path(tempfile.mkdtemp()), ts_enrich=True, model=model))
        t = time.perf_counter(); service.embedder.load(); load_s = time.perf_counter() - t
        t = time.perf_counter(); idx = service.index(repo); cold = time.perf_counter() - t
        assert idx.manifest["semantic"]["available"] and idx.retriever.embeddings is not None, "dense retrieval not active"
        t = time.perf_counter(); service.index(repo); warm = time.perf_counter() - t
        rss = proc.memory_info().rss / 2**20
        investigate(idx, "warm up", "working-tree")
        lat = []
        for _ in range(3):
            for q in QUESTIONS:
                t = time.perf_counter(); investigate(idx, q, "working-tree"); lat.append((time.perf_counter() - t) * 1000)
        modes = {}
        for mode in ("bm25", "dense", "hybrid"):
            ms = []
            for q in QUESTIONS:
                t = time.perf_counter(); idx.retriever.rank(q, mode=mode, boosts=False, limit=1000); ms.append((time.perf_counter() - t) * 1000)
            modes[mode] = round(statistics.median(ms), 1)
        name = Path(repo).name
        out[name] = {"files": idx.manifest["file_count"], "chunks": idx.manifest["chunk_count"], "edges": idx.manifest["edge_count"],
                     "model_load_s": round(load_s, 2), "index_cold_s": round(cold, 2), "index_cached_s": round(warm, 3),
                     "rss_after_index_mb": round(rss), "search_ms": {"p50": round(pct(lat, 50), 1), "p95": round(pct(lat, 95), 1), "p99": round(pct(lat, 99), 1), "n": len(lat)},
                     "rank_median_ms": modes}
        print(name, json.dumps(out[name]))
    json.dump(out, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()

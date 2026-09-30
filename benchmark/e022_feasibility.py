"""CPU feasibility of the one cached E022 joint relevance model on TRAIN only."""

import hashlib
import json
import ctypes
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import CrossEncoder

from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from benchmark.e017_train import train_data
from benchmark.e019_operator_rerank import load_docs

OUT = Path("benchmark/results/E022-strong-reranker")
REVISION = "f7481e6055501a30fb19d090657df9ec1f79ab2c"
SNAPSHOT = Path.home() / ".cache/huggingface/hub/models--Alibaba-NLP--gte-reranker-modernbert-base/snapshots" / REVISION
MODEL = "Alibaba-NLP/gte-reranker-modernbert-base"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process_rss():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    data = Counters()
    data.cb = ctypes.sizeof(data)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                   ctypes.byref(data), data.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return int(data.PeakWorkingSetSize)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(8)
    corpus, queries, qrels, train_ids = train_data()
    sample = train_ids[500:505]
    ids, docs = load_docs(corpus, ".venv-gpu/apps-corpus-vectors-gte-modernbert-base.npz")
    embedder = Embedder(Settings())
    assert embedder.load(), embedder.reason
    baseline_ms, rerank_ms, combined_ms, peak = [], [], [], process_rss()
    start = time.perf_counter()
    cross = CrossEncoder(str(SNAPSHOT), max_length=512, device="cpu", local_files_only=True)
    load_s = time.perf_counter() - start
    parameters = sum(p.numel() for p in cross.model.parameters())
    per_query = []
    for q in sample:
        t0 = time.perf_counter()
        vector = embedder.encode([queries[q]], kind="query")[0]
        dense = docs @ vector
        top = np.argsort(-dense, kind="stable")[:50]
        t1 = time.perf_counter()
        pairs = [(queries[q], corpus[ids[i]]) for i in top]
        scores = np.asarray(cross.predict(pairs, batch_size=8, show_progress_bar=False)).reshape(-1)
        t2 = time.perf_counter()
        assert len(scores) == 50 and np.isfinite(scores).all()
        baseline_ms.append((t1 - t0) * 1000)
        rerank_ms.append((t2 - t1) * 1000)
        combined_ms.append((t2 - t0) * 1000)
        peak = max(peak, process_rss())
        per_query.append({"query_id": q, "dense_end_to_end_ms": baseline_ms[-1],
                          "reranker_only_ms": rerank_ms[-1], "e022_end_to_end_ms": combined_ms[-1]})
        print(f"TRAIN sample {q}: rerank {rerank_ms[-1]:.1f} ms", flush=True)
    report = {"model": MODEL, "revision": REVISION, "weight_sha256": digest(SNAPSHOT / "model.safetensors"),
              "tokenizer_sha256": digest(SNAPSHOT / "tokenizer.json"), "source_path": str(SNAPSHOT),
              "parameters": parameters, "device": "cpu", "precision": "float32",
              "max_length": 512, "joint_query_document_scoring": True,
              "input_format": "CrossEncoder.predict([(query, document), ...])",
              "batch_size": 8, "cpu_threads": 8, "sample_queries": len(sample),
              "sample_ids_sha256": hashlib.sha256("\n".join(sample).encode()).hexdigest(),
              "load_s": load_s, "peak_process_rss_bytes": peak,
              "dense_end_to_end_p50_ms": float(np.percentile(baseline_ms, 50)),
              "dense_end_to_end_p95_ms": float(np.percentile(baseline_ms, 95)),
              "reranker_only_p50_ms": float(np.percentile(rerank_ms, 50)),
              "reranker_only_p95_ms": float(np.percentile(rerank_ms, 95)),
              "e022_end_to_end_p50_ms": float(np.percentile(combined_ms, 50)),
              "e022_end_to_end_p95_ms": float(np.percentile(combined_ms, 95)),
              "per_query": per_query,
              "note": "Fixed five-TRAIN-query CPU sample. Includes query encoding and dense matrix score; excludes model load."}
    (OUT / "feasibility.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "model_selection.json").write_text(json.dumps({"primary_model": MODEL,
        "revision": REVISION, "selection_reason": "Cached pretrained joint query-document relevance cross-encoder; E017 used the same architecture and showed CPU-compatible local weights.",
        "fallback": None, "selection_before_dev": True}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

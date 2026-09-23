"""Fail-loudly data and run invariants, plus reproducibility fingerprints."""
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path

import numpy as np


class IntegrityError(AssertionError):
    pass


def _check(condition: bool, message: str):
    if not condition:
        raise IntegrityError(message)


def raw_jsonl_ids(path: Path) -> list[str]:
    """Read ids before any dict conversion, so duplicates cannot be silently collapsed."""
    ids = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                _check(isinstance(row.get("_id"), (str, int)), f"Row without usable _id in {path}")
                ids.append(str(row["_id"]))
    return ids


def check_dataset(directory: Path, corpus: dict, queries: dict, qrels: dict) -> dict:
    corpus_ids, query_ids = raw_jsonl_ids(directory / "corpus.jsonl"), raw_jsonl_ids(directory / "queries.jsonl")
    dup_docs = [i for i, n in Counter(corpus_ids).items() if n > 1]
    dup_queries = [i for i, n in Counter(query_ids).items() if n > 1]
    _check(not dup_docs, f"Duplicate corpus ids: {dup_docs[:5]}")
    _check(not dup_queries, f"Duplicate query ids: {dup_queries[:5]}")
    for ident in corpus_ids + query_ids:
        _check(ident and not any(c.isspace() for c in ident), f"Id unusable in TREC files: {ident!r}")
    empty = [d for d, t in corpus.items() if not t.strip()]
    _check(not empty, f"Empty corpus documents: {empty[:5]}")
    for qid, docs in qrels.items():
        _check(qid in queries, f"Qrel query {qid} not in queries")
        for did, grade in docs.items():
            _check(did in corpus, f"Qrel document {did} (query {qid}) not in corpus")
            _check(isinstance(grade, int), f"Non-integer relevance for {qid}/{did}")
    grades = Counter(g for docs in qrels.values() for g in docs.values())
    return {"documents": len(corpus_ids), "queries_in_file": len(query_ids),
            "judged_queries": sum(1 for d in qrels.values() if any(g > 0 for g in d.values())),
            "qrel_rows": sum(len(d) for d in qrels.values()),
            "positive_pairs": sum(1 for d in qrels.values() for g in d.values() if g > 0),
            "relevance_grades": {str(k): v for k, v in sorted(grades.items())},
            "binary_relevance": set(grades) <= {0, 1}}


def fingerprint(corpus: dict, queries: dict, qrels: dict) -> dict:
    h = lambda lines: hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return {"corpus_sha256": h(f"{d}\t{hashlib.sha256(t.encode()).hexdigest()}" for d, t in sorted(corpus.items())),
            # Same formula as run_mteb.py's run_metadata "corpus_sha256", so a new run can be
            # matched byte-for-byte against the corpus behind the historical official runs.
            "corpus_sha256_run_mteb_formula": h(f"{d}:{hashlib.sha256(t.encode()).hexdigest()}" for d, t in sorted(corpus.items())),
            "queries_sha256": h(f"{q}\t{hashlib.sha256(t.encode()).hexdigest()}" for q, t in sorted(queries.items())),
            "qrels_sha256": h(f"{q}\t{d}\t{g}" for q in sorted(qrels) for d, g in sorted(qrels[q].items()))}


def check_vectors(vectors: np.ndarray, expected_rows: int, expected_dim: int | None = None) -> dict:
    _check(vectors.ndim == 2, f"Vector matrix must be 2-D, got {vectors.shape}")
    _check(len(vectors) == expected_rows, f"{len(vectors)} vectors for {expected_rows} documents")
    if expected_dim:
        _check(vectors.shape[1] == expected_dim, f"Dimension {vectors.shape[1]} != {expected_dim}")
    finite = np.isfinite(vectors).all(axis=1)
    norms = np.linalg.norm(vectors, axis=1)
    _check(bool(finite.all()), f"{int((~finite).sum())} non-finite vectors")
    _check(bool((norms > 0).all()), f"{int((norms == 0).sum())} zero vectors")
    _check(bool(np.allclose(norms, 1.0, atol=1e-3)), f"Vectors not normalized: norm range {norms.min()}..{norms.max()}")
    return {"rows": int(len(vectors)), "dim": int(vectors.shape[1]), "dtype": str(vectors.dtype),
            "norm_min": float(norms.min()), "norm_max": float(norms.max()), "norm_mean": float(norms.mean()),
            "nan": int(np.isnan(vectors).sum()), "inf": int(np.isinf(vectors).sum()), "zero_vectors": int((norms == 0).sum())}


def check_rankings(rankings: dict[str, list[str]], corpus_ids: set, judged: list[str], depth: int) -> dict:
    missing = [q for q in judged if q not in rankings]
    _check(not missing, f"Run is missing {len(missing)} judged queries, e.g. {missing[:5]}")
    for qid, ranked in rankings.items():
        _check(len(ranked) == len(set(ranked)), f"Duplicate documents in ranking for {qid}")
        _check(len(ranked) <= depth, f"Ranking for {qid} deeper than {depth}")
        bad = [d for d in ranked if d not in corpus_ids]
        _check(not bad, f"Ranking for {qid} contains unknown document ids {bad[:3]}")
    return {"queries": len(rankings), "empty_rankings": sum(1 for r in rankings.values() if not r),
            "mean_depth": float(np.mean([len(r) for r in rankings.values()])) if rankings else 0.0}


def environment() -> dict:
    import importlib.metadata as md
    packages = {}
    for name in ("mteb", "sentence-transformers", "transformers", "torch", "numpy", "scipy", "rank-bm25",
                 "pytrec-eval-terrier", "ir-measures", "datasets", "huggingface-hub"):
        try:
            packages[name] = md.version(name)
        except md.PackageNotFoundError:
            packages[name] = None
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = None
    return {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor() or None, "device": device, "packages": packages}

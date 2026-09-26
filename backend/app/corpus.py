"""Snippet-corpus retrieval: rank standalone code snippets for a natural-language query.

This is the screening task's setting (CoIR Apps: problem statement -> Python solution) as a product feature, using the
same Retriever as repository search and the official benchmark. A corpus is a BEIR/CoIR-style JSONL file
(`_id`, `text`, optional `title`); `apps` is the public CoIR Apps corpus.

Versions (P1): each corpus file is one version of the snippet library. Vectors are cached per model by snippet
*content* hash, so indexing a new version embeds only the snippets whose text changed.
Evolutionary retrieval (bonus): searching several versions at once ranks every distinct snippet text once and folds
snippets that are identical across versions into a single result listing each version (and id) it appears in, so
unchanged code does not fill the top 10 with copies; changed variants remain separate, labelled results.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever

APPS_EXPORT = ROOT / ".astflow" / "datasets" / "apps"


def read_corpus(path: Path) -> dict[str, str]:
    snippets = {}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if "_id" not in row or "text" not in row:
                raise ValueError(f"{path}:{number}: each line needs '_id' and 'text'")
            snippets[str(row["_id"])] = (row.get("title", "") + "\n" + row["text"]).strip()
    if not snippets:
        raise ValueError(f"{path} contains no snippets")
    return snippets


def resolve(spec: str) -> tuple[str, Path]:
    """`apps`, `name=path.jsonl` or `path.jsonl` (version named after the file) -> (version, path)."""
    if spec == "apps":
        path = APPS_EXPORT / "corpus.jsonl"
        if not path.exists():
            from benchmark.mteb_appretrieval import download_export
            download_export(APPS_EXPORT, "test")
        return "apps", path
    name, _, location = spec.rpartition("=")
    path = Path(location).expanduser().resolve()
    return name or path.stem, path


class VectorCache:
    """Per-model vectors keyed by snippet content hash (append-only; unchanged snippets are never re-embedded)."""

    def __init__(self, settings: Settings):
        slug = hashlib.sha256(settings.model.encode()).hexdigest()[:12]
        self.directory = settings.cache / "corpus-vectors" / slug
        self.index_path, self.vector_path = self.directory / "hashes.json", self.directory / "vectors.npy"
        meta = json.loads(self.index_path.read_text(encoding="utf-8")) if self.index_path.exists() else {}
        self.rows = {h: i for i, h in enumerate(meta.get("hashes", []))} if meta.get("model") == settings.model else {}
        self.vectors = np.load(self.vector_path) if self.rows else None
        self.model = settings.model

    def get(self, hashes: list[str], texts: list[str], embedder: Embedder):
        missing = [i for i, h in enumerate(hashes) if h not in self.rows]
        if missing:
            new = embedder.encode([texts[i] for i in missing])
            if new is None:
                return None, {"reused": 0, "computed": 0}
            new = np.asarray(new, dtype=np.float32)
            base = len(self.rows)
            self.vectors = new if self.vectors is None else np.vstack([self.vectors, new])
            for offset, i in enumerate(missing):  # `hashes` are distinct, so rows follow the stacked order
                self.rows[hashes[i]] = base + offset
            self._save()
        return self.vectors[[self.rows[h] for h in hashes]], {"reused": len(hashes) - len(missing), "computed": len(missing)}

    def _save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.rows, key=self.rows.get)
        np.save(self.vector_path, self.vectors)
        self.index_path.write_text(json.dumps({"model": self.model, "hashes": ordered}), encoding="utf-8")


@dataclass
class SnippetIndex:
    versions: dict[str, dict[str, str]]
    settings: Settings = field(default_factory=Settings)
    embedder: Embedder | None = None

    def __post_init__(self):
        started = time.perf_counter()
        self.embedder = self.embedder or Embedder(self.settings)
        # One retrieval unit per distinct snippet text; `members` records every (version, id) that holds it.
        self.members: dict[str, list[tuple[str, str]]] = {}
        texts: dict[str, str] = {}
        for version, snippets in self.versions.items():
            for sid, text in sorted(snippets.items()):
                digest = hashlib.sha256(text.encode()).hexdigest()
                self.members.setdefault(digest, []).append((version, sid))
                texts[digest] = text
        hashes = sorted(texts)
        chunks = [Chunk(h, h, "", self.members[h][0][1], "dataset_document", 1, max(1, len(texts[h].splitlines())),
                        texts[h], texts[h], h) for h in hashes]
        vectors, self.embedding_cache = VectorCache(self.settings).get(hashes, [texts[h] for h in hashes], self.embedder)
        self.retriever = Retriever(chunks, vectors, self.embedder, self.settings)
        self.stats = {"versions": {v: len(s) for v, s in self.versions.items()}, "distinct_snippets": len(hashes),
                      "embedding_cache": self.embedding_cache, "semantic": self.embedder.status,
                      "index_seconds": round(time.perf_counter() - started, 2)}

    def search(self, query: str, top_k: int = 10, mode: str = "hybrid"):
        started = time.perf_counter()
        if mode != "bm25" and self.retriever.embeddings is None:
            mode = "bm25"  # truthful fallback: reported below, never labelled hybrid
        rows, _ = self.retriever.rank(query, mode=mode, boosts=False, limit=top_k)
        results = []
        for rank, row in enumerate(rows[:top_k], 1):
            chunk, members = row["chunk"], self.members[row["chunk"].chunk_id]
            results.append({"rank": rank, "score": round(row["score"], 6), "id": members[0][1],
                            "versions": sorted({v for v, _ in members}), "occurrences": [f"{v}:{i}" for v, i in members],
                            "lines": chunk.end_line, "snippet": chunk.text,
                            "evidence": {"lexical_rank": row["evidence"]["lexical_rank"],
                                         "semantic_rank": row["evidence"]["semantic_rank"]}})
        return {"query": query, "mode": mode, "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "results": results}

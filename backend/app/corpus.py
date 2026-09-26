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
from backend.app.retrieval.embeddings import Embedder, ModelUnavailable
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


# Document vectors computed for the official AppsRetrieval run (frozen model, 8,765 documents), published with the
# submission release so that `astflow snippets` does not spend ~4 CPU-hours re-embedding the corpus. They are keyed by
# the same content hash as this cache and are spot-checked against live encoding before use.
PREBUILT = {"Alibaba-NLP/gte-modernbert-base":
            "https://github.com/ANUJ-DESHPANDE/ASTFLOW/releases/download/v1.0-submission/apps-corpus-vectors-gte-modernbert-base.npz"}
PREBUILT_MIN = 256  # only worth a download when at least this many snippets would otherwise be embedded
PROBE_COS = 0.995  # live re-encoding agreement required (batch-padding noise measured at 7e-4)


def log(message: str):
    import sys
    print(message, file=sys.stderr, flush=True)


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

    def prebuilt(self, hashes: list[str], texts: list[str], embedder: Embedder, url: str | None = None) -> int:
        """Merge published vectors for the requested snippets after a live spot check; returns rows added."""
        import urllib.request
        url = url or PREBUILT.get(self.model)
        if not url or embedder.load() is None:
            return 0
        log(f"Fetching precomputed {self.model} vectors for this corpus from {url} …")
        try:
            with urllib.request.urlopen(url, timeout=120) as reply:
                import io
                data = np.load(io.BytesIO(reply.read()), allow_pickle=False)
                model, keys, vectors = str(data["model"]), [str(k) for k in data["hashes"]], data["vectors"]
        except Exception as exc:  # network or format: fall back to computing, loudly
            log(f"Could not use precomputed vectors ({type(exc).__name__}: {exc}); embedding on CPU instead.")
            return 0
        wanted = {h: i for i, h in enumerate(hashes) if h not in self.rows}
        rows = [(h, j) for j, h in enumerate(keys) if h in wanted]
        if model != self.model or not rows:
            log("Precomputed vectors do not match this model or corpus; embedding on CPU instead.")
            return 0
        probe = rows[:: max(1, len(rows) // 8)][:8]
        live = np.asarray(embedder.encode([texts[wanted[h]] for h, _ in probe]), dtype=np.float32)
        cos = float(min((live * vectors[[j for _, j in probe]]).sum(axis=1)))
        if cos < PROBE_COS:
            log(f"Precomputed vectors disagree with live encoding (cos {cos:.4f}); embedding on CPU instead.")
            return 0
        base = len(self.rows)
        add = np.asarray(vectors[[j for _, j in rows]], dtype=np.float32)
        self.vectors = add if self.vectors is None else np.vstack([self.vectors, add])
        for offset, (h, _) in enumerate(rows):
            self.rows[h] = base + offset
        self._save()
        log(f"Using {len(rows)} precomputed vectors (live spot check: min cos {cos:.4f} over {len(probe)} snippets).")
        return len(rows)

    def get(self, hashes: list[str], texts: list[str], embedder: Embedder):
        missing, fetched = [i for i, h in enumerate(hashes) if h not in self.rows], 0
        if len(missing) >= PREBUILT_MIN and self.model in PREBUILT:
            fetched = self.prebuilt(hashes, texts, embedder)
            missing = [i for i, h in enumerate(hashes) if h not in self.rows]
        if missing:
            log(f"Embedding {len(missing)} snippets with {self.model} on CPU (one time; vectors are cached) …")
            new = embedder.encode([texts[i] for i in missing])
            if new is None:
                return None, {"reused": 0, "computed": 0, "precomputed": 0}
            new = np.asarray(new, dtype=np.float32)
            base = len(self.rows)
            self.vectors = new if self.vectors is None else np.vstack([self.vectors, new])
            for offset, i in enumerate(missing):  # `hashes` are distinct, so rows follow the stacked order
                self.rows[hashes[i]] = base + offset
            self._save()
        return self.vectors[[self.rows[h] for h in hashes]], {"reused": len(hashes) - len(missing) - fetched,
                                                              "computed": len(missing), "precomputed": fetched}

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

    def search(self, query: str, top_k: int = 10, mode: str | None = None):
        started = time.perf_counter()
        mode = mode or self.settings.retrieval  # frozen: dense, exactly as in the official AppsRetrieval run
        if mode != "bm25" and self.retriever.embeddings is None:
            if self.settings.semantic != "off":
                raise ModelUnavailable(self.embedder.reason)
            mode = "bm25"  # explicit lexical-only mode: reported below, never labelled dense or hybrid
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

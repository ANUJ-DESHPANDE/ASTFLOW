import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.app.config import ROOT, Settings
from backend.app.indexing.discovery import list_versions, read_snapshot, snapshot_hash
from backend.app.parsing.javascript import parse_file
from backend.app.retrieval.embedding_cache import EmbeddingCache
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever
from backend.app.storage.store import load_index, save_index
from backend.app.structure.graph import ProjectGraph
from backend.app.structure.resolver import resolve_structure


@dataclass
class Index:
    manifest: dict
    files: dict
    symbols: list
    chunks: list
    edges: list
    extra: dict
    retriever: Retriever
    graph: ProjectGraph


class IndexService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.embedder = Embedder(self.settings)
        self.embedding_cache = EmbeddingCache(self.settings.cache / "embedding_cache.sqlite")
        self.indexes = {}
        self.registry = {}
        self.repo_path = None
        self.lock = threading.RLock()
        self.status = {"state": "idle", "stage": "Ready to index", "progress": 0}
        state = self.settings.cache / "state.json"
        if state.exists():
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
                self.registry = data.get("registry", {})
                self.repo_path = data.get("repo_path")
            except (ValueError, OSError):
                pass

    def _alias(self, repo: str, version: str):
        return repo + "\n" + version

    def _persist(self):
        self.settings.cache.mkdir(parents=True, exist_ok=True)
        temp = self.settings.cache / f"state-{uuid.uuid4().hex}.tmp"
        temp.write_text(json.dumps({"repo_path": self.repo_path, "registry": self.registry}), encoding="utf-8")
        temp.replace(self.settings.cache / "state.json")

    def _construct(self, data):
        manifest, files, symbols, chunks, edges, extra, embeddings = data
        if embeddings is not None and manifest.get('embedding_model') != self.settings.model:
            raise ValueError('Indexed embedding model differs from the configured model; reindex this version')
        return Index(manifest, files, symbols, chunks, edges, extra,
                     Retriever(chunks, embeddings, self.embedder, self.settings), ProjectGraph(symbols, edges))

    def index(self, repo_path: str, version: str = "working-tree"):
        with self.lock:
            started = time.perf_counter()
            try:
                repo = Path(repo_path).expanduser().resolve(strict=True)
                self.status = {"state": "indexing", "stage": "Reading source snapshot", "progress": 5}
                files, revision, warnings = read_snapshot(repo, version, self.settings)
                if not files:
                    raise ValueError("No supported JavaScript source files were found")
                self.status.update(stage="Loading CPU search model", progress=12)
                self.embedder.load()
                digest = snapshot_hash(files)
                identity = f"{repo}\n{revision}\n{digest}\n{self.settings.fingerprint()}\n{self.embedder.status}"
                key = hashlib.sha256(identity.encode()).hexdigest()[:24]
                folder = self.settings.cache / "indexes" / key
                cached = None
                if (folder / "manifest.json").exists():
                    try:
                        cached = self._construct(load_index(folder))
                    except ValueError:
                        # Preserve corrupt evidence for diagnosis; explicit reindex rebuilds it.
                        folder.rename(folder.with_name(key + '.corrupt.' + uuid.uuid4().hex))
                if cached is not None:
                    index = cached
                else:
                    parsed = []
                    for i, (path, source) in enumerate(files.items()):
                        self.status.update(stage=f"Parsing {path}", progress=15 + int(40 * i / len(files)))
                        parsed.append(parse_file(path, source))
                    symbols = sorted([s for f in parsed for s in f.symbols], key=lambda s: s.symbol_id)
                    chunks = sorted([c for f in parsed for c in f.chunks], key=lambda c: c.chunk_id)
                    for chunk in chunks:
                        chunk.version_key = key
                    self.status.update(stage="Resolving source relationships", progress=58)
                    edges, unresolved, sequences = resolve_structure(parsed)
                    warnings.extend(d for f in parsed for d in f.diagnostics)
                    enrichment = {"status": "disabled", "edges_added": 0, "edges_confirmed": 0}
                    if self.settings.ts_enrich:
                        from backend.app.structure.typescript import enrich
                        self.status.update(stage="Checking language-service evidence", progress=68)
                        edges, enrichment = enrich(files, symbols, edges)
                    self.status.update(stage="Embedding code chunks", progress=78)
                    embeddings, embed_stats = self._embed_chunks(chunks)
                    manifest = {"version_key": key, "repository_path": str(repo), "repository_name": repo.name,
                                "version": version, "resolved_revision": revision, "source_hash": digest,
                                "indexed_at": datetime.now(timezone.utc).isoformat(), "embedding_model": self.embedder.status["model"],
                                "file_count": len(files), "symbol_count": len(symbols), "chunk_count": len(chunks),
                                "edge_count": len(edges), "configuration_hash": self.settings.fingerprint(),
                                "semantic": self.embedder.status, "enrichment": enrichment, "warnings": warnings,
                                "embedding_cache": embed_stats,
                                "index_latency_ms": round((time.perf_counter() - started) * 1000, 2)}
                    extra = {"unresolved": unresolved, "sequences": sequences,
                             "imports": {f.path: f.imports for f in parsed}, "exports": {f.path: f.exports for f in parsed}}
                    staging = self.settings.cache / "indexes" / (key + "." + uuid.uuid4().hex + ".tmp")
                    save_index(staging, manifest, files, symbols, chunks, edges, extra, embeddings)
                    # Windows sync/antivirus software can briefly lock a newly
                    # closed SQLite file. Publish atomically, with bounded retry.
                    for attempt in range(6):
                        try:
                            staging.rename(folder)
                            break
                        except (FileExistsError, PermissionError):
                            if (folder / "manifest.json").exists():
                                break
                            if attempt == 5:
                                raise
                            time.sleep(.1 * (2 ** attempt))
                    index = self._construct((manifest, files, symbols, chunks, edges, extra, embeddings))
                self.repo_path = str(repo)
                self.registry[self._alias(str(repo), version)] = key
                # Immutable keys can always be used to open the precise indexed snapshot.
                self.indexes[key] = index
                self._persist()
                self.status = {"state": "ready", "stage": "Index ready", "progress": 100,
                               "version": version, "manifest": index.manifest,
                               "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                return index
            except Exception as exc:
                self.status = {"state": "error", "stage": str(exc), "progress": 0}
                raise

    def _embed_chunks(self, chunks):
        """Encode only chunks whose exact indexed text has never been embedded by
        this model before; reuse persisted vectors for the rest. A chunk's
        search_text is unchanged whenever its file, name, imports, comments and
        source span are unchanged, which is the common case when only some
        files change between indexed versions."""
        stats = {"reused": 0, "computed": 0}
        if not chunks or self.embedder.load() is None:
            return None, stats
        model_name = self.settings.model
        hashes = [hashlib.sha256(c.search_text.encode()).hexdigest() for c in chunks]
        cached = self.embedding_cache.get_many(model_name, hashes)
        missing = [i for i, h in enumerate(hashes) if h not in cached]
        if missing:
            vectors = self.embedder.encode([chunks[i].search_text for i in missing])
            if vectors is None:
                return None, stats
            new_items = {hashes[i]: vectors[j] for j, i in enumerate(missing)}
            self.embedding_cache.put_many(model_name, new_items)
            cached.update(new_items)
        stats["reused"] = len(chunks) - len(missing)
        stats["computed"] = len(missing)
        embeddings = np.stack([cached[h] for h in hashes]).astype(np.float32)
        return embeddings, stats

    def get(self, version: str = "working-tree") -> Index:
        if not self.repo_path:
            raise ValueError("Index a repository first")
        key = self.registry.get(self._alias(self.repo_path, version), version)
        # Never interpret an untrusted version string as a filesystem path.
        if key not in self.registry.values() or not re_key(key):
            raise ValueError(f"Version {version!r} is not indexed; select it and index it first")
        if key not in self.indexes:
            self.indexes[key] = self._construct(load_index(self.settings.cache / "indexes" / key))
        return self.indexes[key]

    def repository(self, version: str | None = None):
        if not self.repo_path:
            return {"path": None, "name": None, "files": [], "indexes": [], "demo_path": str(ROOT / "examples" / "demo-repo")}
        manifests = []
        for alias, key in list(self.registry.items()):
            repo, alias_version = alias.rsplit("\n", 1)
            if repo == self.repo_path:
                index = self.get(key)
                manifests.append({**index.manifest, "version": alias_version})
        latest = self.indexes.get(manifests[-1]["version_key"]) if manifests else None
        if version:
            key = self.registry.get(self._alias(self.repo_path, version))
            latest = self.get(key) if key else None
        return {"path": self.repo_path, "name": Path(self.repo_path).name,
                "files": sorted(latest.files) if latest else [], "indexes": manifests,
                "demo_path": str(ROOT / "examples" / "demo-repo")}

    def versions(self):
        versions = list_versions(Path(self.repo_path)) if self.repo_path else []
        known = {v['name'] for v in versions}
        for alias in self.registry:
            repo, name = alias.rsplit('\n', 1)
            if repo == self.repo_path and name not in known:
                versions.append({'name': name, 'commit': None, 'label': name})
                known.add(name)
        for version in versions:
            key = self.registry.get(self._alias(self.repo_path, version["name"]))
            version.update(indexed=bool(key), version_key=key)
        return versions


def re_key(value: str):
    return len(value) == 24 and all(c in "0123456789abcdef" for c in value)

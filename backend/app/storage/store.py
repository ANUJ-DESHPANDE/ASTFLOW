import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import numpy as np

from backend.app.models.entities import Chunk, Edge, Symbol


def save_index(folder: Path, manifest: dict, files: dict[str, str], symbols: list[Symbol],
               chunks: list[Chunk], edges: list[Edge], extra: dict, embeddings):
    folder.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(folder / "index.sqlite")) as db:
        db.executescript("""
            CREATE TABLE files (path TEXT PRIMARY KEY, source TEXT NOT NULL);
            CREATE TABLE symbols (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE chunks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE edges (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, data TEXT NOT NULL);
        """)
        db.executemany("INSERT INTO files VALUES (?, ?)", sorted(files.items()))
        db.executemany("INSERT INTO symbols VALUES (?, ?)", [(s.symbol_id, json.dumps(asdict(s))) for s in symbols])
        db.executemany("INSERT INTO chunks VALUES (?, ?)", [(c.chunk_id, json.dumps(asdict(c))) for c in chunks])
        db.executemany("INSERT INTO edges(data) VALUES (?)", [(json.dumps(asdict(e)),) for e in edges])
        db.execute("INSERT INTO metadata VALUES ('extra', ?)", (json.dumps(extra),))
        db.execute("INSERT INTO metadata VALUES ('manifest', ?)", (json.dumps(manifest),))
        db.commit()
    if embeddings is not None:
        np.save(folder / "embeddings.npy", embeddings, allow_pickle=False)
    (folder / "embedding_rows.json").write_text(json.dumps([c.chunk_id for c in chunks]), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _load_index(folder: Path):
    database = folder / "index.sqlite"
    if not database.is_file():
        raise ValueError("Index database is missing; rebuild this snapshot")
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        files = dict(db.execute("SELECT path, source FROM files ORDER BY path"))
        symbols = [Symbol(**json.loads(row[0])) for row in db.execute("SELECT data FROM symbols ORDER BY id")]
        # Embedding rows must match insertion order, not symbol sort order.
        chunks = [Chunk(**json.loads(row[0])) for row in db.execute("SELECT data FROM chunks ORDER BY rowid")]
        edges = [Edge(**json.loads(row[0])) for row in db.execute("SELECT data FROM edges ORDER BY id")]
        extra = json.loads(db.execute("SELECT data FROM metadata WHERE key='extra'").fetchone()[0])
        manifest = json.loads(db.execute("SELECT data FROM metadata WHERE key='manifest'").fetchone()[0])
    embeddings = np.load(folder / "embeddings.npy", allow_pickle=False) if (folder / "embeddings.npy").exists() else None
    rows = json.loads((folder / 'embedding_rows.json').read_text(encoding='utf-8'))
    if rows != [c.chunk_id for c in chunks]:
        raise ValueError("Embedding row identities do not match stored chunks; rebuild index")
    if manifest['semantic']['available'] and embeddings is None and chunks:
        raise ValueError("Semantic index vectors are missing; rebuild index")
    if embeddings is not None and (embeddings.ndim != 2 or embeddings.shape[0] != len(chunks)
                                   or not np.isfinite(embeddings).all()):
        raise ValueError("Invalid embedding shape or values; rebuild index")
    return manifest, files, symbols, chunks, edges, extra, embeddings


def load_index(folder: Path):
    try:
        return _load_index(folder)
    except (sqlite3.Error, OSError, KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("Index is missing or corrupt; reindex the repository to recover") from exc

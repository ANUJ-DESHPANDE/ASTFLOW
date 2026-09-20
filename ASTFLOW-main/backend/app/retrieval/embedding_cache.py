"""Content-addressed embedding cache shared across indexed versions.

Re-indexing a changed snapshot previously re-encoded every chunk, even chunks
whose exact indexed text (path + qualified name + imports + comments + source)
was untouched by the change. This store lets IndexService reuse a chunk's
embedding whenever the same model has already encoded byte-identical text,
so only genuinely new or modified chunks are sent through the CPU model.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np


class EmbeddingCache:
    _BATCH = 400  # keeps each IN (...) query well under SQLite's default variable limit

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS vectors (
                    model TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY (model, text_hash)
                )"""
            )
            db.commit()

    def get_many(self, model: str, hashes: list[str]) -> dict[str, np.ndarray]:
        if not hashes:
            return {}
        found: dict[str, np.ndarray] = {}
        unique = sorted(set(hashes))
        with closing(sqlite3.connect(self.path)) as db:
            for start in range(0, len(unique), self._BATCH):
                batch = unique[start:start + self._BATCH]
                placeholders = ",".join("?" * len(batch))
                rows = db.execute(
                    f"SELECT text_hash, dim, vector FROM vectors WHERE model = ? AND text_hash IN ({placeholders})",
                    [model, *batch],
                ).fetchall()
                for text_hash, dim, blob in rows:
                    found[text_hash] = np.frombuffer(blob, dtype=np.float32).reshape(dim).copy()
        return found

    def put_many(self, model: str, items: dict[str, np.ndarray]) -> None:
        if not items:
            return
        rows = [
            (model, text_hash, int(np.asarray(vector).shape[0]), np.asarray(vector, dtype=np.float32).tobytes())
            for text_hash, vector in items.items()
        ]
        with closing(sqlite3.connect(self.path)) as db:
            db.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?, ?)", rows)
            db.commit()

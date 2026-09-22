import numpy as np
from pathlib import Path
from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embedder
from backend.app.models.entities import Chunk
import json

def precompute():
    settings = Settings()
    embedder = Embedder(settings)
    embedder.load()

    # Load corpus
    corpus_path = settings.cache / "datasets" / "apps" / "corpus.jsonl"
    if not corpus_path.exists():
        print(f"Corpus not found at {corpus_path}. Please run benchmark with --download first.")
        return

    print("Loading corpus...")
    chunks = []
    with open(corpus_path, 'r', encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            text = row.get("text", "")
            chunks.append(Chunk(
                chunk_id=str(row["_id"]),
                symbol_id=str(row["_id"]),
                file_path="",
                qualified_name=row.get("title", ""),
                kind="dataset_document",
                start_line=1,
                end_line=len(text.splitlines()),
                text=text,
                search_text=text,
                content_hash=""
            ))

    print(f"Encoding {len(chunks)} documents (this will take a few minutes)...")
    # Use the same windowing strategy as the frozen config
    window_size, overlap = 256, 64
    embeddings = embedder.encode([c.text for c in chunks], use_windows=True, window_size=window_size, overlap=overlap)

    # embeddings[i] corresponds to chunks[i], i.e. to this script's own corpus.jsonl
    # iteration order. Any consumer (e.g. mteb_appretrieval.py) builds its own chunk
    # list independently and is not guaranteed to use the same order (in practice it
    # sorts by document id, which corpus.jsonl is not). Persist chunk_id alongside
    # each embedding so a consumer can realign by id instead of trusting position.
    ids = [c.chunk_id for c in chunks]

    save_path = settings.cache / "datasets" / "apps_fixed.npy"
    meta_path = settings.cache / "datasets" / "apps_fixed.meta.json"
    np.save(save_path, np.asarray(embeddings, dtype=object))
    meta_path.write_text(json.dumps({
        "ids": ids,
        "model": settings.model,
        "window_size": window_size,
        "overlap": overlap,
    }), encoding="utf-8")
    print(f"Saved embeddings to {save_path} ({len(ids)} ids in {meta_path})")

if __name__ == "__main__":
    precompute()

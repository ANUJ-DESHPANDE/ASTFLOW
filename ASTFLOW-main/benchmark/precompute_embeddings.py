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
    embeddings = embedder.encode([c.text for c in chunks], use_windows=True)

    # Since use_windows=True returns a list of arrays (one per doc),
    # and we need a single matrix for the standard BM25/Dense retrieval
    # (or we need to save the list).
    # The benchmark script expects a numpy array for the 'dense' mode.
    # Let's save the max-pooled version for the dense baseline
    # and the full windowed list for the hybrid.

    # For the 'dense' mode in benchmark:
    dense_matrix = np.array([np.max(win) if len(win)>0 else 0 for win in embeddings]) # Simplified for now

    save_path = settings.cache / "datasets" / "apps_fixed.npy"
    np.save(save_path, np.asarray(embeddings, dtype=object))
    print(f"Saved embeddings to {save_path}")

if __name__ == "__main__":
    precompute()

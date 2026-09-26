"""Lazy CPU embeddings with a truthful lexical-only fallback."""
import threading
from pathlib import Path

import numpy as np

from backend.app.config import Settings

# How each supported model expects to be called (model cards). Unlisted models are used as-is: no prefixes and
# their own sequence limit. `max_seq` bounds CPU cost; it never exceeds what the model was trained for.
PROFILES = {
    "sentence-transformers/all-MiniLM-L6-v2": {"query_prefix": "", "document_prefix": "", "max_seq": None},
    "Alibaba-NLP/gte-modernbert-base": {"query_prefix": "", "document_prefix": "", "max_seq": 512},
    "ibm-granite/granite-embedding-english-r2": {"query_prefix": "", "document_prefix": "", "max_seq": 1024},
}


def profile(model: str) -> dict:
    return PROFILES.get(model, {"query_prefix": "", "document_prefix": "", "max_seq": None})


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.attempted = False
        self.reason = "Semantic search has not loaded"
        self.lock = threading.RLock()

    def load(self, download: bool = False):
        with self.lock:
            if self.attempted and not download:
                return self.model
            self.attempted = True
            if self.settings.semantic == "off" and not download:
                self.reason = "Semantic search disabled by configuration"
                return None
            try:
                from sentence_transformers import SentenceTransformer
                import torch
                torch.set_num_threads(min(4, torch.get_num_threads()))
                model_path = self.settings.cache / "models" / self.settings.model.replace("/", "--").replace("\\", "--").replace(":", "_")
                source = str(model_path) if (model_path / "modules.json").exists() else self.settings.model
                self.model = SentenceTransformer(source, device="cpu", local_files_only=not download,
                                                 trust_remote_code=False,
                                                 cache_folder=str(self.settings.cache / "models" / "hub"))
                if download:
                    self.model.save(str(model_path))
                cap = profile(self.settings.model)["max_seq"]
                if cap:
                    self.model.max_seq_length = min(cap, self.model.max_seq_length or cap)
                self.reason = "CPU semantic model ready"
            except Exception as exc:
                self.model = None
                self.reason = f"Lexical fallback: {type(exc).__name__}; run astflow model-download to enable semantic search"
            return self.model

    def encode(self, texts: list[str], use_windows: bool = False, window_size: int = 256, overlap: int = 64,
               kind: str = "document"):
        if not self.load():
            return None
        prefix = profile(self.settings.model)["query_prefix" if kind == "query" else "document_prefix"]
        if prefix:
            texts = [prefix + t for t in texts]
        with self.lock:
            if not use_windows:
                return np.asarray(self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                                    convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)

            all_windows = []
            doc_window_counts = []
            for text in texts:
                tokens = self.model.tokenizer.tokenize(text)
                if len(tokens) <= window_size:
                    all_windows.append(text)
                    doc_window_counts.append(1)
                else:
                    stride = window_size - overlap
                    count = 0
                    for start in range(0, len(tokens), stride):
                        all_windows.append(self.model.tokenizer.convert_tokens_to_string(tokens[start : start + window_size]))
                        count += 1
                    doc_window_counts.append(count)

            embeddings = self.model.encode(all_windows, batch_size=32, normalize_embeddings=True,
                                           convert_to_numpy=True, show_progress_bar=False)

            grouped = []
            curr = 0
            for count in doc_window_counts:
                grouped.append(embeddings[curr : curr + count])
                curr += count
            return grouped


    @property
    def status(self):
        return {"available": self.model is not None, "model": self.settings.model if self.model else None, "message": self.reason}

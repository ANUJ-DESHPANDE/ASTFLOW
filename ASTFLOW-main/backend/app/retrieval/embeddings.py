"""Lazy CPU embeddings with a truthful lexical-only fallback."""
import threading
from pathlib import Path

import numpy as np

from backend.app.config import Settings


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
                self.reason = "CPU semantic model ready"
            except Exception as exc:
                self.model = None
                self.reason = f"Lexical fallback: {type(exc).__name__}; run astflow model-download to enable semantic search"
            return self.model

    def encode(self, texts: list[str]):
        if not self.load():
            return None
        with self.lock:
            return np.asarray(self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                                convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)

    @property
    def status(self):
        return {"available": self.model is not None, "model": self.settings.model if self.model else None, "message": self.reason}

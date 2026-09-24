"""Cross-encoder reranker for high-precision joint scoring of query and candidate code."""
import logging
import threading
from typing import Any, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

_instances: dict[tuple, "Reranker"] = {}
_instances_lock = threading.RLock()


def get_reranker(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", device: str = "cpu", batch_size: int = 32) -> "Reranker":
    """Singleton factory ensuring a reranker model is loaded and initialized only once."""
    key = (model_name, device, batch_size)
    with _instances_lock:
        if key not in _instances:
            _instances[key] = Reranker(model_name=model_name, device=device, batch_size=batch_size)
        return _instances[key]


class Reranker:
    """Manages cross-encoder loading, single-instance caching, and candidate reranking."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", device: str = "cpu", batch_size: int = 32, model_instance: Any = None):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.model: Any = model_instance
        self.attempted: bool = model_instance is not None
        self.available: bool = model_instance is not None
        self.reason: Optional[str] = None
        self._lock = threading.RLock()

    def load(self, force: bool = False) -> bool:
        """Attempt to load sentence_transformers.CrossEncoder once. Thread-safe."""
        with self._lock:
            if self.available and not force:
                return True
            self.attempted = True
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading CrossEncoder model {self.model_name!r} on device {self.device!r}...")
                self.model = CrossEncoder(self.model_name, device=self.device)
                self.available = True
                self.reason = None
                logger.info(f"CrossEncoder model {self.model_name!r} successfully loaded.")
                return True
            except Exception as e:
                self.available = False
                self.model = None
                self.reason = f"{type(e).__name__}: {e}"
                logger.error(f"Failed to load CrossEncoder model {self.model_name!r}: {self.reason}", exc_info=True)
                return False

    def predict(self, pairs: List[List[str]]) -> np.ndarray:
        """Jointly score [query, document_text] pairs."""
        if not pairs:
            return np.array([], dtype=np.float32)

        with self._lock:
            if not self.available:
                loaded = self.load()
                if not loaded:
                    raise RuntimeError(f"Cross-encoder reranker unavailable: {self.reason}")

            try:
                scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
                return np.asarray(scores, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error during cross-encoder prediction: {e}", exc_info=True)
                raise RuntimeError(f"Reranker prediction failed: {type(e).__name__}: {e}") from e

    def rerank(self, query: str, rows: List[dict], depth: int = 100) -> List[dict]:
        """Reranks the top-depth candidates using joint cross-encoder scoring.
        
        The top `depth` candidates are jointly scored with query and reordered.
        Ties in reranker scores are broken deterministically by chunk_id ascending.
        Remaining candidates (beyond depth) remain in their original order.
        """
        if not rows or depth <= 0:
            return rows

        top_n = min(depth, len(rows))
        candidates_to_rerank = rows[:top_n]
        remaining = rows[top_n:]

        # Joint pairs: only query and candidate document text
        pairs = [[query, r["chunk"].search_text] for r in candidates_to_rerank]
        scores = self.predict(pairs)

        # Update candidate scores and evidence
        for idx, (r, score) in enumerate(zip(candidates_to_rerank, scores)):
            r["evidence"]["original_hybrid_score"] = r["score"]
            r["evidence"]["reranker_score"] = float(score)
            r["score"] = float(score)

        # Sort top candidates strictly by (-score, chunk_id)
        candidates_to_rerank.sort(key=lambda r: (-r["score"], r["chunk"].chunk_id))

        for rank, r in enumerate(candidates_to_rerank, 1):
            r["evidence"]["reranker_rank"] = rank

        return candidates_to_rerank + remaining

"""All ranking weights and resource bounds live here."""
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The frozen submission configuration (benchmark/experiments/EXPERIMENTS.md, "RETRIEVAL FREEZE"): official MTEB
# AppsRetrieval NDCG@10 0.5511 with this model, ranking by dense cosine similarity only (no BM25 fusion).
FROZEN_MODEL = "Alibaba-NLP/gte-modernbert-base"
FROZEN_RETRIEVAL = "dense"


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("ASTFLOW_MODEL", FROZEN_MODEL)
    # "on": the embedding model is required and indexing fails with an actionable error if it cannot load (no
    # silent lexical fallback). "off": explicit lexical-only mode (tests, low-resource machines), reported as such.
    semantic: str = os.getenv("ASTFLOW_SEMANTIC", "on")
    # First-stage ranking for repository search: "dense" (frozen), "hybrid" (BM25 + dense RRF) or "bm25".
    retrieval: str = os.getenv("ASTFLOW_RETRIEVAL", FROZEN_RETRIEVAL)
    cache: Path = Path(os.getenv("ASTFLOW_CACHE", str(ROOT / ".astflow"))).resolve()
    ts_enrich: bool = os.getenv("ASTFLOW_TS_ENRICH", "true").lower() == "true"
    rrf_k: int = 60
    lexical_weight: float = 1.0
    semantic_weight: float = 1.0
    exact_boost: float = 0.018
    name_boost: float = 0.004
    graph_boost: float = 0.006
    graph_decay: float = 0.45
    refinement_weight: float = 0.12
    test_weight: float = 0.82
    candidates: int = 500
    max_depth: int = 5
    max_file_bytes: int = 1_000_000
    max_files: int = 20_000
    max_total_bytes: int = 50_000_000
    schema: int = 8

    def __post_init__(self):
        if self.semantic not in {"on", "auto", "off"}:
            raise ValueError(f"ASTFLOW_SEMANTIC must be 'on' or 'off', not {self.semantic!r}")
        if self.retrieval not in {"dense", "hybrid", "bm25"}:
            raise ValueError(f"ASTFLOW_RETRIEVAL must be 'dense', 'hybrid' or 'bm25', not {self.retrieval!r}")

    @property
    def frozen(self) -> bool:
        """True when this is the configuration whose official benchmark result is reported."""
        return self.model == FROZEN_MODEL and self.retrieval == FROZEN_RETRIEVAL and self.semantic != "off"

    def fingerprint(self) -> str:
        values = asdict(self)
        values.pop("cache")
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]

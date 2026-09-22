"""All ranking weights and resource bounds live here."""
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("ASTFLOW_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    semantic: str = os.getenv("ASTFLOW_SEMANTIC", "auto")
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

    def fingerprint(self) -> str:
        values = asdict(self)
        values.pop("cache")
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Symbol:
    symbol_id: str
    qualified_name: str
    name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    parent_symbol_id: str | None
    source_text: str
    content_hash: str
    parameters: list[str] = field(default_factory=list)
    is_test: bool = False
    method_kind: str = "normal"


@dataclass
class Chunk:
    chunk_id: str
    symbol_id: str
    file_path: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    text: str
    search_text: str
    content_hash: str
    version_key: str = ""
    is_test: bool = False


@dataclass
class Edge:
    source_symbol_id: str
    target_symbol_id: str
    edge_type: str
    call_file: str
    call_line: int
    call_end_line: int
    call_start_byte: int
    call_end_byte: int
    source_expression: str
    resolution_method: str
    evidence_type: str = "STATIC_VERIFIED"
    evidence_sources: list[str] = field(default_factory=lambda: ["TREE_SITTER_STATIC"])
    supporting_spans: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "source": self.source_symbol_id, "target": self.target_symbol_id}


@dataclass
class ParsedFile:
    path: str
    source: str
    symbols: list[Symbol] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    imports: dict[str, dict] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)
    bindings: dict[str, dict[str, str]] = field(default_factory=dict)
    shadowed: dict[str, set[str]] = field(default_factory=dict)
    reassigned: dict[str, set[str]] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    binding_spans: dict[str, dict[str, dict]] = field(default_factory=dict)
    has_errors: bool = False

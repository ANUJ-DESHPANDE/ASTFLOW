from pydantic import BaseModel, Field, field_validator


class IndexRequest(BaseModel):
    repo_path: str = Field(min_length=1, max_length=4096)
    version: str = Field(default="working-tree", min_length=1, max_length=200)
    background: bool = True


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    version: str = Field(default="working-tree", min_length=1, max_length=200)
    top_k: int = Field(default=10, ge=1, le=50)
    agentic: bool = True
    runtime_trace_id: str | None = None

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Query cannot be blank")
        return value.strip()


class TraceRequest(BaseModel):
    source_symbol_id: str = Field(min_length=1, max_length=1000)
    target_symbol_id: str = Field(min_length=1, max_length=1000)
    version: str = "working-tree"
    max_depth: int = Field(default=5, ge=1, le=8)


class CompareRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    version_a: str = Field(min_length=1, max_length=200)
    version_b: str = Field(min_length=1, max_length=200)

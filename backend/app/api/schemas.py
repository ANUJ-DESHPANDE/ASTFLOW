from pydantic import BaseModel, ConfigDict, Field, field_validator


# Longest CoIR Apps (AppsRetrieval) query is ~2,570 word-pieces (~11k characters); hands-on queries are "similar to
# the dataset", so the limit leaves room for full competitive-programming problem statements.
MAX_QUERY_CHARS = 32_000


class RequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class IndexRequest(RequestModel):
    repo_path: str = Field(min_length=1, max_length=4096)
    version: str = Field(default="working-tree", min_length=1, max_length=200)
    background: bool = True


class SearchRequest(RequestModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
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


class TraceRequest(RequestModel):
    source_symbol_id: str = Field(min_length=1, max_length=1000)
    target_symbol_id: str = Field(min_length=1, max_length=1000)
    version: str = Field(default="working-tree", min_length=1, max_length=200)
    max_depth: int = Field(default=5, ge=1, le=8)


class CompareRequest(RequestModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    version_a: str = Field(min_length=1, max_length=200)
    version_b: str = Field(min_length=1, max_length=200)

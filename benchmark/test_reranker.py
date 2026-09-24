"""Unit and integration tests for the CrossEncoder Reranker using mocks and deterministic data."""
import numpy as np
import pytest
from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.reranker import Reranker, get_reranker
from backend.app.retrieval.search import Retriever


class MockCrossEncoderModel:
    """Mock cross-encoder that computes deterministic scores without Hugging Face."""
    def __init__(self, score_map=None, call_recorder=None):
        self.score_map = score_map or {}
        self.call_recorder = call_recorder if call_recorder is not None else []
        self.init_count = 1

    def predict(self, pairs, batch_size=32, show_progress_bar=False):
        self.call_recorder.append(pairs)
        scores = []
        for query, doc_text in pairs:
            # If explicit score mapped for (query, doc_text) or doc_text:
            score = self.score_map.get((query, doc_text), self.score_map.get(doc_text, 0.5))
            scores.append(score)
        return np.array(scores, dtype=np.float32)


def make_chunk(chunk_id: str, text: str, name: str = "") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        file_path=f"path/{chunk_id}.py",
        symbol_id=f"sym_{chunk_id}",
        qualified_name=name or f"mod.{chunk_id}",
        kind="function",
        start_line=1,
        end_line=10,
        text=text,
        search_text=text,
        content_hash=f"hash_{chunk_id}",
        is_test=False,
    )


def test_candidates_passed_to_reranker_and_scores_mapped():
    """1 & 2: Candidates are passed to reranker as [query, text] and scores mapped correctly."""
    recorded_pairs = []
    score_map = {"text A": 0.2, "text B": 0.9, "text C": 0.5}
    mock_model = MockCrossEncoderModel(score_map=score_map, call_recorder=recorded_pairs)
    reranker = Reranker(model_name="mock", model_instance=mock_model)

    c_a = make_chunk("c_a", "text A")
    c_b = make_chunk("c_b", "text B")
    c_c = make_chunk("c_c", "text C")

    rows = [
        {"chunk": c_a, "score": 0.8, "evidence": {}},
        {"chunk": c_b, "score": 0.7, "evidence": {}},
        {"chunk": c_c, "score": 0.6, "evidence": {}},
    ]

    reranked = reranker.rerank("search query", rows, depth=3)

    # 1. Verify pairs passed
    assert len(recorded_pairs) == 1
    assert recorded_pairs[0] == [
        ["search query", "text A"],
        ["search query", "text B"],
        ["search query", "text C"],
    ]

    # 2. Verify descending scores and reordered ranking: B (0.9), C (0.5), A (0.2)
    assert [r["chunk"].chunk_id for r in reranked] == ["c_b", "c_c", "c_a"]
    assert reranked[0]["score"] == pytest.approx(0.9)
    assert reranked[1]["score"] == pytest.approx(0.5)
    assert reranked[2]["score"] == pytest.approx(0.2)

    # Verify evidence preserved
    assert reranked[0]["evidence"]["reranker_rank"] == 1
    assert reranked[0]["evidence"]["original_hybrid_score"] == 0.7
    assert reranked[0]["evidence"]["reranker_score"] == pytest.approx(0.9)


def test_descending_scores_and_deterministic_ties():
    """3 & 4: Descending scores produce descending rankings; tied scores broken by chunk_id ascending."""
    # Chunk D and Chunk B both score 0.8; Chunk A scores 0.9; Chunk C scores 0.1
    score_map = {"text A": 0.9, "text B": 0.8, "text D": 0.8, "text C": 0.1}
    mock_model = MockCrossEncoderModel(score_map=score_map)
    reranker = Reranker(model_name="mock", model_instance=mock_model)

    c_a = make_chunk("c_a", "text A")
    c_b = make_chunk("c_b", "text B")
    c_c = make_chunk("c_c", "text C")
    c_d = make_chunk("c_d", "text D")

    # Initial order: D before B
    rows = [
        {"chunk": c_d, "score": 0.5, "evidence": {}},
        {"chunk": c_b, "score": 0.4, "evidence": {}},
        {"chunk": c_c, "score": 0.3, "evidence": {}},
        {"chunk": c_a, "score": 0.2, "evidence": {}},
    ]

    reranked = reranker.rerank("query", rows, depth=4)

    # Expected: c_a (0.9), then tie between c_b and c_d -> c_b before c_d (chunk_id ascending), then c_c (0.1)
    ordered_ids = [r["chunk"].chunk_id for r in reranked]
    assert ordered_ids == ["c_a", "c_b", "c_d", "c_c"]


def test_top_k_candidate_limits_respected():
    """5: Candidate depth limits (e.g. top 2, top 20, top 50, top 100) are strictly respected."""
    recorded_pairs = []
    # Make candidate 5 score highest if reranked
    score_map = {f"text {i}": float(i) for i in range(10)}
    mock_model = MockCrossEncoderModel(score_map=score_map, call_recorder=recorded_pairs)
    reranker = Reranker(model_name="mock", model_instance=mock_model)

    rows = [{"chunk": make_chunk(f"c_{i}", f"text {i}"), "score": 1.0 / (i + 1), "evidence": {}} for i in range(10)]

    # Rerank with depth=3: only first 3 candidates (c_0, c_1, c_2) should be sent to reranker
    reranked = reranker.rerank("query", rows, depth=3)

    assert len(recorded_pairs[0]) == 3
    # Top 3 should be reordered among themselves: c_2 (score 2.0), c_1 (1.0), c_0 (0.0)
    assert [r["chunk"].chunk_id for r in reranked[:3]] == ["c_2", "c_1", "c_0"]
    # Remaining candidates 3..9 should remain untouched in their original positions and order
    assert [r["chunk"].chunk_id for r in reranked[3:]] == [f"c_{i}" for i in range(3, 10)]


def test_reranker_failures_are_visible():
    """6: Reranker failure (e.g. model cannot load or prediction throws) is visible, not silently swallowed."""
    class FailingModel:
        def predict(self, pairs, **kwargs):
            raise ValueError("GPU out of memory or corrupted tensor")

    failing_reranker = Reranker(model_name="failing_model", model_instance=FailingModel())
    rows = [{"chunk": make_chunk("c1", "text 1"), "score": 0.5, "evidence": {}}]

    with pytest.raises(RuntimeError, match="Reranker prediction failed.*ValueError"):
        failing_reranker.rerank("query", rows, depth=1)


def test_model_is_initialized_once_via_singleton():
    """7: The model is initialized only once via get_reranker singleton factory."""
    r1 = get_reranker(model_name="test-singleton-model", device="cpu", batch_size=16)
    r2 = get_reranker(model_name="test-singleton-model", device="cpu", batch_size=16)
    assert r1 is r2


def test_original_hybrid_ranking_preserved_when_reranking_disabled():
    """8: When reranking is disabled, exact Hybrid ranking is preserved untouched."""
    chunks = [make_chunk("c1", "banana apple"), make_chunk("c2", "banana orange")]
    settings = Settings(reranker_enabled=False, semantic="off")
    retriever = Retriever(chunks=chunks, embeddings=None, embedder=None, settings=settings)

    # In hybrid mode with reranker_enabled=False
    results, meta = retriever.rank("apple", mode="hybrid")
    assert [r["chunk"].chunk_id for r in results] == ["c1"]

    # In reranked mode with mock reranker attached
    mock_model = MockCrossEncoderModel(score_map={"banana apple": 0.1, "banana orange": 0.9})
    reranker = Reranker(model_name="mock", model_instance=mock_model)
    retriever.reranker = reranker

    # When mode='reranked' is explicitly called on query matching both candidates
    reranked_results, _ = retriever.rank("banana", mode="reranked")
    # c2 scored 0.9, c1 scored 0.1 -> c2 first
    assert [r["chunk"].chunk_id for r in reranked_results] == ["c2", "c1"]


def test_no_benchmark_labels_leaked():
    """No qrels, grades, or ground-truth answer IDs are passed to reranker."""
    call_pairs = []
    mock_model = MockCrossEncoderModel(call_recorder=call_pairs)
    reranker = Reranker(model_name="mock", model_instance=mock_model)

    chunk = make_chunk("doc_123", "def calculate_sum(a, b): return a + b")
    rows = [{"chunk": chunk, "score": 0.5, "evidence": {}}]

    reranker.rerank("how to sum two numbers", rows, depth=1)

    assert len(call_pairs) == 1
    query, doc_text = call_pairs[0][0]
    # Check that neither qrels nor relevance information is present
    assert query == "how to sum two numbers"
    assert doc_text == "def calculate_sum(a, b): return a + b"
    assert "doc_123" not in doc_text

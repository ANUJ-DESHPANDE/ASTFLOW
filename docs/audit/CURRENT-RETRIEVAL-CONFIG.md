# Frozen Retrieval Configuration (Subset NDCG@10 = 0.1184)

This document records the exact configuration used to achieve NDCG@10 = 0.1184 on the 100-query AppsRetrieval subset. This configuration is FROZEN for full-scale verification.

## Lexical Retrieval (BM25F)
- **Method**: BM25F (Field-aware simulated via weighted sum)
- **k1**: 1.6
- **b**: 0.75
- **Stopwords**: Custom set (defined in `search.py`)
- **Tokenizer**: Custom regex-based tokenizer with camelCase/snake_case splitting.
- **Field Weights**:
    - `qualified_name` (Title): 2.0
    - `search_text` (Body): 1.0
- **Candidate Depth**: 500

## Dense Retrieval
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Normalization**: L2 (normalized_embeddings=True)
- **Max Sequence Length**: 256 tokens
- **Long-Document Strategy**: Sliding Window (window_size=256, overlap=64) with Max-Pooling (maximum similarity across windows).
- **Similarity Metric**: Dot Product (on normalized vectors)
- **Similarity Threshold**: 0.05
- **Candidate Depth**: 500

## Fusion
- **Method**: Reciprocal Rank Fusion (RRF)
- **RRF k**: 60
- **Weighting**:
    - Lexical Weight: 1.0
    - Semantic Weight: 1.0
- **Tie Handling**: Stable sort by `chunk_id`.

## Heuristics
- **exact_symbol**: Active (Boost: 0.018)
- **symbol_tokens**: Active (Boost: 0.004 * overlap)
- **test_weight**: Active (Weight: 0.82 if chunk is test and query does not mention test/spec)

## Reranker
- **Enabled**: Yes
- **Model**: `mxbai-rerank-base-v2`
- **Candidate Count**: Top 100 candidates from hybrid stage.
- **Score Combination**: Reranker score replaces Hybrid score for top 100.
- **Final Ranking**: Sorted by reranker score, then `chunk_id`.

## Benchmark Environment
- **Dataset**: CoIR-Retrieval/apps
- **Queries (Subset)**: 100
- **Corpus Size**: 8,765
- **Hardware**: CPU
- **Key Packages**: `sentence-transformers`, `rank_bm25`, `scipy`, `numpy`

# Open-Source Retrieval Study: ASTFLOW Improvements

This document analyzes open-source code retrieval techniques and maps them to the ASTFLOW implementation to improve the AppsRetrieval benchmark scores.

## 1. Technique Matrix

| Technique | Source Project | ASTFLOW Has It? | Difference | Expected Benefit | Cost | Experiment? |
|---|---|---|---|---|---|---|
| **BM25F** | rag-your-code | No | ASTFLOW uses single-field BM25. | Higher signal for titles/signatures. | Low | Yes |
| **Field Boosts** | BM25F | Partial | Current boosts are post-RRF heuristics. | Better candidate generation. | Low | Yes |
| **AST Chunks** | codesearch | Yes | ASTFLOW has a similar AST-based parser. | Better granularity. | Low | No (Baseline) |
| **Dense Retrieval**| Code-Search | Yes | Current uses MiniLM. | Semantic matching. | Low | No (Baseline) |
| **RRF** | codesearch | Yes | Standard RRF implementation. | Robust fusion. | Low | No (Baseline) |
| **Sliding Window** | Research (RepoEval)| No | Current truncates at 256 tokens. | Fixes 23.5% truncation loss. | Medium | Yes |
| **Cross-Encoder** | mxbai-rerank | No | No reranking stage currently. | Massive boost to NDCG/MRR. | High (CPU) | Yes |
| **Late Chunking** | Research (alphaXiv)| No | Naive chunk-then-embed. | Better small-chunk context. | Medium | No |

## 2. Classification of Techniques

- **ALREADY IMPLEMENTED**: AST Chunks, Dense Retrieval, RRF.
- **IMPLEMENTED DIFFERENTLY**: Field Boosts (currently post-fusion heuristics; should be moved to BM25F).
- **MISSING AND HIGH VALUE**: Cross-Encoder Reranking, Sliding Window Embeddings.
- **MISSING BUT LOW VALUE**: Late Chunking (too complex for current gain).
- **EXPERIMENTAL**: BM25F (Field-aware lexical retrieval).

## 3. AppsRetrieval Specific Mapping

The AppsRetrieval dataset contains only `title` and `text`. To avoid "manufacturing" fields, the implementation will map as follows:

- **Product Search (JS Repo)**: Full BM25F (`name`, `signature`, `description`, `relations`, `body`).
- **Benchmark Path**: Two-field BM25F (`title` $\to$ high weight, `text` $\to$ low weight).

## 4. Justification for Implementation Order

1. **Candidate Pool expansion**: Increase candidate depth $\to$ Sliding Windows $\to$ BM25F. (Ensure the "Correct" document is in the top 500).
2. **Ranking optimization**: Cross-Encoder Reranking. (Ensure the "Correct" document is in the top 10).

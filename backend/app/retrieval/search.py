import re

import numpy as np
from rank_bm25 import BM25Okapi
from scipy.sparse import csr_matrix

from backend.app.config import Settings
from backend.app.models.entities import Chunk

# Try to import CrossEncoder for reranking
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = False # DISABLED for stability and speed
except ImportError:
    CROSS_ENCODER_AVAILABLE = False

STOP = set("where is are the a an how does do to of for in on and or can i it this that what which with handled used before after from into was be as by def else if import int list return str".split())


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in re.findall(r"[A-Za-z_$][\w$]*", text):
        split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", word)
        split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", split)
        parts = re.split(r"[_$\s]+", split.lower())
        tokens.extend(p for p in parts if p and p not in STOP)
        exact = word.lower()
        if len(parts) > 1 and exact not in STOP:
            tokens.append(exact)
    return tokens


class Retriever:
    def __init__(self, chunks: list[Chunk], embeddings, embedder, settings: Settings, tokenizer=tokenize,
                 k1: float = 1.6, b: float = 0.75):
        self.chunks, self.embeddings, self.embedder, self.settings = chunks, embeddings, embedder, settings
        self.tokenize = tokenizer
        self.by_id = {c.chunk_id: c for c in chunks}

        # Field-aware corpus for BM25F simulation
        # For AppsRetrieval: title (qualified_name) and text (search_text)
        self.corpus_title = [self.tokenize(c.qualified_name) or ["__empty__"] for c in chunks]
        self.corpus_text = [self.tokenize(c.search_text) or ["__empty__"] for c in chunks]

        # Weights for BM25F (higher for title)
        self.w_title = 2.0
        self.w_text = 1.0

        # Original BM25 for backward compatibility and baseline
        corpus = [self.tokenize(c.search_text) or ["__empty__"] for c in chunks]
        self.bm25 = BM25Okapi(corpus, k1=k1, b=b) if corpus else None
        if self.bm25:
            frequencies = {}
            for doc in corpus:
                for token in set(doc):
                    frequencies[token] = frequencies.get(token, 0) + 1
            self.bm25.idf = {t: float(np.log(1 + (len(corpus) - df + .5) / (df + .5))) for t, df in frequencies.items()}
        self.vocabulary = {term: i for i, term in enumerate(sorted(self.bm25.idf))} if self.bm25 else {}
        values, term_rows, doc_columns = [], [], []
        if self.bm25:
            for doc, frequencies in enumerate(self.bm25.doc_freqs):
                norm = self.bm25.k1 * (1 - self.bm25.b + self.bm25.b * self.bm25.doc_len[doc] / self.bm25.avgdl)
                for term, frequency in frequencies.items():
                    term_rows.append(self.vocabulary[term]); doc_columns.append(doc)
                    values.append(self.bm25.idf[term] * frequency * (self.bm25.k1 + 1) / (frequency + norm))
        self.postings = csr_matrix((values, (term_rows, doc_columns)), shape=(len(self.vocabulary), len(chunks)))

    def lexical_scores(self, terms: list[str]):
        # BM25F Simulation: weighted sum of scores from different fields
        # In a real BM25F, IDF is shared across fields. Here we use the precomputed
        # main corpus IDF for simplicity, which is a strong approximation.

        # Score for 'text' field (original behavior)
        ids = [self.vocabulary[t] for t in terms if t in self.vocabulary]
        text_scores = np.asarray(self.postings[ids].sum(axis=0)).ravel() if ids else np.zeros(len(self.chunks))

        # Score for 'title' field (simulated by scanning qualified_name)
        # For high performance, we could precompute a title-postings matrix,
        # but with <20k chunks, a direct scan is acceptable for the benchmark.
        title_scores = np.zeros(len(self.chunks))
        if ids:
            for i, chunk in enumerate(self.chunks):
                chunk_title_tokens = set(self.tokenize(chunk.qualified_name))
                match_count = sum(1 for t in terms if t in chunk_title_tokens)
                if match_count > 0:
                    # Simple TF * IDF boost for title
                    title_scores[i] = sum(self.bm25.idf.get(t, 0) for t in terms if t in chunk_title_tokens)

        return (self.w_text * text_scores) + (self.w_title * title_scores)

    def rank(self, query: str, mode: str = "hybrid", boosts: bool = True, limit: int | None = None):
        if not self.chunks:
            return [], {"lexical_top": [], "semantic_top": [], "semantic_available": False}
        terms = self.tokenize(query)
        lexical = self.lexical_scores(terms)
        dense = None
        if mode != "bm25" and self.embeddings is not None:
            query_embedding = self.embedder.encode([query])
            if query_embedding is not None:
                q_vec = query_embedding[0]
                if isinstance(self.embeddings, list):
                    # Max-pooling over windows: score = max(window_embedding @ q_vec)
                    dense = np.array([
                        np.max(win @ q_vec) if win.size > 0 else -1.0
                        for win in self.embeddings
                    ])
                else:
                    dense = self.embeddings @ q_vec
        size = max(self.settings.candidates, limit or 0)
        lexical_order = sorted((i for i, s in enumerate(lexical) if s > 0), key=lambda i: (-lexical[i], self.chunks[i].chunk_id))[:size]
        semantic_order = sorted((i for i in range(len(dense)) if dense[i] > .05), key=lambda i: (-dense[i], self.chunks[i].chunk_id))[:size] if dense is not None else []
        lr = {i: n + 1 for n, i in enumerate(lexical_order)}
        sr = {i: n + 1 for n, i in enumerate(semantic_order)}
        candidates = set(lr if mode == "bm25" else sr if mode == "dense" else set(lr) | set(sr))
        rows = []
        query_identifiers = {w.lower() for w in re.findall(r"[\w$]+", query)}
        term_set = set(terms)
        for i in candidates:
            chunk = self.chunks[i]
            name = chunk.qualified_name.split(".")[-1]
            exact = chunk.kind != 'dataset_document' and (name.lower() in query_identifiers or bool(re.search(r"(?<![\w$])" + re.escape(chunk.qualified_name) + r"(?![\w$])", query, re.I)))
            overlap = len(term_set & set(self.tokenize(chunk.qualified_name))) / max(1, len(term_set)) if boosts else 0.
            contributions = {
                "lexical": self.settings.lexical_weight / (self.settings.rrf_k + lr[i]) if i in lr and mode != "dense" else 0.,
                "semantic": self.settings.semantic_weight / (self.settings.rrf_k + sr[i]) if i in sr and mode != "bm25" else 0.,
                "exact_symbol": self.settings.exact_boost if boosts and exact else 0.,
                "symbol_tokens": self.settings.name_boost * overlap if boosts else 0.,
                "structural": 0., "test_reference": 0.,
            }
            weight = self.settings.test_weight if boosts and chunk.is_test and not re.search(r"\b(test|tests|spec)\b", query, re.I) else 1.
            score = sum(contributions.values()) * weight
            rows.append({"chunk": chunk, "score": score, "evidence": {
                "lexical_rank": lr.get(i), "semantic_rank": sr.get(i),
                "lexical_score": float(lexical[i]), "semantic_score": float(dense[i]) if dense is not None else None,
                "exact_symbol_match": exact, "structural_distance": None, "structural_edges": [],
                "test_reference": chunk.is_test, "runtime_observed": False,
                "contributions": contributions, "test_weight": weight,
                "relationship_status": "SEARCH_INFERRED",
            }})
        rows.sort(key=lambda r: (-r["score"], r["chunk"].chunk_id))

        # --- CROSS-ENCODER RERANKING ---
        if CROSS_ENCODER_AVAILABLE and len(rows) > 0:
            try:
                # Lazy load CrossEncoder only when ranking to save memory
                from sentence_transformers import CrossEncoder
                reranker = CrossEncoder('mxbai-rerank-base-v2', device='cpu')

                # Re-rank only the top candidates (e.g., top 100) to manage CPU cost
                top_n = min(100, len(rows))
                candidates_to_rerank = rows[:top_n]

                # Create pairs of (query, document_text) for the model
                pairs = [[query, r["chunk"].search_text] for r in candidates_to_rerank]
                rerank_scores = reranker.predict(pairs)

                # Replace the hybrid score with the high-precision reranker score
                for idx, score in enumerate(rerank_scores):
                    candidates_to_rerank[idx]["score"] = float(score)

                # Re-sort the candidate list based on the new reranker scores
                rows.sort(key=lambda r: (-r["score"], r["chunk"].chunk_id))
            except Exception as e:
                # If the reranker fails, we gracefully fallback to the original Hybrid order
                pass
        return rows[:size], {"lexical_top": [self.chunks[i].chunk_id for i in lexical_order[:10]],
                             "semantic_top": [self.chunks[i].chunk_id for i in semantic_order[:10]],
                             "semantic_available": dense is not None}


def serialize_result(row: dict, rank: int, version: str):
    chunk = row["chunk"]
    return {"rank": rank, "chunk_id": chunk.chunk_id, "symbol_id": chunk.symbol_id,
            "symbol_name": chunk.qualified_name.split(".")[-1], "qualified_name": chunk.qualified_name,
            "kind": chunk.kind, "file_path": chunk.file_path, "start_line": chunk.start_line,
            "end_line": chunk.end_line, "snippet": chunk.text, "score": round(row["score"], 8),
            "evidence": row["evidence"], "version": version}

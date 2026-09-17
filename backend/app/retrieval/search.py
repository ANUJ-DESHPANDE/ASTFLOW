import re

import numpy as np
from rank_bm25 import BM25Okapi

from backend.app.config import Settings
from backend.app.models.entities import Chunk

STOP = set("where is are the a an how does do to of for in on and or can i it this that what which with handled used before after from into was be as by".split())


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
    def __init__(self, chunks: list[Chunk], embeddings, embedder, settings: Settings):
        self.chunks, self.embeddings, self.embedder, self.settings = chunks, embeddings, embedder, settings
        self.by_id = {c.chunk_id: c for c in chunks}
        corpus = [tokenize(c.search_text) or ["__empty__"] for c in chunks]
        self.bm25 = BM25Okapi(corpus) if corpus else None
        # Standard BM25Okapi has non-positive IDF on tiny corpora. A positive BM25
        # IDF variant preserves meaningful lexical matching in single-file repos.
        if self.bm25:
            frequencies = {}
            for doc in corpus:
                for token in set(doc):
                    frequencies[token] = frequencies.get(token, 0) + 1
            self.bm25.idf = {t: float(np.log(1 + (len(corpus) - df + .5) / (df + .5))) for t, df in frequencies.items()}

    def rank(self, query: str, mode: str = "hybrid", boosts: bool = True, limit: int | None = None):
        if not self.chunks:
            return [], {"lexical_top": [], "semantic_top": [], "semantic_available": False}
        terms = tokenize(query)
        lexical = np.asarray(self.bm25.get_scores(terms))
        dense = None
        if mode != "bm25" and self.embeddings is not None:
            query_embedding = self.embedder.encode([query])
            if query_embedding is not None:
                dense = self.embeddings @ query_embedding[0]
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
            exact = name.lower() in query_identifiers or bool(re.search(r"(?<![\w$])" + re.escape(chunk.qualified_name) + r"(?![\w$])", query, re.I))
            overlap = len(term_set & set(tokenize(chunk.qualified_name))) / max(1, len(term_set))
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

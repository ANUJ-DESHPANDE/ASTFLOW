import argparse
import statistics
from pathlib import Path
import numpy as np
from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever
from benchmark.metrics import metrics
from benchmark.mteb_appretrieval import load_export
import hashlib
import re

def run_ablation(retriever, queries, relevance, mode="hybrid", 
                 dense_threshold=0.05, 
                 candidates_limit=100, 
                 boosts_config={"exact": True, "symbol": True, "test": True}):
    
    results = []
    for qid, query_text in queries.items():
        terms = retriever.tokenize(query_text)
        lexical = retriever.lexical_scores(terms)
        dense = None
        if mode != "bm25" and retriever.embeddings is not None:
            query_embedding = retriever.embedder.encode([query_text])
            if query_embedding is not None:
                dense = retriever.embeddings @ query_embedding[0]
        
        size = candidates_limit
        lexical_order = sorted((i for i, s in enumerate(lexical) if s > 0), key=lambda i: (-lexical[i], retriever.chunks[i].chunk_id))[:size]
        
        semantic_order = []
        if dense is not None:
            semantic_order = sorted((i for i in range(len(dense)) if dense[i] > dense_threshold), key=lambda i: (-dense[i], retriever.chunks[i].chunk_id))[:size]
            
        lr = {i: n + 1 for n, i in enumerate(lexical_order)}
        sr = {i: n + 1 for n, i in enumerate(semantic_order)}
        
        candidates_set = set(lr if mode == "bm25" else sr if mode == "dense" else set(lr) | set(sr))
        
        rows = []
        query_identifiers = {w.lower() for w in re.findall(r"[\w$]+", query_text)}
        term_set = set(terms)
        for i in candidates_set:
            chunk = retriever.chunks[i]
            name = chunk.qualified_name.split(".")[-1]
            
            exact = False
            if boosts_config["exact"] and chunk.kind != 'dataset_document':
                exact = (name.lower() in query_identifiers or bool(re.search(r"(?<![\w$])" + re.escape(chunk.qualified_name) + r"(?![\w$])", query_text, re.I)))
            
            overlap = len(term_set & set(retriever.tokenize(chunk.qualified_name))) / max(1, len(term_set)) if boosts_config["symbol"] else 0.
            
            contributions = {
                "lexical": retriever.settings.lexical_weight / (retriever.settings.rrf_k + lr[i]) if i in lr and mode != "dense" else 0.,
                "semantic": retriever.settings.semantic_weight / (retriever.settings.rrf_k + sr[i]) if i in sr and mode != "bm25" else 0.,
                "exact_symbol": retriever.settings.exact_boost if exact else 0.,
                "symbol_tokens": retriever.settings.name_boost * overlap if boosts_config["symbol"] else 0.,
            }
            
            weight = retriever.settings.test_weight if boosts_config["test"] and chunk.is_test and not re.search(r"\b(test|tests|spec)\b", query_text, re.I) else 1.
            score = sum(contributions.values()) * weight
            rows.append({"chunk": chunk, "score": score})
            
        rows.sort(key=lambda r: (-r["score"], r["chunk"].chunk_id))
        ranking = [r["chunk"].chunk_id for r in rows]
        
        rel_docs = set(relevance.get(qid, {}).keys())
        actual_candidates = {retriever.chunks[i].chunk_id for i in candidates_set}
        candidate_recall = len(rel_docs & actual_candidates) / len(rel_docs) if rel_docs else 1.0
        
        results.append({
            "metrics": metrics(ranking, relevance.get(qid, {})),
            "candidate_recall": candidate_recall
        })

    if not results: return {}, 0.0
    avg_metrics = {key: statistics.mean(r["metrics"][key] for r in results) for key in ("ndcg@10", "mrr", "recall@10")}
    avg_recall = statistics.mean(r["candidate_recall"] for r in results)
    return avg_metrics, avg_recall

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / ".astflow/datasets/apps")
    parser.add_argument("--split", default="test")
    parser.add_argument("--max-queries", type=int, default=100)
    args = parser.parse_args()
    
    corpus, queries, relevance = load_export(args.data, args.split)
    settings = Settings()
    embedder = Embedder(settings)
    embedder.load()
    
    chunks = [Chunk(did, did, "", did, "dataset_document", 1, len(text.splitlines()), text, text,
                hashlib.sha256(text.encode()).hexdigest()) for did, text in sorted(corpus.items())]
    
    embeddings = embedder.encode([c.text for c in chunks])
    retriever = Retriever(chunks, embeddings, embedder, settings)
    
    # FIX: Iterate over relevance.keys() to ensure ground truth exists
    eval_query_ids = sorted(relevance.keys())[:args.max_queries]
    subset_queries = {qid: queries[qid] for qid in eval_query_ids}
    subset_relevance = {qid: relevance[qid] for qid in eval_query_ids}

    print(f"Starting Foundation Audit on {len(eval_query_ids)} queries...")

    # --- Audit 1: Dense Threshold ---
    print("\n--- Audit 1: Dense Threshold Ablation ---")
    for threshold in [0.0, 0.01, 0.05, 0.1]:
        m, r = run_ablation(retriever, subset_queries, subset_relevance, dense_threshold=threshold)
        print(f"Threshold {threshold:.2f}: NDCG@10={m.get('ndcg@10',0):.4f}, Recall@10={m.get('recall@10',0):.4f}, CandidateRecall={r:.4f}")
        
    # --- Audit 2: Candidate Depth ---
    print("\n--- Audit 2: RRF Candidate Depth Analysis ---")
    for depth in [10, 50, 100, 500]:
        m, r = run_ablation(retriever, subset_queries, subset_relevance, candidates_limit=depth)
        print(f"Depth {depth}: NDCG@10={m.get('ndcg@10',0):.4f}, Recall@10={m.get('recall@10',0):.4f}, CandidateRecall={r:.4f}")
        
    # --- Audit 3: Heuristic Ablation ---
    print("\n--- Audit 3: Heuristic Ablation ---")
    configs = [
        ("Plain RRF", {"exact": False, "symbol": False, "test": False}),
        (" + Exact", {"exact": True, "symbol": False, "test": False}),
        (" + Symbol", {"exact": False, "symbol": True, "test": False}),
        (" + Test", {"exact": False, "symbol": False, "test": True}),
        ("Full Hybrid", {"exact": True, "symbol": True, "test": True}),
    ]
    for label, cfg in configs:
        m, r = run_ablation(retriever, subset_queries, subset_relevance, boosts_config=cfg)
        print(f"{label:15}: NDCG@10={m.get('ndcg@10',0):.4f}, Recall@10={m.get('recall@10',0):.4f}")

if __name__ == "__main__":
    main()

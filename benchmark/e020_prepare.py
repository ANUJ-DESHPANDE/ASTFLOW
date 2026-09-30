"""Prepare E020 train-only model and E018 DEV hard-negative evidence, without DEV scoring."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever, tokenize
from benchmark.campaign import ranks_from_scores
from benchmark.e017_train import load_mined, train_data
from benchmark.e019_operator_rerank import load_docs
from benchmark.e020_ranker import FEATURES, features, terms
from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets

OUT = Path("benchmark/results/E020-hard-negative-ranking")


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    corpus, queries, qrels, train_ids = train_data()
    train_ids = train_ids[:300]
    dev = query_sets(qrels)["dev"]
    assert not (set(train_ids) & set(dev))
    ids, docs = load_docs(corpus, ".venv-gpu/apps-corpus-vectors-gte-modernbert-base.npz")
    pos = {d: i for i, d in enumerate(ids)}
    df = Counter()
    for d in ids:
        df.update(terms(corpus[d]))
    idf = {t: math.log((len(ids) + 1) / (n + 1)) + 1 for t, n in df.items()}
    dump("idf.json", idf)

    mined = load_mined(".astflow/e017/mined", sorted(set(qrels) - set(query_sets(qrels)["dev"]) - set(query_sets(qrels)["confirmation"])), 4)
    model = Embedder(Settings())
    assert model.load(), model.reason
    train_vectors = model.encode([queries[q] for q in train_ids], kind="query")
    raw, pairs, pair_keys = [], [], []
    for q, qvec in zip(train_ids, train_vectors):
        dense = docs @ qvec
        positive = next(iter(qrels[q]))
        negatives = [d for d in mined[q] if d != positive][:10]
        pf = features(queries[q], corpus[positive], dense[pos[positive]], idf)
        raw.append(pf)
        for negative in negatives:
            nf = features(queries[q], corpus[negative], dense[pos[negative]], idf)
            raw.append(nf)
            pairs.append((pf, nf))
            pair_keys.append(f"{q}\t{positive}\t{negative}")
    raw = np.asarray(raw)
    mean, scale = raw.mean(axis=0), raw.std(axis=0)
    scale[scale < 1e-9] = 1
    diff = np.asarray([(p - n) / scale for p, n in pairs])
    x = np.concatenate([diff, -diff])
    y = np.concatenate([np.ones(len(diff)), np.zeros(len(diff))])
    ranker = LogisticRegression(C=1.0, fit_intercept=False, max_iter=1000, random_state=20260929)
    ranker.fit(x, y)
    coef = ranker.coef_[0]
    assert coef[0] > 0, "trained dense coefficient must be positive"
    training = {"features": FEATURES, "mean": mean.tolist(), "scale": scale.tolist(), "coef": coef.tolist(),
                "train_queries": len(train_ids), "train_pairs": len(pairs),
                "train_ids_sha256": hashlib.sha256("\n".join(train_ids).encode()).hexdigest(),
                "pair_ids_sha256": hashlib.sha256("\n".join(pair_keys).encode()).hexdigest(),
                "idf_sha256": hashlib.sha256((OUT / "idf.json").read_bytes()).hexdigest(),
                "seed": 20260929, "library": "sklearn LogisticRegression C=1 fit_intercept=False"}
    dump("model.json", training)

    reconstructed = json.loads(Path("benchmark/results/E018-ranking-diagnosis/full_rank_reconstruction.json").read_text())
    targets = [r for r in reconstructed["per_query"] if 10 < r["float32_reconstructed_rank"] <= 50]
    assert len(targets) == 32
    chunks = [Chunk(d, d, "", d, "dataset_document", 1, 1, corpus[d], corpus[d],
                    hashlib.sha256(corpus[d].encode()).hexdigest()) for d in ids]
    retriever = Retriever(chunks, None, None, Settings(semantic="off"))
    dev_vectors = np.load(".astflow/e019/query-vectors.npz", allow_pickle=False)
    qvec = dict(zip(dev_vectors["ids"].tolist(), dev_vectors["vectors"]))
    rows = []
    wins = Counter()
    differences = Counter()
    for target in targets:
        q = target["query_id"]
        dense = docs @ qvec[q]
        lexical = np.asarray(retriever.lexical_scores(tokenize(queries[q])))
        positive = next(iter(qrels[q]))
        pi = pos[positive]
        pr = ranks_from_scores(dense, pi)
        assert pr == target["float32_reconstructed_rank"]
        pf = features(queries[q], corpus[positive], dense[pi], idf)
        order = np.argsort(-dense, kind="stable")[:pr - 1]
        for ni in order:
            negative = ids[ni]
            nf = features(queries[q], corpus[negative], dense[ni], idf)
            row = {"query_id": q, "positive_doc_id": positive, "negative_doc_id": negative,
                   "positive_dense_rank": pr, "negative_dense_rank": ranks_from_scores(dense, int(ni)),
                   "positive_dense_score": float(dense[pi]), "negative_dense_score": float(dense[ni]),
                   "positive_bm25_score": float(lexical[pi]), "negative_bm25_score": float(lexical[ni]),
                   "positive_bm25_rank": ranks_from_scores(lexical, pi),
                   "negative_bm25_rank": ranks_from_scores(lexical, int(ni)),
                   "positive_features": dict(zip(FEATURES, pf.tolist())),
                   "negative_features": dict(zip(FEATURES, nf.tolist()))}
            rows.append(row)
            for name, a, b in zip(FEATURES, pf, nf):
                wins[name] += a > b
                differences[name] += float(a - b)
    with (OUT / "hard_negative_pairs.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    dump("feature_analysis.json", {"target_queries": 32, "pairs": len(rows),
                                   "positive_gt_negative_fraction": {n: wins[n] / len(rows) for n in FEATURES},
                                   "mean_positive_minus_negative": {n: differences[n] / len(rows) for n in FEATURES},
                                   "model_coefficients": dict(zip(FEATURES, coef.tolist()))})
    print(json.dumps({"train_pairs": len(pairs), "dev_hard_negative_pairs": len(rows),
                      "coefficients": dict(zip(FEATURES, coef.tolist()))}, indent=2))


if __name__ == "__main__":
    main()

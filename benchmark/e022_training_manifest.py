"""Record available TRAIN-only genuine dense hard negatives without training."""

import hashlib
import json
from pathlib import Path

from benchmark.e017_train import load_mined, train_data

OUT = Path("benchmark/results/E022-strong-reranker")


def digest(values):
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    _, _, qrels, qids = train_data()
    train_a, train_b = qids[:1000], qids[1000:1200]
    mined = load_mined(".astflow/e017/mined", qids, 4)
    rows = []
    usable = 0
    for q in train_a:
        positive = next(iter(qrels[q]))
        candidates = mined[q]
        rank = candidates.index(positive) + 1 if positive in candidates else None
        higher = candidates[:rank - 1] if rank is not None else candidates
        negatives = [d for d in higher if d != positive][:4]
        if negatives:
            usable += 1
        for i, negative in enumerate(negatives):
            rows.append({"query_id": q, "positive_doc_id": positive,
                         "negative_doc_id": negative, "negative_dense_rank": i + 1,
                         "positive_dense_top20_rank": rank})
    with (OUT / "train_hard_negatives.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    config = {"status": "prepared, not trained: CPU feasibility gate failed",
              "train_a_queries": len(train_a), "train_a_ids_sha256": digest(train_a),
              "train_b_queries": len(train_b), "train_b_ids_sha256": digest(train_b),
              "train_a_queries_with_higher_ranked_negatives": usable,
              "hard_negative_pairs": len(rows),
              "negative_source": "E017 frozen GTE TRAIN top-20 mining; only documents ranked above the positive",
              "model": "Alibaba-NLP/gte-reranker-modernbert-base",
              "model_revision": "f7481e6055501a30fb19d090657df9ec1f79ab2c",
              "training_performed": False, "dev_used": False, "test_used": False}
    (OUT / "train_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (OUT / "train_metrics.json").write_text(json.dumps({"status": "not evaluated because operational feasibility failed",
                                                      "train_b_scored": False}, indent=2) + "\n", encoding="utf-8")
    (OUT / "train_target_bucket.json").write_text(json.dumps({"status": "not evaluated because operational feasibility failed",
                                                            "train_b_scored": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()

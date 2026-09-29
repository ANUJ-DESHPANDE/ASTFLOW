"""Reproduce E018 from frozen campaign candidates and the established train DEV split.

The candidate ZIP is the campaign's saved dense top-200. Full-depth aggregate
recall is read from its frozen metrics; ranks beyond 200 are deliberately not
invented. No TEST labels are loaded by this script.
"""

import argparse
import hashlib
import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import Retriever, tokenize
from benchmark.campaign import ranks_from_scores
from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", default=".venv-gpu/campaign-candidates.zip")
    parser.add_argument("--output", default="benchmark/results/E018-ranking-diagnosis")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    corpus, queries, qrels = load_dataset_split("train")
    qids = query_sets(qrels)["dev"]
    frozen = json.loads(Path("benchmark/results/campaign/campaign.json").read_text(encoding="utf-8"))
    dev = frozen["sets"]["dev"]
    with zipfile.ZipFile(args.candidates) as archive:
        candidates = json.loads(archive.read("candidates.json"))["dev"]["dense_top200"]
    assert set(candidates) == set(qids)
    assert len(qids) == 300 and all(len(qrels[q]) == 1 for q in qids)

    ranks = {}
    for q in qids:
        positive = next(iter(qrels[q]))
        docs = candidates[q]
        assert len(docs) == 200 and len(docs) == len(set(docs))
        ranks[q] = docs.index(positive) + 1 if positive in docs else None
    buckets = [("rank 1", 1, 1), ("rank 2-5", 2, 5), ("rank 6-10", 6, 10),
               ("rank 11-20", 11, 20), ("rank 21-50", 21, 50),
               ("rank 51-100", 51, 100), ("rank 101-200", 101, 200)]
    counts = []
    cumulative = 0
    for label, lo, hi in buckets:
        n = sum(r is not None and lo <= r <= hi for r in ranks.values())
        cumulative += n
        counts.append({"bucket": label, "queries": n, "percentage": n / len(qids),
                       "cumulative_recall": cumulative / len(qids)})
    for label, lo, hi in [("rank 201-500", 201, 500), ("rank 501-1000", 501, 1000)]:
        n = round(dev["systems"]["dense"][f"r@{hi}"] * len(qids)) - cumulative
        cumulative += n
        counts.append({"bucket": label, "queries": n, "percentage": n / len(qids),
                       "cumulative_recall": cumulative / len(qids)})
    counts.append({"bucket": "not retrieved", "queries": len(qids) - cumulative,
                   "percentage": (len(qids) - cumulative) / len(qids),
                   "cumulative_recall": cumulative / len(qids)})
    assert sum(x["queries"] for x in counts) == len(qids)

    dmet = dev["systems"]["dense"]
    baseline = {"experiment": "E018", "baseline_commit": "fec272f",
                "dev_queries": len(qids), "dev_query_ids_sha256": digest("\n".join(qids).encode()),
                "qrels_sha256": digest(json.dumps({q: qrels[q] for q in qids}, sort_keys=True).encode()),
                "candidate_zip_sha256": digest(Path(args.candidates).read_bytes()),
                "frozen_campaign_sha256": digest(Path("benchmark/results/campaign/campaign.json").read_bytes()),
                **{key: dmet[src] for key, src in [("ndcg10", "ndcg@10"), ("mrr10", "mrr@10"),
                    ("recall10", "r@10"), ("recall50", "r@50"),
                    ("recall100", "r@100"), ("recall500", "r@500"), ("recall1000", "r@1000")]}}
    baseline["recall20"] = sum(r is not None and r <= 20 for r in ranks.values()) / len(qids)
    dump(out / "baseline.json", baseline)
    dump(out / "rank_buckets.json", counts)

    recoverable = [r for r in ranks.values() if r is not None and 10 < r <= 200]
    total_recoverable = round((dmet["r@1000"] - dmet["r@10"]) * len(qids))
    oracle = {"recoverable_top1000": total_recoverable,
              "observed_top200": len(recoverable),
              "observed_top200_mean_rank": statistics.mean(recoverable),
              "observed_top200_median_rank": statistics.median(recoverable),
              "observed_top200_p75_rank": float(np.percentile(recoverable, 75)),
              "observed_top200_p90_rank": float(np.percentile(recoverable, 90)),
              "candidate_set_oracle_ndcg10": dmet["r@1000"],
              "candidate_set_oracle_mrr10": dmet["r@1000"],
              "note": "Oracle is a ceiling, not an achievable model score. Rank statistics only use saved top-200 lists."}
    dump(out / "oracle_analysis.json", oracle)

    # Existing campaign already scored exact product BM25 on the same 300 queries.
    overlap = dev["overlap_dense_vs_bm25code"]
    complement = {"dense": {k: dmet[f"r@{k}"] for k in (10, 100, 1000)},
                  "bm25": {k: dev["systems"]["bm25_code"][f"r@{k}"] for k in (10, 100, 1000)},
                  "overlap": overlap,
                  "union_recall": {k: 1 - overlap[f"top{k}"]["neither"] / len(qids) for k in (10, 100, 1000)},
                  "bm25_unique_top10": overlap["top10"]["bm25_only"],
                  "bm25_unique_top1000": overlap["top1000"]["bm25_only"]}

    doc_ids = sorted(corpus)
    doc_pos = {d: i for i, d in enumerate(doc_ids)}
    chunks = [Chunk(d, d, "", d, "dataset_document", 1, 1, corpus[d], corpus[d],
                    hashlib.sha256(corpus[d].encode()).hexdigest()) for d in doc_ids]
    retriever = Retriever(chunks, None, None, Settings(semantic="off"))
    bm25_ranks = {}
    bm25_scores = {}
    for q in qids:
        scores = np.asarray(retriever.lexical_scores(tokenize(queries[q])))
        bm25_scores[q] = scores
        bm25_ranks[q] = ranks_from_scores(scores, doc_pos[next(iter(qrels[q]))])
    assert sum(r <= 10 for r in bm25_ranks.values()) == round(complement["bm25"][10] * len(qids))
    assert sum(r <= 100 for r in bm25_ranks.values()) == round(complement["bm25"][100] * len(qids))
    dense_fail = [q for q in qids if ranks[q] is None or ranks[q] > 10]
    complement["conditional_on_dense_outside_top10"] = {
        f"bm25_top{k}": sum(bm25_ranks[q] <= k for q in dense_fail) for k in (10, 20, 50, 100)}
    complement["conditional_on_dense_outside_top10"]["queries"] = len(dense_fail)
    complement["conditional_on_dense_outside_top1000"] = {
        "queries": overlap["top1000"]["neither"],
        "bm25_top1000": overlap["top1000"]["bm25_only"]}
    dump(out / "bm25_complementarity.json", complement)

    errors = []
    negative_rows = []
    signals = Counter()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(".astflow/e017/train-300/final", local_files_only=True)
    doc_tokens = {d: len(tokenizer(corpus[d], add_special_tokens=True, truncation=False)["input_ids"])
                  for d in doc_ids}
    lengths = {"top10": [], "rank11to200": [], "outside200": []}
    for q in qids:
        rank = ranks[q]
        positive = next(iter(qrels[q]))
        length_bucket = "top10" if rank is not None and rank <= 10 else "rank11to200" if rank is not None else "outside200"
        lengths[length_bucket].append(doc_tokens[positive])
        if rank is not None and rank <= 10:
            continue
        top = candidates[q][:10]
        positive_text = corpus[positive]
        row = {"query_id": q, "query": queries[q], "positive_doc_id": positive,
               "positive_rank_top200": rank, "positive_chars": len(positive_text),
               "positive_model_tokens": doc_tokens[positive], "bm25_positive_rank": bm25_ranks[q],
               "top10_doc_ids": top}
        errors.append(row)
        if rank is not None:
            negatives = [{"doc_id": d, "rank": i + 1, "text": corpus[d][:1000],
                          "bm25_score": float(bm25_scores[q][doc_pos[d]])}
                         for i, d in enumerate(top) if d != positive]
            negative_rows.append({"query_id": q, "positive_doc_id": positive,
                                  "positive_rank": rank, "positive_text": positive_text[:1000],
                                  "bm25_positive_score": float(bm25_scores[q][doc_pos[positive]]),
                                  "higher_ranked_negatives": negatives})
            query_terms = set(queries[q].lower().split())
            overlap_positive = len(query_terms.intersection(positive_text.lower().split()))
            overlap_top = len(query_terms.intersection(corpus[top[0]].lower().split()))
            signals["top_false_positive_more_exact_query_words"] += overlap_top > overlap_positive
            signals["positive_exceeds_512_model_tokens"] += doc_tokens[positive] > 512
            signals["top1_exceeds_512_model_tokens"] += doc_tokens[top[0]] > 512
    for name, rows in [("ranking_errors.jsonl", errors), ("hard_negatives.jsonl", negative_rows)]:
        with (out / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    dump(out / "error_taxonomy.json", {"deterministic_signals": signals,
                                       "positive_document_token_lengths": {
                                           k: {"queries": len(v), "median": statistics.median(v),
                                               "exceeds_512": sum(x > 512 for x in v)} for k, v in lengths.items()},
                                       "tokenizer": ".astflow/e017/train-300/final (ModernBERT tokenizer)",
                                       "note": "Deterministic signals only; no semantic labels inferred."})
    hashes = {p.name: digest(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}
    dump(out / "artifact_hashes.json", hashes)
    print(json.dumps({"baseline": baseline, "buckets": counts, "oracle": oracle,
                      "bm25": complement, "signals": signals}, indent=2))


if __name__ == "__main__":
    main()

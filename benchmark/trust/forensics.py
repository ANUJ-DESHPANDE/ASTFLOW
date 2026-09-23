"""Diagnostics computed from frozen runs + qrels. Qrels are used here ONLY to
measure; nothing in this module feeds back into retrieval."""
import math
import random

BUCKETS = [("rank 1", 1, 1), ("ranks 2-10", 2, 10), ("ranks 11-50", 11, 50), ("ranks 51-100", 51, 100),
           ("ranks 101-500", 101, 500), ("ranks 501-1000", 501, 1000)]


def first_relevant_rank(ranked: list[str], rels: dict[str, int]) -> int | None:
    return next((i + 1 for i, d in enumerate(ranked) if rels.get(d, 0) > 0), None)


def rank_buckets(run: dict, qrels: dict, judged: list[str]) -> dict:
    counts = {name: 0 for name, _, _ in BUCKETS}
    counts["not retrieved (beyond depth)"] = 0
    for qid in judged:
        r = first_relevant_rank(run.get(qid, []), qrels[qid])
        label = next((n for n, lo, hi in BUCKETS if r is not None and lo <= r <= hi), "not retrieved (beyond depth)")
        counts[label] += 1
    n = len(judged)
    cumulative = {f"relevant in top {k}": sum(1 for q in judged if (r := first_relevant_rank(run.get(q, []), qrels[q])) and r <= k) / n
                  for k in (10, 20, 50, 100, 500, 1000)} if n else {}
    return {"counts": counts, "fractions": {k: v / n for k, v in counts.items()} if n else {}, "cumulative": cumulative}


def ndcg10(ranked: list[str], rels: dict[str, int]) -> float:
    dcg = sum(rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:10]))
    ideal = sorted((g for g in rels.values() if g > 0), reverse=True)[:10]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def oracle_ceiling(run: dict, qrels: dict, judged: list[str], k: int) -> float:
    """Best NDCG@10 achievable by only REORDERING the top-k candidates already retrieved.
    Diagnostic only: it uses relevance labels and is not a deployable ranker."""
    total = 0.0
    for qid in judged:
        candidates = run.get(qid, [])[:k]
        reordered = sorted(candidates, key=lambda d: -qrels[qid].get(d, 0))
        total += ndcg10(reordered, qrels[qid])
    return total / len(judged) if judged else 0.0


def mode_comparison(runs: dict[str, dict], qrels: dict, judged: list[str]) -> dict:
    per = {m: {q: ndcg10(r.get(q, []), qrels[q]) for q in judged} for m, r in runs.items()}
    out = {}
    if {"bm25", "dense", "hybrid"} <= set(per):
        b, d, h = per["bm25"], per["dense"], per["hybrid"]
        out = {"all_three_zero": sum(1 for q in judged if b[q] == d[q] == h[q] == 0),
               "bm25_only_nonzero": sum(1 for q in judged if b[q] > 0 and d[q] == 0),
               "dense_only_nonzero": sum(1 for q in judged if d[q] > 0 and b[q] == 0),
               "both_nonzero": sum(1 for q in judged if b[q] > 0 and d[q] > 0),
               "hybrid_beats_both": sum(1 for q in judged if h[q] > max(b[q], d[q])),
               "hybrid_below_bm25": sum(1 for q in judged if h[q] < b[q]),
               "hybrid_below_dense": sum(1 for q in judged if h[q] < d[q]),
               "best_single_mode": {m: sum(1 for q in judged if per[m][q] > 0 and per[m][q] == max(x[q] for x in per.values()))
                                    for m in per}}
    return out


def paired_bootstrap(baseline: dict[str, float], candidate: dict[str, float], samples: int = 10000, seed: int = 20260923) -> dict:
    """Mean per-query delta and a fixed-seed 95% bootstrap interval over queries."""
    queries = sorted(set(baseline) & set(candidate))
    deltas = [candidate[q] - baseline[q] for q in queries]
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples))
    return {"queries": n, "mean_delta": sum(deltas) / n, "ci95": [means[int(0.025 * samples)], means[int(0.975 * samples) - 1]],
            "improved": sum(1 for x in deltas if x > 0), "worsened": sum(1 for x in deltas if x < 0), "seed": seed}

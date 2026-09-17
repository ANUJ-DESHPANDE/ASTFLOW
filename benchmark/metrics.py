import math


def metrics(ranked_ids: list[str], relevance: dict[str, int], k: int = 10):
    # Unique document IDs: repeated hits must never inflate relevance metrics.
    ranked = list(dict.fromkeys(ranked_ids))
    gains = [relevance.get(sid, 0) for sid in ranked[:k]]
    dcg = sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(gains))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(ideal))
    rr = next((1 / (i + 1) for i, sid in enumerate(ranked) if relevance.get(sid, 0) > 0), 0.)
    positives = {sid for sid, grade in relevance.items() if grade > 0}
    return {f"ndcg@{k}": dcg / idcg if idcg else 0., "mrr": rr,
            f"recall@{k}": len(set(ranked[:k]) & positives) / len(positives) if positives else 0.}

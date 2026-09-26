"""E005 screen: does a code-retrieval embedding model beat MiniLM on CoIR Apps, measured off the test split?

Stages (benchmark/EXPERIMENTS.md, E005 pre-registration):
  micro  N train-split queries against their relevant documents plus D random distractors (minutes per model)
  dev    N train-split queries against the full 8,765-document corpus (the realistic setting)

Only the CoIR Apps *train* qrels are used, so the official test split stays untouched until the final MTEB run.
Hybrid is ASTFLOW's own Retriever (BM25 + dense, RRF k=60, boosts off) with the candidate model's vectors, so the
number measured here is the number the product path would produce. A failure dump of the control model's misses
is printed for the failure analysis that motivated the experiment.
"""
import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import Retriever, tokenize

DATASET = "CoIR-Retrieval/apps"
REVISION = "f22508f96b7a36c2415181ed8bb76f76e04ae2d5"

# One entry per screened model. Prefixes follow each model card; max_seq caps CPU cost (queries: median 467,
# p90 759 MiniLM word-pieces), and never exceeds what the model was trained for.
PROFILES = {
    "sentence-transformers/all-MiniLM-L6-v2": {"query_prefix": "", "doc_prefix": "", "max_seq": 256, "remote_code": False},
    "Alibaba-NLP/gte-modernbert-base": {"query_prefix": "", "doc_prefix": "", "max_seq": 1024, "remote_code": False},
    "ibm-granite/granite-embedding-english-r2": {"query_prefix": "", "doc_prefix": "", "max_seq": 1024, "remote_code": False},
    "nomic-ai/CodeRankEmbed": {"query_prefix": "Represent this query for searching relevant code: ", "doc_prefix": "",
                               "max_seq": 1024, "remote_code": True},
}
CONTROL = "sentence-transformers/all-MiniLM-L6-v2"


def load_dataset_split(split: str):
    import datasets
    cache = str(ROOT / ".astflow" / "datasets" / "hub")
    splits = datasets.get_dataset_split_names(DATASET, "default", revision=REVISION)
    print(f"qrels splits available: {splits}", flush=True)
    if split not in splits:
        raise SystemExit(f"split {split!r} unavailable; refusing to fall back to test")
    load = lambda config, s: datasets.load_dataset(DATASET, config, split=s, revision=REVISION, cache_dir=cache)
    corpus_rows = load("corpus", datasets.get_dataset_split_names(DATASET, "corpus", revision=REVISION)[0])
    query_rows = load("queries", datasets.get_dataset_split_names(DATASET, "queries", revision=REVISION)[0])
    corpus = {str(r["_id"]): (r.get("title", "") + "\n" + r["text"]).strip() for r in corpus_rows}
    queries = {str(r["_id"]): r["text"] for r in query_rows}
    qrels = {}
    for r in load("default", split):
        if int(r["score"]) > 0:
            qrels.setdefault(str(r["query-id"]), {})[str(r["corpus-id"])] = int(r["score"])
    missing = [q for q, rel in qrels.items() if q not in queries or any(d not in corpus for d in rel)]
    print(f"corpus {len(corpus)} · queries {len(queries)} · {split} qrels {len(qrels)} · unresolvable {len(missing)}", flush=True)
    qrels = {q: rel for q, rel in qrels.items() if q not in missing}
    return corpus, queries, qrels


def select(corpus, qrels, stage, n_queries, n_distractors, seed):
    rng = random.Random(seed)
    qids = sorted(qrels)
    rng.shuffle(qids)
    qids = sorted(qids[:n_queries])
    if stage == "dev":
        return qids, sorted(corpus)
    positives = {d for q in qids for d in qrels[q]}
    others = sorted(set(corpus) - positives)
    rng.shuffle(others)
    return qids, sorted(positives | set(others[:n_distractors]))


def stratum(code: str) -> str:
    """LeetCode-style starter code (named method mirrors the problem) vs stdin programs (terse, no names)."""
    return "starter" if "class Solution" in code else "stdin"


def rank_of(ranking, relevant):
    return next((i + 1 for i, d in enumerate(ranking) if d in relevant), None)


def summarize(ranks):
    n = len(ranks)
    ndcg = sum(1 / np.log2(r + 1) for r in ranks if r and r <= 10) / n  # exactly one relevant doc per query
    mrr = sum(1 / r for r in ranks if r and r <= 10) / n
    hit = lambda k: sum(1 for r in ranks if r and r <= k) / n
    return {"ndcg@10": ndcg, "mrr@10": mrr, "r@10": hit(10), "r@50": hit(50), "r@100": hit(100)}


def per_query_ndcg(ranks):
    return np.array([1 / np.log2(r + 1) if r and r <= 10 else 0. for r in ranks])


def bootstrap(delta, seed=20260923, samples=5000):
    rng = np.random.default_rng(seed)
    means = rng.choice(delta, size=(samples, len(delta)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


class QueryVectors:
    """Embedder stand-in for Retriever: returns the pre-computed (prefixed) query vector."""
    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, texts, **_):
        return np.stack([self.vectors[t] for t in texts])


def run_model(name, corpus, queries, qrels, qids, doc_ids, cache_dir: Path, threads: int, budget_s: float = 1e9):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(threads)
    profile = PROFILES[name]
    started = time.perf_counter()
    model = SentenceTransformer(name, device="cpu", trust_remote_code=profile["remote_code"])
    model.max_seq_length = min(profile["max_seq"], model.max_seq_length or profile["max_seq"])
    load_s = time.perf_counter() - started
    texts = [corpus[d] for d in doc_ids]
    # Cache identity: model, sequence cap, prefix and every document's id *and* content (never reuse stale vectors).
    content = "\n".join(d + ":" + hashlib.sha256(t.encode()).hexdigest() for d, t in zip(doc_ids, texts))
    key = hashlib.sha256((name + str(model.max_seq_length) + profile["doc_prefix"] + content).encode()).hexdigest()[:24]
    doc_file = cache_dir / f"docs-{key}.npy"
    started = time.perf_counter()
    if doc_file.exists():
        docs = np.load(doc_file)
        doc_s, doc_cached = time.perf_counter() - started, True
    else:
        # Encode in slices with progress; stop early (kill rule) when the projected time exceeds the budget.
        parts, step = [], 256
        for start in range(0, len(texts), step):
            parts.append(model.encode([profile["doc_prefix"] + t for t in texts[start:start + step]], batch_size=16,
                                      normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype(np.float32))
            done, elapsed = min(start + step, len(texts)), time.perf_counter() - started
            projected = elapsed / done * len(texts)
            print(f"   {name}: {done}/{len(texts)} docs · {done / elapsed:.1f} docs/s · projected {projected / 60:.1f} min", flush=True)
            if projected > budget_s and done < len(texts):
                raise TimeoutError(f"STOPPED-TIME-LIMIT: {done / elapsed:.2f} docs/s projects {projected / 60:.1f} min for "
                                   f"{len(texts)} documents (budget {budget_s / 60:.0f} min)")
        docs = np.vstack(parts)
        doc_s, doc_cached = time.perf_counter() - started, False
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(doc_file, docs)
    started = time.perf_counter()
    qvecs = model.encode([profile["query_prefix"] + queries[q] for q in qids], batch_size=16, normalize_embeddings=True,
                         convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
    query_s = time.perf_counter() - started

    chunks = [Chunk(d, d, "", d, "dataset_document", 1, max(1, len(t.splitlines())), t, t, hashlib.sha256(t.encode()).hexdigest())
              for d, t in zip(doc_ids, texts)]
    retriever = Retriever(chunks, docs, QueryVectors({queries[q]: v for q, v in zip(qids, qvecs)}), Settings(semantic="off"))
    ranks = {"dense": [], "bm25": [], "hybrid": []}
    latency = []
    for q, v in zip(qids, qvecs):
        rel = qrels[q]
        order = np.argsort(-(docs @ v), kind="stable")[:1000]
        ranks["dense"].append(rank_of([doc_ids[i] for i in order], rel))
        t0 = time.perf_counter()
        rows, _ = retriever.rank(queries[q], mode="hybrid", boosts=False, limit=1000)
        latency.append((time.perf_counter() - t0) * 1000)
        ranks["hybrid"].append(rank_of([r["chunk"].chunk_id for r in rows], rel))
        rows, _ = retriever.rank(queries[q], mode="bm25", boosts=False, limit=1000)
        ranks["bm25"].append(rank_of([r["chunk"].chunk_id for r in rows], rel))
    return {
        "model": name, "max_seq_length": model.max_seq_length, "dim": int(docs.shape[1]),
        "params": sum(p.numel() for p in model.parameters()),
        "cost": {"load_s": round(load_s, 1), "doc_encode_s": round(doc_s, 1), "doc_cached": doc_cached,
                 "docs_per_s": round(len(texts) / doc_s, 2) if not doc_cached else None,
                 "query_encode_s": round(query_s, 1), "queries_per_s": round(len(qids) / query_s, 2),
                 "rank_p50_ms": round(statistics.median(latency), 2), "threads": threads},
        "ranks": ranks, "metrics": {m: summarize(r) for m, r in ranks.items()},
    }, model


def failure_dump(result, model, corpus, queries, qrels, qids, doc_ids, limit):
    """Measured failure signals for the control model's hybrid misses (relevant document not in the top 10)."""
    hybrid, bm25, dense = result["ranks"]["hybrid"], result["ranks"]["bm25"], result["ranks"]["dense"]
    tok = model.tokenizer
    rows = []
    for i, q in enumerate(qids):
        if hybrid[i] and hybrid[i] <= 10:
            continue
        rel = next(iter(qrels[q]))
        q_terms, d_terms = set(tokenize(queries[q])), set(tokenize(corpus[rel]))
        in_b, in_d, in_h = [r is not None and r <= 100 for r in (bm25[i], dense[i], hybrid[i])]
        if in_h:
            category = "retrieved (top 100) but ranked 11-100"
        elif in_b or in_d:
            category = "one retriever top 100, lost by fusion"
        else:
            category = "absent from both retrievers' top 100"
        rows.append({"qid": q, "rel": rel, "hybrid": hybrid[i], "bm25": bm25[i], "dense": dense[i], "category": category,
                     "query_wordpieces": len(tok.tokenize(queries[q])), "doc_wordpieces": len(tok.tokenize(corpus[rel])),
                     "query_terms_in_doc": round(len(q_terms & d_terms) / max(1, len(q_terms)), 3),
                     "doc_terms_in_query": round(len(q_terms & d_terms) / max(1, len(d_terms)), 3)})
    n = len(rows)
    if not n:
        return {"count": 0, "categories": {}, "rows": []}
    for r in rows[:limit]:
        print(f"\n### {r['qid']} → {r['rel']} (hybrid rank {r['hybrid']}, bm25 {r['bm25']}, dense {r['dense']}; {r['category']})")
        print("QUERY: " + " ".join(queries[r["qid"]].split())[:700])
        print("RELEVANT DOC:\n" + corpus[r["rel"]][:500])
    print(f"\n## Control failure analysis ({n} of {len(qids)} queries miss the top 10)\n")
    cats = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    for c, k in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"- {c}: {k} ({k / n:.1%})")
    trunc = sum(r["query_wordpieces"] > 254 for r in rows)
    print(f"- query longer than the 254-piece dense window (truncated): {trunc} ({trunc / max(1, n):.1%})")
    for key in ("query_terms_in_doc", "doc_terms_in_query", "query_wordpieces", "doc_wordpieces"):
        vals = [r[key] for r in rows]
        print(f"- {key}: median {statistics.median(vals)}, p90 {sorted(vals)[int(.9 * (len(vals) - 1))]}")
    return {"count": n, "categories": cats, "rows": rows}


def combine(directory: Path):
    """Paired comparison of every screened model against the control on identical queries (separate CI jobs)."""
    results, meta, meta_strata = {}, None, None
    for path in sorted(directory.rglob("e005-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        key = (report["stage"], report["seed"], report["documents"], tuple(report["queries"]))
        if meta is None:
            meta = key
        elif key != meta:
            raise SystemExit(f"{path} was run on a different query/document selection; refusing to pair it")
        meta_strata = report.get("strata")
        results.update({n: r for n, r in report["results"].items() if "error" not in r})
    if CONTROL not in results:
        raise SystemExit("control model result missing")
    lines = [f"# E005 {meta[0]} paired vs {CONTROL} ({len(meta[3])} queries × {meta[2]} docs)", "",
             "| Model | Mode | NDCG@10 | Δ vs control hybrid | 95% CI | MRR@10 | R@100 | docs/s |", "|---|---|---:|---:|---|---:|---:|---:|"]
    base = per_query_ndcg(results[CONTROL]["ranks"]["hybrid"])
    strata = np.array(meta_strata) if meta_strata else None
    for name, res in results.items():
        for mode in ("dense", "hybrid"):
            q = per_query_ndcg(res["ranks"][mode])
            low, high = bootstrap(q - base)
            m = res["metrics"][mode]
            lines.append(f"| {name} | {mode} | {m['ndcg@10']:.4f} | {q.mean() - base.mean():+.4f} | [{low:+.4f}, {high:+.4f}] | "
                         f"{m['mrr@10']:.4f} | {m['r@100']:.4f} | {res['cost']['docs_per_s']} |")
            for group in (sorted(set(meta_strata)) if meta_strata else []):
                mask = strata == group
                low, high = bootstrap(q[mask] - base[mask])
                lines.append(f"| ↳ {group} ({int(mask.sum())}) | {mode} | {q[mask].mean():.4f} | {q[mask].mean() - base[mask].mean():+.4f} | "
                             f"[{low:+.4f}, {high:+.4f}] | | | |")
    text = "\n".join(lines) + "\n"
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combine", type=Path, help="pair previously written results against the control and exit")
    parser.add_argument("--models", default=",".join(PROFILES))
    parser.add_argument("--stage", choices=["micro", "dev"], default="micro")
    parser.add_argument("--split", default="train")
    parser.add_argument("--queries", type=int, default=300)
    parser.add_argument("--distractors", type=int, default=2700)
    parser.add_argument("--seed", type=int, default=20260926)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--encode-budget-min", type=float, default=30, help="stop a model whose document encoding projects longer")
    parser.add_argument("--failure-dump", type=int, default=0, help="print N control-model misses (control only)")
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "e005")
    args = parser.parse_args()
    if args.combine:
        return combine(args.combine)
    corpus, queries, qrels = load_dataset_split(args.split)
    qids, doc_ids = select(corpus, qrels, args.stage, args.queries, args.distractors, args.seed)
    print(f"stage {args.stage}: {len(qids)} {args.split} queries × {len(doc_ids)} documents", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    strata = [stratum(corpus[next(iter(qrels[q]))]) for q in qids]
    print(f"strata: {dict((k, strata.count(k)) for k in sorted(set(strata)))}", flush=True)
    report = {"stage": args.stage, "split": args.split, "seed": args.seed, "queries": qids, "documents": len(doc_ids),
              "dataset_revision": REVISION, "strata": strata, "results": {}}
    for name in args.models.split(","):
        try:
            result, model = run_model(name, corpus, queries, qrels, qids, doc_ids, ROOT / ".astflow" / "e005-cache", args.threads,
                                      args.encode_budget_min * 60)
        except Exception as exc:  # a model that cannot load is recorded, not fatal to the others
            print(f"!! {name}: {type(exc).__name__}: {exc}", flush=True)
            report["results"][name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        if name == CONTROL and args.failure_dump:
            result["failures"] = failure_dump(result, model, corpus, queries, qrels, qids, doc_ids, args.failure_dump)
        report["results"][name] = result
        m = result["metrics"]
        print(f"== {name}: dense {m['dense']['ndcg@10']:.4f} hybrid {m['hybrid']['ndcg@10']:.4f} bm25 {m['bm25']['ndcg@10']:.4f} "
              f"cost {result['cost']}", flush=True)
    safe = "_".join(n.split("/")[-1] for n in args.models.split(","))[:80]
    (args.output / f"e005-{args.stage}-{safe}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    lines = [f"# E005 {args.stage}: {len(qids)} {args.split} queries × {len(doc_ids)} docs", "",
             "| Model | Mode | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 | docs/s | queries/s |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, res in report["results"].items():
        if "error" in res:
            lines.append(f"| {name} | ERROR | {res['error'][:80]} | | | | | | |")
            continue
        for mode in ("bm25", "dense", "hybrid"):
            m = res["metrics"][mode]
            lines.append(f"| {name} | {mode} | {m['ndcg@10']:.4f} | {m['mrr@10']:.4f} | {m['r@10']:.4f} | {m['r@50']:.4f} | "
                         f"{m['r@100']:.4f} | {res['cost']['docs_per_s']} | {res['cost']['queries_per_s']} |")
            for group in sorted(set(strata)):
                sub = summarize([r for r, g in zip(res["ranks"][mode], strata) if g == group])
                lines.append(f"| ↳ {group} ({strata.count(group)}) | {mode} | {sub['ndcg@10']:.4f} | {sub['mrr@10']:.4f} | "
                             f"{sub['r@10']:.4f} | {sub['r@50']:.4f} | {sub['r@100']:.4f} | | |")
    text = "\n".join(lines) + "\n"
    print("\n" + text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()

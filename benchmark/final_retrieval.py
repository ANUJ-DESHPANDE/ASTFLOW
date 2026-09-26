"""Final retrieval decision (2026-09-26): E004 on MiniLM, and a full-corpus dev gate for gte-modernbert-base.

Subcommands
  e004        MiniLM baseline vs E004 `longquery-mean254` on train-split dev + confirmation, full corpus.
  embed       one shard of gte-modernbert-base embeddings (corpus documents and/or query sets), with timings.
  gate        assemble the shards; GTE Dense vs the current MiniLM Hybrid on the same train queries, full corpus.

Only CoIR Apps *train* queries are used here; the official test split is scored once, by MTEB, for the chosen system.
Query sets: all train qids shuffled with seed 20260926; dev = first 300 (the failure-analysis set), confirmation = next 300.
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
from backend.app.retrieval.search import Retriever
from benchmark.e005_screen import QueryVectors, bootstrap, load_dataset_split, per_query_ndcg, rank_of, summarize

SEED, PER_SET = 20260926, 300
MINILM, GTE, GTE_MAX_SEQ = "sentence-transformers/all-MiniLM-L6-v2", "Alibaba-NLP/gte-modernbert-base", 512


def query_sets(qrels):
    qids = sorted(qrels)
    random.Random(SEED).shuffle(qids)
    return {"dev": sorted(qids[:PER_SET]), "confirmation": sorted(qids[PER_SET:2 * PER_SET])}


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def summary_line(label, m):
    return f"| {label} | {m['ndcg@10']:.4f} | {m['mrr@10']:.4f} | {m['r@10']:.4f} | {m['r@50']:.4f} | {m['r@100']:.4f} |"


def emit(lines):
    text = "\n".join(lines) + "\n"
    print(text, flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)


def ranks_for(retriever, doc_ids, docs, qids, queries, qrels, vectors, modes=("dense", "hybrid")):
    """Rank of the relevant document per query for each mode, using the given query vectors (text -> vector)."""
    retriever.embedder = QueryVectors(vectors)
    out, latency = {m: [] for m in modes}, []
    for q in qids:
        rel = qrels[q]
        if "dense" in modes:
            t0 = time.perf_counter()
            order = np.argsort(-(docs @ vectors[queries[q]]), kind="stable")[:1000]
            latency.append((time.perf_counter() - t0) * 1000)
            out["dense"].append(rank_of([doc_ids[i] for i in order], rel))
        if "hybrid" in modes:
            rows, _ = retriever.rank(queries[q], mode="hybrid", boosts=False, limit=1000)
            out["hybrid"].append(rank_of([r["chunk"].chunk_id for r in rows], rel))
    return out, latency


def build_retriever(corpus, doc_ids, docs):
    chunks = [Chunk(d, d, "", d, "dataset_document", 1, max(1, len(corpus[d].splitlines())), corpus[d], corpus[d],
                    hashlib.sha256(corpus[d].encode()).hexdigest()) for d in doc_ids]
    return Retriever(chunks, docs, None, Settings(semantic="off"))


def paired(label, cand, base):
    delta = per_query_ndcg(cand) - per_query_ndcg(base)
    low, high = bootstrap(delta)
    return {"label": label, "delta": float(delta.mean()), "ci": [low, high]}


# ---------------------------------------------------------------- E004

def chunk_vector(model, ids):
    """Mean-pooled (pre-normalisation) embedding of `[CLS] ids [SEP]` — one chunk, exactly as the baseline sees its window."""
    import torch
    tok, transformer = model.tokenizer, model[0].auto_model
    chunk = [tok.cls_token_id] + list(ids) + [tok.sep_token_id]
    with torch.inference_mode():
        hidden = transformer(input_ids=torch.tensor([chunk]), attention_mask=torch.ones(1, len(chunk), dtype=torch.long)).last_hidden_state
    return hidden[0].mean(dim=0).numpy(), len(chunk)


def e004_vector(model, text):
    """Pre-registered `longquery-mean254`: token-weighted mean of per-chunk mean-pooled embeddings, then L2-normalised."""
    ids = model.tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
    parts = [chunk_vector(model, ids[start:start + 254]) for start in range(0, max(1, len(ids)), 254)]
    vec = np.average(np.stack([p for p, _ in parts]), axis=0, weights=np.array([w for _, w in parts], dtype=np.float64))
    return (vec / np.linalg.norm(vec)).astype(np.float32), ids


def run_e004(args):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(os.cpu_count() or 4)
    corpus, queries, qrels = load_dataset_split("train")
    sets = query_sets(qrels)
    model = SentenceTransformer(MINILM, device="cpu")
    doc_ids = sorted(corpus)
    t0 = time.perf_counter()
    docs = model.encode([corpus[d] for d in doc_ids], batch_size=32, normalize_embeddings=True, convert_to_numpy=True,
                        show_progress_bar=False).astype(np.float32)
    doc_s = time.perf_counter() - t0
    print(f"MiniLM corpus: {len(doc_ids)} docs in {doc_s:.0f} s", flush=True)
    retriever = build_retriever(corpus, doc_ids, docs)
    report = {"experiment": "E004-longquery-mean254", "split": "train", "seed": SEED, "doc_encode_s": doc_s, "sets": {}}
    integrity = {"fit_max_dev": 0.0, "first_chunk_min_cos": 1.0, "fit_checked": 0, "trunc_checked": 0}
    for name, qids in sets.items():
        base_vecs, e4_vecs, base_ms, e4_ms, chunks = {}, {}, [], [], []
        for q in qids:
            text = queries[q]
            t = time.perf_counter()
            base_vecs[text] = model.encode([text], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)[0]
            base_ms.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            e4_vecs[text], ids = e004_vector(model, text)
            e4_ms.append((time.perf_counter() - t) * 1000)
            n = len(ids)
            chunks.append(-(-n // 254))
            cos = float(base_vecs[text] @ e4_vecs[text])
            if n <= 254:  # must equal the baseline encoding exactly
                integrity["fit_max_dev"] = max(integrity["fit_max_dev"], 1 - cos)
                integrity["fit_checked"] += 1
            elif integrity["trunc_checked"] < 25:  # baseline == first chunk only
                first, _ = chunk_vector(model, ids[:254])
                first = first / np.linalg.norm(first)
                integrity["first_chunk_min_cos"] = min(integrity["first_chunk_min_cos"], float(first @ base_vecs[text]))
                integrity["trunc_checked"] += 1
        base, _ = ranks_for(retriever, doc_ids, docs, qids, queries, qrels, base_vecs)
        cand, _ = ranks_for(retriever, doc_ids, docs, qids, queries, qrels, e4_vecs)
        report["sets"][name] = {
            "queries": len(qids), "truncated": sum(c > 1 for c in chunks), "chunks_mean": statistics.mean(chunks),
            "baseline": {m: summarize(r) for m, r in base.items()}, "e004": {m: summarize(r) for m, r in cand.items()},
            "hybrid_delta": paired("hybrid", cand["hybrid"], base["hybrid"]), "dense_delta": paired("dense", cand["dense"], base["dense"]),
            "query_encode_ms": {"baseline_p50": statistics.median(base_ms), "baseline_p95": float(np.percentile(base_ms, 95)),
                                "e004_p50": statistics.median(e4_ms), "e004_p95": float(np.percentile(e4_ms, 95))},
            "ranks": {"baseline": base, "e004": cand}}
    report["integrity"] = integrity
    ok = integrity["fit_max_dev"] <= 1e-5 and integrity["first_chunk_min_cos"] >= 0.999
    passes = {n: s["hybrid_delta"]["delta"] > 0 and s["hybrid_delta"]["ci"][0] > 0 for n, s in report["sets"].items()}
    report["decision"] = "ACCEPT" if ok and all(passes.values()) else ("INVALID" if not ok else "REJECT")
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    (out / "e004.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    lines = [f"# E004 longquery-mean254 (train split, full corpus {len(doc_ids)} docs) — decision: **{report['decision']}**", "",
             f"Integrity: fitting queries max 1-cos {integrity['fit_max_dev']:.2e} ({integrity['fit_checked']} checked); "
             f"baseline vs first chunk min cos {integrity['first_chunk_min_cos']:.6f} ({integrity['trunc_checked']} checked)", ""]
    for name, s in report["sets"].items():
        lines += [f"## {name} ({s['queries']} queries, {s['truncated']} truncated, mean {s['chunks_mean']:.2f} chunks)", "",
                  "| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 |", "|---|---:|---:|---:|---:|---:|"]
        for mode in ("dense", "hybrid"):
            lines += [summary_line(f"baseline {mode}", s["baseline"][mode]), summary_line(f"E004 {mode}", s["e004"][mode])]
        h, d, ms = s["hybrid_delta"], s["dense_delta"], s["query_encode_ms"]
        lines += ["", f"Hybrid ΔNDCG@10 {h['delta']:+.4f} [{h['ci'][0]:+.4f}, {h['ci'][1]:+.4f}] · Dense ΔNDCG@10 {d['delta']:+.4f} "
                      f"[{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}] · query encode P50/P95 {ms['baseline_p50']:.0f}/{ms['baseline_p95']:.0f} ms → "
                      f"{ms['e004_p50']:.0f}/{ms['e004_p95']:.0f} ms", ""]
    emit(lines)


# ---------------------------------------------------------------- GTE shards and gate

def run_embed(args):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(os.cpu_count() or 4)
    corpus, queries, qrels = load_dataset_split("train" if args.what != "test" else "test")
    if args.what == "docs":
        ids = sorted(corpus)
        texts = [corpus[d] for d in ids]
    else:
        ids = sorted(qrels) if args.what == "test" else [q for s in query_sets(qrels).values() for q in s]
        texts = [queries[q] for q in ids]
    ids, texts = ids[args.shard::args.of], texts[args.shard::args.of]
    t0 = time.perf_counter()
    model = SentenceTransformer(GTE, device="cpu")
    model.max_seq_length = GTE_MAX_SEQ
    load_s = time.perf_counter() - t0
    vecs, per_item_ms, started = [], [], time.perf_counter()
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # length-sorted batches, as sentence-transformers does
    for b in range(0, len(order), 16):
        idx = order[b:b + 16]
        t = time.perf_counter()
        v = model.encode([texts[i] for i in idx], batch_size=16, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        per_item_ms += [(time.perf_counter() - t) * 1000 / len(idx)] * len(idx)
        vecs.append((idx, v.astype(np.float32)))
        done = b + len(idx)
        print(f"   {args.what} shard {args.shard}/{args.of}: {done}/{len(texts)} · {done / (time.perf_counter() - started):.2f}/s", flush=True)
    matrix = np.zeros((len(texts), model.get_sentence_embedding_dimension()), dtype=np.float32)
    for idx, v in vecs:
        matrix[idx] = v
    elapsed = time.perf_counter() - started
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.what}-{args.shard:02d}"
    np.save(out / f"{stem}.npy", matrix)
    (out / f"{stem}.json").write_text(json.dumps({
        "model": GTE, "max_seq": GTE_MAX_SEQ, "what": args.what, "ids": ids, "keys": [text_key(t) for t in texts],
        "load_s": load_s, "encode_s": elapsed, "per_item_ms": per_item_ms, "threads": torch.get_num_threads(),
        "cpu": os.cpu_count()}), encoding="utf-8")
    print(f"{stem}: {len(texts)} items in {elapsed:.0f} s ({len(texts) / elapsed:.2f}/s)", flush=True)


def load_shards(directory: Path, what: str):
    metas = sorted(directory.rglob(f"{what}-*.json"))
    ids, keys, mats, per_item, encode_s = [], [], [], [], 0.0
    for meta_path in metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ids += meta["ids"]; keys += meta["keys"]; per_item += meta["per_item_ms"]; encode_s += meta["encode_s"]
        mats.append(np.load(meta_path.with_suffix(".npy")))
    return ids, keys, (np.vstack(mats) if mats else None), per_item, encode_s, len(metas)


def run_gate(args):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(os.cpu_count() or 4)
    corpus, queries, qrels = load_dataset_split("train")
    sets = query_sets(qrels)
    shards = Path(args.shards)
    d_ids, d_keys, d_mat, d_ms, d_s, n_d = load_shards(shards, "docs")
    q_ids, q_keys, q_mat, q_ms, q_s, n_q = load_shards(shards, "queries")
    if sorted(d_ids) != sorted(corpus) or any(text_key(corpus[d]) != k for d, k in zip(d_ids, d_keys)):
        raise SystemExit("GTE document shards do not cover the corpus exactly (missing, duplicate or changed documents)")
    want = [q for s in sets.values() for q in s]
    if sorted(q_ids) != sorted(want) or any(text_key(queries[q]) != k for q, k in zip(q_ids, q_keys)):
        raise SystemExit("GTE query shards do not match the dev/confirmation sets")
    pos = {d: i for i, d in enumerate(d_ids)}
    doc_ids = sorted(corpus)
    gte_docs = d_mat[[pos[d] for d in doc_ids]]
    gte_q = {queries[q]: v for q, v in zip(q_ids, q_mat)}
    # Integrity: re-encode a few documents and queries live; they must match the shard vectors.
    model = SentenceTransformer(GTE, device="cpu"); model.max_seq_length = GTE_MAX_SEQ
    probe_d = doc_ids[:: max(1, len(doc_ids) // 5)][:5]
    live = model.encode([corpus[d] for d in probe_d], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    probe_cos = [float(a @ gte_docs[doc_ids.index(d)]) for a, d in zip(live, probe_d)]
    probe_q = want[:3]
    liveq = model.encode([queries[q] for q in probe_q], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    probe_cos += [float(a @ gte_q[queries[q]]) for a, q in zip(liveq, probe_q)]
    del model
    # Current system: MiniLM Hybrid, exactly as in the product benchmark path.
    mini = SentenceTransformer(MINILM, device="cpu")
    mini_docs = mini.encode([corpus[d] for d in doc_ids], batch_size=32, normalize_embeddings=True, convert_to_numpy=True,
                            show_progress_bar=False).astype(np.float32)
    mini_q = {queries[q]: v for q, v in zip(want, mini.encode([queries[q] for q in want], normalize_embeddings=True,
                                                               convert_to_numpy=True, show_progress_bar=False))}
    mini_ret = build_retriever(corpus, doc_ids, mini_docs)
    gte_ret = build_retriever(corpus, doc_ids, gte_docs)
    report = {"model": GTE, "max_seq": GTE_MAX_SEQ, "probe_min_cos": min(probe_cos), "sets": {},
              "cost": {"doc_shards": n_d, "docs": len(d_ids), "doc_encode_s_total": d_s, "docs_per_s_per_runner": len(d_ids) / d_s,
                       "doc_ms_p50": statistics.median(d_ms), "doc_ms_p95": float(np.percentile(d_ms, 95)),
                       "query_shards": n_q, "queries": len(q_ids), "query_encode_s_total": q_s,
                       "query_ms_p50": statistics.median(q_ms), "query_ms_p95": float(np.percentile(q_ms, 95)),
                       "artifact_bytes": int(gte_docs.nbytes)}}
    for name, qids in sets.items():
        cur, _ = ranks_for(mini_ret, doc_ids, mini_docs, qids, queries, qrels, mini_q, modes=("hybrid",))
        gte, lat = ranks_for(gte_ret, doc_ids, gte_docs, qids, queries, qrels, gte_q, modes=("dense",))
        report["sets"][name] = {"current_hybrid": summarize(cur["hybrid"]), "gte_dense": summarize(gte["dense"]),
                                "delta": paired("gte dense vs current hybrid", gte["dense"], cur["hybrid"]),
                                "rank_ms_p50": statistics.median(lat), "rank_ms_p95": float(np.percentile(lat, 95)),
                                "ranks": {"current_hybrid": cur["hybrid"], "gte_dense": gte["dense"]}}
    dev, conf = report["sets"]["dev"]["delta"], report["sets"]["confirmation"]["delta"]
    valid = report["probe_min_cos"] >= 0.999
    passed = dev["delta"] >= 0.05 and dev["ci"][0] > 0 and conf["delta"] > 0 and conf["ci"][0] > 0
    report["decision"] = "INVALID" if not valid else "PASS" if passed else "FAIL"
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    (out / "gte_gate.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    c = report["cost"]
    lines = [f"# GTE dev gate (train split, full corpus {len(doc_ids)} docs) — **{report['decision']}**", "",
             f"Live re-encode vs shard vectors: min cos {report['probe_min_cos']:.6f}", "",
             f"Cost: {c['docs']} docs over {c['doc_shards']} runners, {c['doc_encode_s_total'] / 60:.1f} runner-minutes "
             f"({c['docs_per_s_per_runner']:.2f} docs/s per 4-vCPU runner; per-doc P50 {c['doc_ms_p50']:.0f} ms, P95 {c['doc_ms_p95']:.0f} ms); "
             f"queries per-item P50 {c['query_ms_p50']:.0f} ms, P95 {c['query_ms_p95']:.0f} ms; document matrix {c['artifact_bytes'] / 1e6:.1f} MB", ""]
    for name, s in report["sets"].items():
        d = s["delta"]
        lines += [f"## {name}", "", "| System | NDCG@10 | MRR@10 | R@10 | R@50 | R@100 |", "|---|---:|---:|---:|---:|---:|",
                  summary_line("current MiniLM hybrid", s["current_hybrid"]), summary_line("GTE dense", s["gte_dense"]), "",
                  f"ΔNDCG@10 {d['delta']:+.4f} [{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}] · dense ranking P50 {s['rank_ms_p50']:.1f} ms, "
                  f"P95 {s['rank_ms_p95']:.1f} ms (excludes query encoding)", ""]
    emit(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("e004"); p.add_argument("--output", default=str(ROOT / "out" / "e004"))
    p = sub.add_parser("embed"); p.add_argument("--what", choices=["docs", "queries", "test"], required=True)
    p.add_argument("--shard", type=int, required=True); p.add_argument("--of", type=int, required=True)
    p.add_argument("--output", default=str(ROOT / "out" / "gte"))
    p = sub.add_parser("gate"); p.add_argument("--shards", required=True); p.add_argument("--output", default=str(ROOT / "out" / "gate"))
    args = parser.parse_args()
    {"e004": run_e004, "embed": run_embed, "gate": run_gate}[args.cmd](args)


if __name__ == "__main__":
    main()

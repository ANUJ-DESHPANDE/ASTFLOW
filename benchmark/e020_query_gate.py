"""Cheap frozen-DEV query length diagnostic; never reads TEST."""

import json
from pathlib import Path

import numpy as np
from transformers import AutoTokenizer

from benchmark.e005_screen import load_dataset_split
from benchmark.final_retrieval import query_sets


def main():
    _, queries, qrels = load_dataset_split("train")
    ids = query_sets(qrels)["dev"]
    prior = json.loads(Path("benchmark/results/E018-ranking-diagnosis/full_rank_reconstruction.json").read_text())
    ranks = {row["query_id"]: row["float32_reconstructed_rank"] for row in prior["per_query"]}
    assert len(ids) == len(ranks) == 300
    tok = AutoTokenizer.from_pretrained(".astflow/e017/train-300/final", local_files_only=True)
    groups = {key: [] for key in ("all", "top10", "rank11to50", "rank51to1000", "miss")}
    rows = []
    for q in ids:
        t = queries[q]
        n = len(tok(t, add_special_tokens=True, truncation=False)["input_ids"])
        r = ranks[q]
        group = "top10" if r <= 10 else "rank11to50" if r <= 50 else "rank51to1000" if r <= 1000 else "miss"
        row = {"query_id": q, "raw_chars": len(t), "whitespace_tokens": len(t.split()), "model_tokens": n,
               "exceeds_512": n > 512, "dense_rank": r, "bucket": group}
        rows.append(row)
        groups[group].append(n)
        groups["all"].append(n)
    summary = {g: {"queries": len(v), "exceeds_512": sum(x > 512 for x in v),
                   "percentage_exceeds_512": sum(x > 512 for x in v) / len(v),
                   "median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
                   "p95": float(np.percentile(v, 95))} for g, v in groups.items()}
    fail = groups["rank11to50"] + groups["rank51to1000"]
    a = sum(x > 512 for x in fail)
    b = sum(x > 512 for x in groups["top10"])
    enrichment = (a / len(fail)) / (b / len(groups["top10"])) if b else None
    report = {"tokenizer": ".astflow/e017/train-300/final", "summary": summary,
              "failure_rate_le_512": sum(r["bucket"] != "top10" for r in rows if not r["exceeds_512"]) / sum(not r["exceeds_512"] for r in rows),
              "failure_rate_gt_512": sum(r["bucket"] != "top10" for r in rows if r["exceeds_512"]) / max(1, sum(r["exceeds_512"] for r in rows)),
              "recoverable_exceeds_512": a, "top10_exceeds_512": b, "enrichment": enrichment,
              "condition_a": a >= 11, "condition_b": enrichment is not None and enrichment >= 2,
              "rows": rows}
    report["decision"] = "query-cleanup" if report["condition_a"] and report["condition_b"] else "hard-negative-ranking"
    out = Path("benchmark/results/E020-hard-negative-ranking")
    out.mkdir(parents=True, exist_ok=True)
    (out / "query_length_gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()

"""Final validation run (2026-09-28), step 1: verify the TEST data before the benchmark. Read-only; changes nothing.

Uses the repository's own loader (benchmark.e005_screen.load_dataset_split) and MTEB's AppsRetrieval task loader,
and checks counts, ID integrity and TEST/TRAIN separation. Writes data_check.json next to this file.
"""
import collections
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from benchmark.e005_screen import DATASET, REVISION, load_dataset_split  # noqa: E402
from benchmark.final_retrieval import query_sets  # noqa: E402


def raw_ids(config):
    import datasets
    cache = str(HERE.parents[2] / ".astflow" / "datasets" / "hub")
    split = datasets.get_dataset_split_names(DATASET, config, revision=REVISION)[0]
    rows = datasets.load_dataset(DATASET, config, split=split, revision=REVISION, cache_dir=cache)
    return [str(r["_id"]) for r in rows]


def main():
    report = {"dataset": DATASET, "revision": REVISION}
    corpus, queries, test = load_dataset_split("test")
    _, _, train = load_dataset_split("train")

    doc_ids, query_ids = raw_ids("corpus"), raw_ids("queries")
    dup_docs = [d for d, n in collections.Counter(doc_ids).items() if n > 1]
    dup_queries = [q for q, n in collections.Counter(query_ids).items() if n > 1]
    test_pairs = sum(len(v) for v in test.values())
    rel_per_query = collections.Counter(len(v) for v in test.values())
    test_docs = {d for v in test.values() for d in v}
    train_docs = {d for v in train.values() for d in v}
    dev_conf = query_sets(train)

    report.update({
        "documents": len(corpus), "documents_raw_rows": len(doc_ids), "duplicate_document_ids": dup_docs,
        "distinct_document_texts": len({hashlib.sha256(t.encode()).hexdigest() for t in corpus.values()}),
        "queries_all_splits": len(queries), "queries_raw_rows": len(query_ids), "duplicate_query_ids": dup_queries,
        "test_queries": len(test), "test_qrels_pairs": test_pairs,
        "test_relevant_per_query": dict(rel_per_query),
        "test_relevant_docs_distinct": len(test_docs),
        "test_qrels_unresolvable": sum(1 for q, v in test.items() if q not in queries or any(d not in corpus for d in v)),
        "train_queries": len(train),
        "test_train_query_overlap": len(set(test) & set(train)),
        "test_train_relevant_doc_overlap": len(test_docs & train_docs),
        "dev_confirmation_in_test": len((set(dev_conf["dev"]) | set(dev_conf["confirmation"])) & set(test)),
        "empty_query_texts": sum(1 for q in test if not queries[q].strip()),
        "empty_document_texts": sum(1 for t in corpus.values() if not t.strip()),
        "test_qid_sha256": hashlib.sha256("\n".join(sorted(test)).encode()).hexdigest(),
        "test_qrels_sha256": hashlib.sha256("\n".join(f"{q}\t{d}\t{s}" for q in sorted(test)
                                                        for d, s in sorted(test[q].items())).encode()).hexdigest(),
    })

    # Cross-check against the loader the benchmark actually uses (MTEB) and the repo's committed qrels file.
    import mteb
    task = mteb.get_task("AppsRetrieval")
    report["mteb_task_revision"] = task.metadata.dataset["revision"]
    report["mteb_eval_splits"] = task.metadata.eval_splits
    task.load_data()
    split = task.dataset["default"]["test"]
    m_corpus, m_queries, m_rel = split["corpus"], split["queries"], split["relevant_docs"]
    m_qids = {str(r["id"]) for r in m_queries}
    report["mteb_documents"] = len(m_corpus)
    report["mteb_test_queries"] = len(m_queries)
    report["mteb_test_qrels_pairs"] = sum(1 for v in m_rel.values() for s in v.values() if s > 0)
    report["mteb_matches_repo_loader"] = (m_qids == set(test) and {str(r["id"]) for r in m_corpus} == set(corpus)
                                          and {q: {d: s for d, s in v.items() if s > 0} for q, v in m_rel.items()} == test)

    committed = HERE.parents[1] / "verification" / "apps.qrels"
    if committed.exists():
        rows = [line.split() for line in committed.read_text(encoding="utf-8").splitlines() if line.strip()]
        pairs = {(r[0], r[2]) for r in rows if len(r) >= 4 and int(r[3]) > 0}
        report["committed_apps_qrels_pairs"] = len(pairs)
        report["committed_apps_qrels_match"] = pairs == {(q, d) for q, v in test.items() for d in v}

    (HERE / "data_check.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

"""Build a held-out development/validation split of AppsRetrieval queries.

Why this exists: the guideline's evaluation is scored on the CoIR AppsRetrieval
*test* split, and MTEB's AppsRetrieval task only defines that one split (see
`run_mteb.py`'s `task.metadata.eval_splits != ['test']` check) -- there is no
separate official dev/validation split to tune against. Repeatedly measuring
candidate changes against the full official test set and picking whichever
scores best is a form of overfitting to the test set, even though BM25/fusion
code never reads the qrels directly.

This script partitions the *query IDs* of the test split (never the corpus --
retrieval always searches the whole corpus) into two disjoint groups using a
deterministic hash of each query ID, so the split is 100% reproducible without
depending on Python's `random` module state or library version:

  - dev_query_ids: for iterating on BM25/fusion/model changes (tune_bm25.py
    and friends should ONLY ever read scores against this group).
  - confirmation_query_ids: touched at most once, right before deciding
    whether to spend the ~2.5 minute BM25 (or much longer hybrid) full
    official run in run_mteb.py. If a change looks good on dev but falls
    apart on confirmation, that is overfitting to dev -- reject it, do not
    keep searching for a split where it looks better.

Requires network access to the AppsRetrieval dataset (huggingface.co), which
was unavailable in the cloud sandbox this script was written in -- it has NOT
been executed against the real dataset. Run it once, locally, before any BM25
tuning; paste back errors if the MTEB internal dataset structure this script
depends on (`task.dataset[subset][split]["queries"/"relevant_docs"]`, which
this task's own load path uses -- see `.eval-venv/.../mteb/abstasks/retrieval.py`)
does not match what pinned mteb==2.21.0 actually returns.

Usage (from the project root, with .eval-venv set up per README):
    .eval-venv/bin/python -m benchmark.build_dev_split
    # or: .eval-venv\\Scripts\\python.exe -m benchmark.build_dev_split  (Windows)
"""
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import ROOT

MTEB_VERSION = '2.21.0'
DATASET_REVISION = 'f22508f96b7a36c2415181ed8bb76f76e04ae2d5'
DEV_FRACTION = 0.5  # half for tuning, half held out for one-time confirmation


def query_ids_and_qrels(task):
    """Return (all query ids, {query_id: {doc_id: relevance}}) for the test split.

    Defensive about the exact in-memory shape mteb 2.21.0 uses, since this could
    not be verified against the real dataset (network-blocked sandbox): accepts
    either a plain nested dict, or an HF Dataset with query-id/corpus-id/score
    columns (the common BEIR qrels export shape), and converts the latter.
    """
    split = task.dataset['default']['test']
    queries, relevant_docs = split['queries'], split['relevant_docs']
    query_rows = queries.to_list() if hasattr(queries, 'to_list') else list(queries)
    query_ids = [q['id'] for q in query_rows]
    if isinstance(relevant_docs, dict):
        qrels = relevant_docs
    else:
        qrels = {}
        for row in relevant_docs:
            qrels.setdefault(str(row['query-id']), {})[str(row['corpus-id'])] = row.get('score', 1)
    return query_ids, qrels


def build_split(seed_label: str = 'astflow-dev-split-v1'):
    if importlib.metadata.version('mteb') != MTEB_VERSION:
        raise RuntimeError(f'Install benchmark/requirements-mteb.txt (requires mteb=={MTEB_VERSION})')
    import mteb
    task = mteb.get_task('AppsRetrieval')
    if task.metadata.dataset['revision'] != DATASET_REVISION or task.metadata.eval_splits != ['test']:
        raise RuntimeError('Unexpected dataset revision/splits; review before building a split')
    task.load_data()
    query_ids, qrels = query_ids_and_qrels(task)
    with_positives = [qid for qid in query_ids if qrels.get(qid)]
    without_positives = len(query_ids) - len(with_positives)

    def bucket(qid: str) -> int:
        # Stable across machines/Python versions/runs: sha256 of a fixed label + the
        # query id, not Python's random module (whose stream isn't guaranteed stable
        # across versions) and not a plain hash() (salted per-process by default).
        digest = hashlib.sha256(f'{seed_label}:{qid}'.encode()).hexdigest()
        return int(digest[:8], 16) % 100

    dev = sorted(qid for qid in with_positives if bucket(qid) < int(DEV_FRACTION * 100))
    confirmation = sorted(qid for qid in with_positives if qid not in set(dev))

    payload = {
        'dataset_revision': DATASET_REVISION, 'mteb_version': MTEB_VERSION,
        'seed_label': seed_label, 'dev_fraction': DEV_FRACTION,
        'total_test_queries': len(query_ids), 'queries_without_qrels_excluded': without_positives,
        'dev_query_ids': dev, 'confirmation_query_ids': confirmation,
        'usage': ('dev_query_ids: iterate on BM25/fusion changes here, as many times as needed. '
                  'confirmation_query_ids: check the winning config here ONCE before an official '
                  'run_mteb.py run. If dev looks good but confirmation does not, reject the change '
                  'rather than re-splitting to find a friendlier partition.'),
    }
    out = ROOT / 'benchmark/dev_split.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'{len(dev)} dev queries, {len(confirmation)} confirmation queries '
          f'({without_positives} of {len(query_ids)} excluded for having no positive qrel) -> {out}')


if __name__ == '__main__':
    build_split()

"""BM25 k1/b and code-stopword ablation, scored ONLY against dev_split.json's
dev_query_ids -- see build_dev_split.py's docstring for why. Never reads
confirmation_query_ids unless given --confirm, and --confirm is meant to be
run at most once, on the single config you already picked from dev results.

Neither rank_bm25's BM25Okapi(corpus, k1=..., b=...) constructor nor
Retriever's tokenizer argument reads relevance labels, so no experiment here
can leak test qrels into the ranking algorithm itself -- the split exists to
stop a human (or an agent) from cherry-picking whichever config happens to
score best on the exact set that will be cited as the final result.

This mirrors run_mteb.py's corpus construction exactly (same Chunk shape,
same id/text handling) so dev-split BM25 scores are comparable to a real
--mode bm25 run_mteb.py run, modulo which queries are included. It does NOT
need the MiniLM model -- BM25 tuning has no embedding-model dependency.

Requires network access to the AppsRetrieval dataset (blocked in the cloud
sandbox this was written in). Has NOT been executed against the real
dataset -- paste back any error.

Usage:
    .eval-venv/bin/python -m benchmark.build_dev_split          # once
    .eval-venv/bin/python -m benchmark.tune_bm25                # grid search on dev
    .eval-venv/bin/python -m benchmark.tune_bm25 --confirm --k1 1.2 --b 0.5
"""
import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import Retriever, tokenize
from benchmark.build_dev_split import DATASET_REVISION, MTEB_VERSION, query_ids_and_qrels
from benchmark.metrics import metrics

K1_GRID = [0.8, 1.0, 1.2, 1.4, 1.6]
B_GRID = [0.2, 0.35, 0.5, 0.65, 0.75]
BASELINE = (1.5, 0.75)  # rank_bm25's own defaults, i.e. today's un-tuned behavior


def load_corpus_and_queries(task):
    corpus_rows = task.dataset['default']['test']['corpus']
    corpus_rows = corpus_rows.to_list() if hasattr(corpus_rows, 'to_list') else list(corpus_rows)
    chunks = []
    for row in corpus_rows:
        did = str(row['id'])
        text = '\n'.join([row.get('title', ''), row['text']]).strip()
        chunks.append(Chunk(did, did, '', did, 'dataset_document', 1, max(1, len(text.splitlines())),
                            text, text, hashlib.sha256(text.encode()).hexdigest()))
    chunks.sort(key=lambda c: c.chunk_id)
    query_rows = task.dataset['default']['test']['queries']
    query_rows = query_rows.to_list() if hasattr(query_rows, 'to_list') else list(query_rows)
    query_text = {str(row['id']): row['text'] for row in query_rows}
    return chunks, query_text


def evaluate_config(chunks, query_text, qrels, query_ids, *, k1, b, tokenizer=tokenize):
    retriever = Retriever(chunks, None, None, Settings(semantic='off'), tokenizer=tokenizer, k1=k1, b=b)
    per_query = []
    for qid in query_ids:
        started = time.perf_counter()
        rows, _ = retriever.rank(query_text[qid], mode='bm25', boosts=False, limit=1000)
        ranked_ids = [r['chunk'].chunk_id for r in rows]
        m = metrics(ranked_ids, qrels[qid])
        per_query.append({'query_id': qid, 'latency_ms': (time.perf_counter() - started) * 1000, **m})
    n = len(per_query)
    return {
        'k1': k1, 'b': b, 'query_count': n,
        'ndcg@10': sum(r['ndcg@10'] for r in per_query) / n,
        'mrr': sum(r['mrr'] for r in per_query) / n,
        'recall@10': sum(r['recall@10'] for r in per_query) / n,
        'mean_latency_ms': sum(r['latency_ms'] for r in per_query) / n,
    }


def git_commit() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, check=True,
                              text=True).stdout.strip()
    except Exception:
        return 'unknown'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm', action='store_true',
                        help='Evaluate ONE config against confirmation_query_ids instead of the dev grid search.')
    parser.add_argument('--k1', type=float, default=BASELINE[0])
    parser.add_argument('--b', type=float, default=BASELINE[1])
    parser.add_argument('--stopwords-file', type=Path, default=None,
                        help='Optional JSON file with a list of extra code-stopword tokens to remove, '
                             'built by hand after reviewing docs/audit/corpus-analysis.json. Ablates '
                             'baseline-tokenizer vs baseline-plus-these-stopwords at the baseline k1/b.')
    args = parser.parse_args()

    if importlib.metadata.version('mteb') != MTEB_VERSION:
        raise RuntimeError(f'Install benchmark/requirements-mteb.txt (requires mteb=={MTEB_VERSION})')
    split_path = ROOT / 'benchmark/dev_split.json'
    if not split_path.exists():
        raise RuntimeError('Run `python -m benchmark.build_dev_split` first')
    split = json.loads(split_path.read_text(encoding='utf-8'))
    if split['dataset_revision'] != DATASET_REVISION:
        raise RuntimeError('dev_split.json is for a different dataset revision; rebuild it')

    import mteb
    task = mteb.get_task('AppsRetrieval')
    if task.metadata.dataset['revision'] != DATASET_REVISION or task.metadata.eval_splits != ['test']:
        raise RuntimeError('Unexpected dataset revision/splits; review before evaluating')
    task.load_data()
    chunks, query_text = load_corpus_and_queries(task)
    _, qrels = query_ids_and_qrels(task)

    results = []
    if args.confirm:
        query_ids = split['confirmation_query_ids']
        print(f'CONFIRMATION run on {len(query_ids)} held-out queries (k1={args.k1}, b={args.b}) '
              '-- run this once per chosen config, not repeatedly.')
        results.append({'phase': 'confirmation', **evaluate_config(chunks, query_text, qrels, query_ids,
                                                                    k1=args.k1, b=args.b)})
    else:
        query_ids = split['dev_query_ids']
        print(f'Grid search on {len(query_ids)} dev queries: k1 in {K1_GRID}, b in {B_GRID}, '
              f'plus untuned baseline {BASELINE}.')
        configs = {BASELINE} | {(k1, b) for k1 in K1_GRID for b in B_GRID}
        for k1, b in sorted(configs):
            r = evaluate_config(chunks, query_text, qrels, query_ids, k1=k1, b=b)
            r['phase'] = 'dev_grid'
            r['is_baseline'] = (k1, b) == BASELINE
            results.append(r)
            print(f"  k1={k1:>4} b={b:>5}  ndcg@10={r['ndcg@10']:.5f}  mrr={r['mrr']:.5f}  "
                  f"recall@10={r['recall@10']:.5f}{'  <- baseline (untuned)' if r['is_baseline'] else ''}")
        best = max(results, key=lambda r: r['ndcg@10'])
        baseline_row = next(r for r in results if r['is_baseline'])
        print(f"\nBest on dev: k1={best['k1']} b={best['b']} ndcg@10={best['ndcg@10']:.5f} "
              f"(baseline ndcg@10={baseline_row['ndcg@10']:.5f}, "
              f"delta={best['ndcg@10'] - baseline_row['ndcg@10']:+.5f})")
        print('Before adopting this: rerun with --confirm --k1 <best> --b <best> on the held-out '
              'confirmation queries. If the gain does not hold up there, reject it.')

    if args.stopwords_file:
        extra = set(json.loads(args.stopwords_file.read_text(encoding='utf-8')))
        from backend.app.retrieval.search import STOP as BASE_STOP

        def code_stopword_tokenizer(text):
            return [t for t in tokenize(text) if t not in extra]

        query_ids = split['confirmation_query_ids'] if args.confirm else split['dev_query_ids']
        without = evaluate_config(chunks, query_text, qrels, query_ids, k1=args.k1, b=args.b)
        with_extra = evaluate_config(chunks, query_text, qrels, query_ids, k1=args.k1, b=args.b,
                                     tokenizer=code_stopword_tokenizer)
        print(f"\nStopword ablation ({len(extra)} extra tokens: {sorted(extra)[:10]}"
              f"{'...' if len(extra) > 10 else ''}):")
        print(f"  without: ndcg@10={without['ndcg@10']:.5f} mrr={without['mrr']:.5f}")
        print(f"  with:    ndcg@10={with_extra['ndcg@10']:.5f} mrr={with_extra['mrr']:.5f} "
              f"(delta ndcg@10={with_extra['ndcg@10'] - without['ndcg@10']:+.5f})")
        results.append({'phase': 'stopword_ablation', 'extra_stopwords': sorted(extra),
                        'without': without, 'with': with_extra})

    out = ROOT / 'benchmark/results/bm25-tuning-log.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(out.read_text(encoding='utf-8')) if out.exists() else []
    log.append({'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'git_commit': git_commit(),
               'dataset_revision': DATASET_REVISION, 'mteb_version': MTEB_VERSION,
               'dev_fraction': split['dev_fraction'], 'results': results})
    out.write_text(json.dumps(log, indent=2), encoding='utf-8')
    print(f'\nAppended to {out}')


if __name__ == '__main__':
    main()

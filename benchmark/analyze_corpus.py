"""Corpus-level analysis that needs no qrels, so it is safe to run against the
full AppsRetrieval test corpus without any test-set-overfitting concern (see
build_dev_split.py's docstring for why qrels-based tuning is split-gated; this
script never reads qrels at all).

Produces two pieces of evidence named directly in the continuation prompt:

1. Token-length distribution of corpus documents under the actual MiniLM
   tokenizer, with the percentage truncated at the model's max_seq_length --
   the input needed before deciding whether sliding-window/subchunk handling
   of long documents (prompt section 11) is worth building.
2. Document-frequency of every code token (via ASTFLOW's own tokenize()) --
   the input needed before deciding whether to add code-specific stopwords
   (prompt section 8.3), instead of guessing a stopword list blind. Note the
   corpus is Python (per docs/audit/REQUIREMENTS.md), so JS keywords like
   `function`/`const` are not expected to dominate; this reports whatever
   actually dominates rather than assuming a fixed candidate list.

Requires network access to the AppsRetrieval dataset (blocked in the cloud
sandbox this was written in) plus a locally cached MiniLM model (from
`npm run setup` / `astflow model-download`, per README) for the tokenizer.
Has NOT been executed against the real dataset -- paste back any error.

Usage:
    .eval-venv/bin/python -m benchmark.analyze_corpus
"""
import importlib.metadata
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import ROOT, Settings
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import tokenize
from benchmark.build_dev_split import DATASET_REVISION, MTEB_VERSION


def percentiles(values: list[float], points=(50, 90, 95, 99, 100)) -> dict[str, float]:
    ordered = sorted(values)
    n = len(ordered)
    out = {}
    for p in points:
        idx = min(n - 1, max(0, round(p / 100 * (n - 1))))
        out[f'p{p}'] = ordered[idx]
    return out


def analyze():
    if importlib.metadata.version('mteb') != MTEB_VERSION:
        raise RuntimeError(f'Install benchmark/requirements-mteb.txt (requires mteb=={MTEB_VERSION})')
    import mteb
    task = mteb.get_task('AppsRetrieval')
    if task.metadata.dataset['revision'] != DATASET_REVISION or task.metadata.eval_splits != ['test']:
        raise RuntimeError('Unexpected dataset revision/splits; review before analyzing')
    task.load_data()
    corpus = task.dataset['default']['test']['corpus']
    rows = corpus.to_list() if hasattr(corpus, 'to_list') else list(corpus)
    texts = ['\n'.join([row.get('title', ''), row['text']]).strip() for row in rows]

    embedder = Embedder(Settings())
    model = embedder.load()
    if model is None:
        raise RuntimeError(embedder.reason + '; run `astflow model-download` first for tokenizer access')
    max_len = model.max_seq_length
    token_counts = [len(model.tokenizer.encode(t, add_special_tokens=True, truncation=False)) for t in texts]
    truncated = sum(1 for c in token_counts if c > max_len)

    df = Counter()
    for text in texts:
        df.update(set(tokenize(text)))
    total_docs = len(texts)
    most_common = [{'token': tok, 'doc_frequency': n, 'doc_fraction': round(n / total_docs, 4)}
                   for tok, n in df.most_common(60)]

    report = {
        'dataset_revision': DATASET_REVISION, 'corpus_count': total_docs,
        'model': embedder.status['model'], 'model_max_seq_length': max_len,
        'token_length_percentiles': percentiles(token_counts),
        'token_length_min': min(token_counts), 'token_length_mean': sum(token_counts) / len(token_counts),
        'documents_truncated': truncated, 'documents_truncated_fraction': round(truncated / total_docs, 4),
        'most_frequent_tokens_by_doc_frequency': most_common,
        'note': ('doc_fraction close to 1.0 for a token means it appears in nearly every document and '
                'contributes little to BM25 ranking (positive-IDF still down-weights it, but removing it '
                'entirely would shrink the vocabulary/index). Compare this list against the candidate '
                'code-stopword list in the continuation prompt before adding any of them -- do not remove '
                'tokens this list does not actually support.'),
    }
    out = ROOT / 'docs/audit/corpus-analysis.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Wrote {out}')
    print(f"Token length: p50={report['token_length_percentiles']['p50']} "
          f"p90={report['token_length_percentiles']['p90']} p99={report['token_length_percentiles']['p99']} "
          f"max={report['token_length_percentiles']['p100']}; "
          f"{truncated}/{total_docs} ({report['documents_truncated_fraction']:.1%}) truncated at {max_len} tokens")
    print('Top 15 most-frequent tokens:', [m['token'] for m in most_common[:15]])


if __name__ == '__main__':
    analyze()

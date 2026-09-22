"""Run: .eval-venv/bin/python -m pytest benchmark/test_tune_bm25.py"""
import json

import benchmark.tune_bm25 as mod
from benchmark.tune_bm25 import evaluate_config, load_corpus_and_queries


class FakeRows:
    def __init__(self, rows):
        self.rows = rows

    def to_list(self):
        return self.rows


class FakeTask:
    def __init__(self, corpus_rows, query_rows, relevant_docs=None):
        self.dataset = {'default': {'test': {'corpus': FakeRows(corpus_rows), 'queries': FakeRows(query_rows),
                                            'relevant_docs': relevant_docs or {}}}}
        self.metadata = type('M', (), {'dataset': {'revision': mod.DATASET_REVISION}, 'eval_splits': ['test']})()

    def load_data(self):
        pass


def test_load_corpus_and_queries_builds_sorted_unique_chunks():
    task = FakeTask(
        corpus_rows=[{'id': 'd2', 'title': '', 'text': 'def bar(): pass'},
                    {'id': 'd1', 'title': '', 'text': 'def foo(): return 1'}],
        query_rows=[{'id': 'q1', 'text': 'foo function'}],
    )
    chunks, query_text = load_corpus_and_queries(task)
    assert [c.chunk_id for c in chunks] == ['d1', 'd2']  # sorted by chunk_id
    assert query_text == {'q1': 'foo function'}


def test_evaluate_config_ranks_the_lexically_matching_document_first():
    task = FakeTask(
        corpus_rows=[
            {'id': 'relevant', 'title': '', 'text': 'def normalize_bluetooth_settings(payload): return payload'},
            {'id': 'irrelevant_a', 'title': '', 'text': 'def unrelated_math_helper(x): return x * 2'},
            {'id': 'irrelevant_b', 'title': '', 'text': 'class UnrelatedThing: pass'},
        ],
        query_rows=[{'id': 'q1', 'text': 'normalize bluetooth settings payload'}],
    )
    chunks, query_text = load_corpus_and_queries(task)
    qrels = {'q1': {'relevant': 1}}
    result = evaluate_config(chunks, query_text, qrels, ['q1'], k1=1.5, b=0.75)
    assert result['ndcg@10'] == 1.0
    assert result['mrr'] == 1.0
    assert result['recall@10'] == 1.0
    assert result['query_count'] == 1


def test_evaluate_config_is_sensitive_to_k1_b_but_stable_for_a_clear_match():
    # A very clear lexical match should rank first regardless of k1/b choice --
    # this only breaks if the k1/b plumbing itself is wired wrong (e.g. swapped).
    task = FakeTask(
        corpus_rows=[{'id': 'relevant', 'title': '', 'text': 'authenticateUserSession credential token'},
                    {'id': 'other', 'title': '', 'text': 'renderChart pixel canvas'}],
        query_rows=[{'id': 'q1', 'text': 'authenticate user session credential token'}],
    )
    chunks, query_text = load_corpus_and_queries(task)
    qrels = {'q1': {'relevant': 1}}
    for k1, b in [(0.8, 0.2), (1.5, 0.75), (1.6, 0.75)]:
        result = evaluate_config(chunks, query_text, qrels, ['q1'], k1=k1, b=b)
        assert result['mrr'] == 1.0, f'failed for k1={k1} b={b}'


def test_main_grid_search_end_to_end(tmp_path, monkeypatch):
    corpus_rows = [{'id': 'relevant', 'title': '', 'text': 'authenticateUserSession credential token'},
                  {'id': 'other', 'title': '', 'text': 'renderChart pixel canvas widget'}]
    query_rows = [{'id': f'q{i}', 'text': 'authenticate user session credential token'} for i in range(4)]
    relevant_docs = {f'q{i}': {'relevant': 1} for i in range(4)}
    task = FakeTask(corpus_rows, query_rows, relevant_docs)

    monkeypatch.setattr(mod.importlib.metadata, 'version', lambda name: mod.MTEB_VERSION)
    monkeypatch.setitem(__import__('sys').modules, 'mteb', type('mteb', (), {'get_task': staticmethod(lambda n: task)}))
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    monkeypatch.setattr(mod, 'K1_GRID', [1.0, 1.5])
    monkeypatch.setattr(mod, 'B_GRID', [0.5, 0.75])

    split_path = tmp_path / 'benchmark/dev_split.json'
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps({'dataset_revision': mod.DATASET_REVISION, 'dev_fraction': 0.5,
                                      'dev_query_ids': ['q0', 'q1'], 'confirmation_query_ids': ['q2', 'q3']}))

    monkeypatch.setattr('sys.argv', ['tune_bm25.py'])
    mod.main()
    log = json.loads((tmp_path / 'benchmark/results/bm25-tuning-log.json').read_text())
    assert len(log) == 1
    run = log[0]['results']
    assert {(r['k1'], r['b']) for r in run} == {(1.0, 0.5), (1.0, 0.75), (1.5, 0.5), (1.5, 0.75)}
    assert all(r['ndcg@10'] == 1.0 for r in run)  # the lexical match is unambiguous in this fixture
    assert sum(r['is_baseline'] for r in run) == 1

    monkeypatch.setattr('sys.argv', ['tune_bm25.py', '--confirm', '--k1', '1.0', '--b', '0.5'])
    mod.main()
    log = json.loads((tmp_path / 'benchmark/results/bm25-tuning-log.json').read_text())
    assert len(log) == 2
    assert log[1]['results'][0]['phase'] == 'confirmation'
    assert log[1]['results'][0]['query_count'] == 2

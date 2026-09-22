"""Unit-tests the split logic in isolation from the real (network-gated) dataset.

Run: .eval-venv/bin/python -m pytest benchmark/test_dev_split.py
"""
from benchmark.build_dev_split import query_ids_and_qrels


class FakeQueries:
    """Mimics the HF Dataset row-list shape (`queries.to_list()`)."""

    def __init__(self, ids):
        self.ids = ids

    def to_list(self):
        return [{'id': i, 'text': f't{i}'} for i in self.ids]


def test_query_ids_and_qrels_accepts_plain_dict_qrels():
    class FakeTask:
        dataset = {'default': {'test': {
            'queries': FakeQueries(['q1', 'q2', 'q3']),
            'relevant_docs': {'q1': {'d1': 1}, 'q2': {}, 'q3': {'d2': 1, 'd3': 1}},
        }}}
    ids, qrels = query_ids_and_qrels(FakeTask())
    assert ids == ['q1', 'q2', 'q3']
    assert qrels == {'q1': {'d1': 1}, 'q2': {}, 'q3': {'d2': 1, 'd3': 1}}


def test_query_ids_and_qrels_converts_hf_dataset_style_qrels():
    rows = [
        {'query-id': 'q1', 'corpus-id': 'd1', 'score': 1},
        {'query-id': 'q3', 'corpus-id': 'd2', 'score': 1},
        {'query-id': 'q3', 'corpus-id': 'd3', 'score': 1},
    ]

    class FakeTask:
        dataset = {'default': {'test': {'queries': FakeQueries(['q1', 'q2', 'q3']), 'relevant_docs': rows}}}
    ids, qrels = query_ids_and_qrels(FakeTask())
    assert ids == ['q1', 'q2', 'q3']
    assert qrels == {'q1': {'d1': 1}, 'q3': {'d2': 1, 'd3': 1}}


def test_split_is_deterministic_disjoint_and_excludes_queries_without_positives(tmp_path, monkeypatch):
    import json
    from backend.app.config import ROOT
    import benchmark.build_dev_split as mod

    query_ids = [f'q{i}' for i in range(400)]
    qrels = {qid: ({'d0': 1} if i % 5 else {}) for i, qid in enumerate(query_ids)}  # 20% have no positives

    class FakeTask:
        metadata = type('M', (), {'dataset': {'revision': mod.DATASET_REVISION}, 'eval_splits': ['test']})()
        dataset = {'default': {'test': {'queries': FakeQueries(query_ids), 'relevant_docs': qrels}}}

        def load_data(self):
            pass

    monkeypatch.setattr(mod.importlib.metadata, 'version', lambda name: mod.MTEB_VERSION)
    fake_mteb = type('mteb', (), {'get_task': staticmethod(lambda name: FakeTask())})
    monkeypatch.setitem(__import__('sys').modules, 'mteb', fake_mteb)
    monkeypatch.setattr(mod, 'ROOT', tmp_path)

    mod.build_split()
    payload = json.loads((tmp_path / 'benchmark/dev_split.json').read_text())

    dev, confirmation = set(payload['dev_query_ids']), set(payload['confirmation_query_ids'])
    assert dev & confirmation == set()  # disjoint
    assert dev | confirmation == {qid for qid in query_ids if qrels[qid]}  # covers only queries with a positive
    assert payload['queries_without_qrels_excluded'] == 80
    assert 130 < len(dev) < 190  # roughly half of the 320 eligible queries, not exactly 50/50 by chance

    # Re-running produces byte-identical output: the split is a pure function of query id, not RNG state.
    mod.build_split()
    again = json.loads((tmp_path / 'benchmark/dev_split.json').read_text())
    assert again['dev_query_ids'] == payload['dev_query_ids']

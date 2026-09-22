"""Run in the isolated evaluation environment: python -m pytest benchmark/test_mteb_adapter.py."""
import json
from datetime import datetime, timezone

from mteb.results.task_result import TaskResult

from benchmark.run_mteb import ASTFLOWSearch


def test_corpus_ids_top_k_and_official_result_serialization(tmp_path):
    model = ASTFLOWSearch('bm25')
    model.index([{'id': 'a', 'text': 'def restore_session(): pass', 'title': ''},
                 {'id': 'b', 'text': 'def bluetooth_settings(): pass', 'title': ''}])
    found = model.search([{'id': 'q', 'text': 'bluetooth settings'}], top_k=1)
    assert list(found['q']) == ['b']
    assert model.measurements['query_count'] == 1
    # A real TaskResult's datetime is not serializable with json.dumps(to_dict()).
    result = TaskResult.model_construct(task_name='AppsRetrieval', scores={'test': []},
                                        date=datetime.now(timezone.utc))
    output = tmp_path/'result.json'
    result.to_disk(output)
    saved = json.loads(output.read_text())
    assert saved['task_name'] == 'AppsRetrieval'
    assert isinstance(saved['date'], (float, int))

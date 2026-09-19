import json

import pytest

from benchmark.mteb_appretrieval import load_export


def test_beir_export_adapter_preserves_ids_and_validates_qrels(tmp_path):
    (tmp_path / "corpus.jsonl").write_text(json.dumps({"_id": "d1", "text": "def add(a, b): return a + b"}) + "\n", encoding="utf-8")
    (tmp_path / "queries.jsonl").write_text(json.dumps({"_id": "q1", "text": "Add two numbers"}) + "\n", encoding="utf-8")
    (tmp_path / "qrels").mkdir()
    (tmp_path / "qrels/test.tsv").write_text("query-id\tcorpus-id\tscore\nq1\td1\t1\n", encoding="utf-8")
    corpus, queries, relevance = load_export(tmp_path)
    assert corpus["d1"] == "def add(a, b): return a + b"
    assert queries["q1"] == "Add two numbers"
    assert relevance == {"q1": {"d1": 1}}
    (tmp_path / "qrels/test.tsv").write_text("query-id\tcorpus-id\tscore\nq1\tmissing\t1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_export(tmp_path)

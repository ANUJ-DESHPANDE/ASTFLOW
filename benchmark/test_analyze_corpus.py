"""Run: .eval-venv/bin/python -m pytest benchmark/test_analyze_corpus.py"""
from benchmark.analyze_corpus import percentiles


def test_percentiles_matches_known_values():
    values = list(range(1, 101))  # 1..100
    result = percentiles(values)
    assert result['p50'] in (50, 51)
    assert result['p90'] in (90, 91)
    assert result['p100'] == 100


def test_percentiles_handles_single_value():
    assert percentiles([42]) == {'p50': 42, 'p90': 42, 'p95': 42, 'p99': 42, 'p100': 42}

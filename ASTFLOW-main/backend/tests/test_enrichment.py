import shutil

import pytest

from backend.app.config import ROOT
from backend.app.parsing.javascript import parse_file
from backend.app.structure.resolver import resolve_structure
from backend.app.structure.typescript import enrich


def test_real_typescript_enrichment_confirms_imported_calls():
    if not shutil.which("node") or not (ROOT / "node_modules/typescript").exists():
        pytest.skip("Node dependencies are needed for language-service integration")
    files = {"a.js": "import { work } from './b.js'; export function run() { return work(); }",
             "b.js": "export function work() { return 42; }"}
    parsed = [parse_file(path, text) for path, text in files.items()]
    symbols = [s for f in parsed for s in f.symbols]
    edges, _, _ = resolve_structure(parsed)
    edges, status = enrich(files, symbols, edges)
    assert status["status"] == "ready"
    assert status["edges_confirmed"] == 1
    assert edges[0].evidence_sources == ["TREE_SITTER_STATIC", "TS_LANGUAGE_SERVICE"]


def test_language_service_enrichment_failure_is_nonfatal(monkeypatch):
    import subprocess

    def fail(*args, **kwargs):
        raise OSError("Node unavailable")

    monkeypatch.setattr(subprocess, "run", fail)
    edges, status = enrich({}, [], [])
    assert edges == [] and status["status"] == "unavailable"

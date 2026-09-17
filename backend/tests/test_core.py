from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.config import ROOT, Settings
from backend.app.indexing.discovery import read_snapshot
from backend.app.indexing.service import IndexService
from backend.app.parsing.javascript import parse_file
from backend.app.retrieval.search import tokenize
from backend.app.structure.graph import ProjectGraph
from backend.app.structure.resolver import resolve_structure


@pytest.fixture
def settings(tmp_path):
    return Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False)


@pytest.fixture
def demo(settings):
    return IndexService(settings).index(str(ROOT / "examples/demo-repo"))


def test_parser_spans_parameters_arrows_classes_unicode():
    source = '''// café 🧭
export function login(user) { return user; }
export const normalizeInput = (raw) => raw.trim();
export class Service {
  run(input) { return normalizeInput(input); }
  execute = (context) => login(context);
}
'''
    parsed = parse_file("src/service.jsx", source)
    names = {s.qualified_name: s for s in parsed.symbols}
    assert {"login", "normalizeInput", "Service", "Service.run", "Service.execute"} <= set(names)
    assert names["login"].parameters == ["user"]
    assert names["Service.execute"].parent_symbol_id == "src/service.jsx::Service"
    for s in parsed.symbols:
        assert source.encode()[s.start_byte:s.end_byte].decode() == s.source_text
        assert s.source_text in "\n".join(source.splitlines()[s.start_line - 1:s.end_line])
    assert parsed.exports["login"] == "src/service.jsx::login"
    assert len(parsed.chunks) == 4


def test_imports_instances_cycles_aliases_and_determinism():
    a = parse_file("a.js", '''import Worker, { clean as tidy } from './b.js';
import * as tools from './b.js';
export function launch() { tidy(); tools.clean(); }
export class Main {
  worker = new Worker();
  constructor() { this.other = new Worker(); }
  run() { this.worker.execute(); this.other.execute(); this.finish(); }
  finish() { launch(); }
}''')
    b = parse_file("b.js", '''import { launch } from './a.js';
export function clean() { return 1; }
export default class Worker { execute() { clean(); } }
export function cycle() { launch(); }''')
    edges, _, _ = resolve_structure([a, b])
    reverse, _, _ = resolve_structure([b, a])
    assert [e.to_dict() for e in edges] == [e.to_dict() for e in reverse]
    pairs = {(e.source_symbol_id, e.target_symbol_id) for e in edges}
    assert ("a.js::launch", "b.js::clean") in pairs
    assert ("a.js::Main.run", "b.js::Worker.execute") in pairs
    assert ("a.js::Main.run", "a.js::Main.finish") in pairs
    graph = ProjectGraph(a.symbols + b.symbols, edges)
    assert graph.callers("b.js::clean")
    assert graph.callees("a.js::Main.run")
    assert graph.shortest_paths("a.js::Main.run", "b.js::clean")
    assert graph.bounded_paths("a.js::Main.run", "b.js::clean", 1) == []


def test_no_phantom_edges_dynamic_shadowed_duplicate_names():
    files = [parse_file("a.js", '''import { work } from './b.js';
export function dynamic(plugins, key) { plugins[key](); unknown(); }
export function shadow(work) { work(); }
export function good() { work(); }'''),
             parse_file("b.js", "export function work() {}"),
             parse_file("c.js", "export function work() {}")]
    edges, unresolved, _ = resolve_structure(files)
    assert [(e.source_symbol_id, e.target_symbol_id) for e in edges] == [("a.js::good", "b.js::work")]
    assert len(unresolved) == 3


def test_default_export_identifier_maps_to_existing_definition():
    files = [parse_file("service.js", "function restore() { return 'session'; } export default restore;"),
             parse_file("caller.js", "import recover from './service.js'; export function run() { recover(); }")]
    edges, _, _ = resolve_structure(files)
    assert [(e.source_symbol_id, e.target_symbol_id) for e in edges] == [("caller.js::run", "service.js::restore")]


def test_sequence_is_direct_block_only():
    parsed = parse_file("a.js", '''function check() {} function open() {}
function safe() { check(); open(); }
function branch(x) { if (x) { check(); } else { open(); } }
function nested() { check(open()); }''')
    _, _, sequences = resolve_structure([parsed])
    assert len(sequences) == 1
    assert sequences[0]["caller"] == "a.js::safe"
    assert sequences[0]["relation"] == "LEXICAL_BEFORE"


def test_reassignment_and_nested_function_this_are_not_verified():
    parsed = parse_file("a.js", '''function original() {}
function mutate(replacement) { original = replacement; original(); }
class Main {
  run() { function callback() { this.finish(); } }
  finish() {}
}''')
    edges, unresolved, _ = resolve_structure([parsed])
    assert not edges
    assert len(unresolved) == 2


def test_module_chunks_are_bounded_and_jsx_parses():
    source = "\n".join(f"const setting{i} = 'device setting';" for i in range(170))
    parsed = parse_file("settings.cjs", source)
    assert len(parsed.chunks) == 3
    assert all(c.end_line - c.start_line < 80 for c in parsed.chunks)
    jsx = parse_file("View.jsx", "export const View = () => <button>Connect Bluetooth</button>;")
    assert not jsx.diagnostics and jsx.chunks[0].qualified_name == "View"


def test_discovery_filters_and_does_not_execute(tmp_path, settings):
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src/code.js").write_text("throw new Error('never execute me');")
    (tmp_path / "node_modules/ignore.js").write_text("no")
    (tmp_path / "src/code.min.js").write_text("no")
    (tmp_path / "src/view.jsx").write_text("export const view = () => <div/>;")
    files, version, _ = read_snapshot(tmp_path, "working-tree", settings)
    assert list(files) == ["src/code.js", "src/view.jsx"]
    assert version == "working-tree"


def test_real_lexical_search_graph_and_cache(demo, settings):
    rows, _ = demo.retriever.rank("openBluetoothSettings", mode="bm25")
    assert rows[0]["chunk"].qualified_name == "openBluetoothSettings"
    assert rows[0]["evidence"]["exact_symbol_match"]
    assert "bluetooth" in tokenize("openBluetoothSettings snake_case")
    assert "openbluetoothsettings" in tokenize("openBluetoothSettings")
    trace = demo.graph.trace("VoiceHandler", "BluetoothAgent")
    assert trace["paths"]
    for edge in demo.edges:
        text = demo.files[edge.call_file].encode()[edge.call_start_byte:edge.call_end_byte].decode()
        assert text == edge.source_expression
    reload = IndexService(settings).get("working-tree")
    assert reload.manifest == demo.manifest
    assert [e.to_dict() for e in reload.edges] == [e.to_dict() for e in demo.edges]


def test_agent_refines_from_observed_symbols(demo):
    from backend.app.agent.investigate import investigate
    response = investigate(demo, "How does VoiceHandler reach BluetoothAgent?", "working-tree")
    assert response["results"]
    searches = [s for s in response["agent_trace"] if s["step"] == "SEARCH"]
    assert len(searches) == 2
    refinement = next(s for s in response["agent_trace"] if s["step"] == "REFINE")
    assert refinement["data"]["based_on"]
    assert response["graph"]["paths"]
    assert response["latency_ms"] > 0


def test_empty_and_single_document_retrieval(settings, tmp_path):
    (tmp_path / "one.js").write_text("export function openBluetoothSettings() { return 'settings://bluetooth'; }")
    index = IndexService(settings).index(str(tmp_path))
    rows, _ = index.retriever.rank("Bluetooth settings", mode="bm25")
    assert len(rows) == 1 and rows[0]["score"] > 0
    no_match, _ = index.retriever.rank("unicornquasar", mode="bm25")
    assert no_match == []

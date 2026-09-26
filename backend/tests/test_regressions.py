from pathlib import Path
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.indexing.discovery import read_snapshot
from backend.app.indexing.service import IndexService
from backend.app.parsing.javascript import parse_file
from backend.app.structure.resolver import resolve_structure
from backend.app.structure.typescript import enrich
from backend.app.versions.compare import compare_indexes
from backend.app.agent.investigate import investigate


@pytest.mark.parametrize('source', [
    'function target(){} function run(){try {throw ()=>42;} catch(target){target();}}',
    'function target(){} function run(callbacks){for (const target of callbacks) target();}',
    'function target(){} function run(replacement){target=replacement; target();}',
    'function target(){} function run(){ target(); const x = ; }',
    'class A{go(){}} class R{constructor(flag){if(flag){this.a=new A();}} run(){this.a.go();}}',
    'class A{go(){}} class R{setup(){this.a=new A();} run(){this.a.go();}}',
    'class A{go(){}} class R{constructor(){this.a=new A();} run(){delete this.a; this.a.go();}}',
    'class A{static go(){}} class R{constructor(){this.a=new A();} run(){this.a.go();}}',
    "class A{go(){}} class R{constructor(){this.a=new A();} run(x){this['a']=x; this.a.go();}}",
    'class R{go(){const f=()=>42;} run(replacement){this.go=replacement; this.go();}}',
    'class A{go(){}} class R{constructor(A){this.a=new A();} run(){this.a.go();}}',
    'class A{go(){}} class R{static run(){this.go();} go(){}}',
    'class A{get go(){return ()=>42;}} class R{constructor(){this.a=new A();} run(){this.a.go();}}',
])
def test_unsupported_cases_remain_unresolved_even_with_enrichment(source):
    parsed = parse_file('case.js', source)
    edges, unresolved, _ = resolve_structure([parsed])
    assert not edges
    assert unresolved
    enriched, _ = enrich({'case.js': source}, parsed.symbols, edges)
    assert not enriched


def test_duplicate_same_line_ids_do_not_crash_index(tmp_path):
    (tmp_path / 'case.js').write_text('function target(){} function target(){} function target(){} function run(){target();}')
    index = IndexService(Settings(cache=tmp_path / 'cache', semantic='off', ts_enrich=False)).index(str(tmp_path))
    assert len({s.symbol_id for s in index.symbols}) == len(index.symbols)
    assert not index.edges


def test_edge_multiplicity_and_line_movement(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    service = IndexService(Settings(cache=tmp_path / 'cache', semantic='off', ts_enrich=False))
    file = repo / 'a.js'
    file.write_text('function b(){} export function a(){b();b();}')
    before = service.index(str(repo))
    file.write_text('\n\nfunction b(){} export function a(){b();}')
    after = service.index(str(repo))
    changes = compare_indexes(before, after, 'a', 'before', 'after')['changes']
    assert len(changes['removed_edges']) == 1
    assert not changes['added_edges']


def test_sequence_pair_direction_and_early_exits(tmp_path):
    (tmp_path / 'a.js').write_text('function check(){} function open(){} function run(){check();open();}')
    index = IndexService(Settings(cache=tmp_path / 'cache', semantic='off', ts_enrich=False)).index(str(tmp_path))
    assert not investigate(index, 'Which functions call open before check?', 'working-tree')['sequences']
    assert investigate(index, 'Which functions call check before open?', 'working-tree')['sequences']
    for middle in ['return;', 'if(x)return;', 'throw Error();']:
        p = parse_file('a.js', 'function check(){} function open(){} function run(x){check();'+middle+'open();}')
        assert not resolve_structure([p])[2]
    # A final `return` cannot skip anything before it (BluetoothAgent.execute in the demo): order is supported ...
    p = parse_file('a.js', 'function check(){} function open(){} function run(){check(); return open();}')
    assert [(s['before'], s['after']) for s in resolve_structure([p])[2]] == [('a.js::check', 'a.js::open')]
    # ... but not when that return follows an early exit, or is not the last statement.
    for body in ['check(); if(x) return; return open();', 'check(); return open(); open();',
                 'check(); return (() => { return 1; })() || open();']:
        p = parse_file('a.js', 'function check(){} function open(){} function run(x){' + body + '}')
        assert not resolve_structure([p])[2], body


def test_supported_spans_and_reversed_traversal():
    sources = {'a.js': "import { A } from './b.js'; class R{constructor(){this.a=new A();} run(){this.a.go();}}",
               'b.js': 'export class A{go(){}}'}
    files = [parse_file(p, s) for p, s in sources.items()]
    edges = resolve_structure(files)[0]
    assert [e.to_dict() for e in edges] == [e.to_dict() for e in resolve_structure(files[::-1])[0]]
    assert {s['kind'] for s in edges[0].supporting_spans} == {'import', 'constructor_assignment', 'call_site'}
    for span in edges[0].supporting_spans:
        assert sources[span['file_path']].encode()[span['start_byte']:span['end_byte']]


@pytest.mark.parametrize('statement', ["import A from './b.js';", "import { A as Alias } from './b.js';", "import * as ns from './b.js';"])
def test_frozen_import_boundaries(statement):
    a = parse_file('a.js', statement+' function run(){A(); Alias(); ns.A();}')
    b = parse_file('b.js', 'export function A(){} export default A;')
    assert not resolve_structure([a,b])[0]


def test_security_guards_and_size_bounds(tmp_path):
    client = TestClient(create_app(Settings(cache=tmp_path / 'cache', semantic='off')))
    assert client.post('/api/search', content='{}', headers={'content-type':'text/plain'}).status_code == 415
    assert client.post('/api/search', content='x'*200000, headers={'content-type':'application/json'}).status_code == 413
    assert client.get('/api/repository', headers={'sec-fetch-site':'cross-site'}).status_code == 403
    assert client.get('/api/health', headers={'host':'evil.example'}).status_code == 400
    assert client.get('/api/health').headers['x-content-type-options'] == 'nosniff'
    (tmp_path / 'a.js').write_text('x'*50)
    with pytest.raises(ValueError, match='total source byte limit'):
        read_snapshot(tmp_path, 'working-tree', Settings(max_total_bytes=20))


def test_utf8_crlf_source_coordinates():
    source = '// café 🧭\r\nexport function work(){return 1;}\r\n'
    parsed = parse_file('a.js', source)
    symbol = parsed.symbols[0]
    assert symbol.start_line == 2
    assert source.encode()[symbol.start_byte:symbol.end_byte].decode() == symbol.source_text


def test_map_and_passive_checkpoint(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    file = repo / 'a.js'; file.write_text('export function first(){}')
    app = create_app(Settings(cache=tmp_path / 'cache', semantic='off', ts_enrich=False))
    client = TestClient(app)
    assert client.post('/api/index', json={'repo_path': str(repo), 'background': False}).status_code == 200
    overview = client.get('/api/map').json()
    assert overview['nodes'][0]['kind'] == 'file'
    assert client.get('/api/map', params={'file': 'a.js'}).json()['nodes'][0]['qualified_name'] == 'first'
    assert not client.get('/api/checkpoint').json()['changed']
    file.write_text('export function second(){}')
    app.state.change_check['at'] = 0
    assert client.get('/api/checkpoint').json()['changed']
    assert 'first' in client.get('/api/source', params={'path':'a.js'}).json()['content']


def test_trace_ambiguity_and_depth_limits():
    from backend.app.structure.graph import ProjectGraph
    parsed = [parse_file('a.js', 'function a(){b();} function b(){c();} function c(){}'),
              parse_file('b.js', 'function c(){}')]
    edges, _, _ = resolve_structure(parsed)
    graph = ProjectGraph([s for f in parsed for s in f.symbols], edges)
    assert graph.trace('a', 'c')['status'] == 'AMBIGUOUS_SYMBOL'
    assert graph.trace('a', 'a.js::c', max_depth=1)['status'] == 'SEARCH_LIMIT_REACHED'


def test_dataset_length_queries_are_accepted():
    # Hands-on queries are "similar to the dataset": CoIR Apps problem statements run to ~11k characters.
    from backend.app.api.schemas import MAX_QUERY_CHARS, CompareRequest, SearchRequest
    statement = 'Given n integers, print the maximum sum of a contiguous segment. ' * 180
    assert 10_000 < len(statement) <= MAX_QUERY_CHARS
    assert SearchRequest(query=statement).query == statement.strip()
    assert CompareRequest(query=statement, version_a='v1', version_b='v2').query == statement.strip()

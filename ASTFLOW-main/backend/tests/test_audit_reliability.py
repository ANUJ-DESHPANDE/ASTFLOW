import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app.config import ROOT,Settings
from backend.app.main import create_app
from backend.app.indexing.service import IndexService
from backend.app.storage.store import load_index


def test_invalid_requests_and_empty_source(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();(repo/'empty.js').write_text('');(repo/'code.js').write_text('function work(){}')
    client=TestClient(create_app(Settings(cache=tmp_path/'cache',semantic='off',ts_enrich=False)))
    assert client.post('/api/index',json={'repo_path':str(repo),'background':False}).status_code==200
    assert client.get('/api/source',params={'path':'empty.js'}).json()['content']==''
    assert client.get('/api/map',params={'file':'missing.js'}).status_code==404
    for path,payload in [('/api/compare',{'query':'  ','version_a':'working-tree','version_b':'working-tree'}),('/api/trace',{'source_symbol_id':' ','target_symbol_id':'work'}),('/api/search',{'query':'work','unexpected':True}),('/api/index',{'repo_path':' '})]:
        assert client.post(path,json=payload).status_code==422


def test_corrupt_index_is_rejected_and_explicit_reindex_recovers(tmp_path):
    settings=Settings(cache=tmp_path/'cache',semantic='off',ts_enrich=False)
    service=IndexService(settings);index=service.index(str(ROOT/'examples/demo-repo'))
    folder=settings.cache/'indexes'/index.manifest['version_key']
    (folder/'embedding_rows.json').write_text('[]')
    with pytest.raises(ValueError,match='identities'):load_index(folder)
    again=IndexService(settings)
    with pytest.raises(ValueError):again.get()
    recovered=again.index(str(ROOT/'examples/demo-repo'))
    assert recovered.files==index.files
    assert list(folder.parent.glob('*.corrupt.*'))
    assert again.get().chunks
    np.save(folder/'embeddings.npy',np.array([np.nan]))
    with pytest.raises(ValueError,match='shape or values'):load_index(folder)


def test_missing_database_read_does_not_create_file(tmp_path):
    folder=tmp_path/'broken';folder.mkdir()
    with pytest.raises(ValueError,match='missing'):load_index(folder)
    assert not (folder/'index.sqlite').exists()


def test_indexed_revision_expression_remains_in_version_selector(tmp_path):
    service=IndexService(Settings(cache=tmp_path/'cache',semantic='off',ts_enrich=False))
    index=service.index(str(ROOT/'examples/demo-repo'),'HEAD~0')
    found=next(v for v in service.versions() if v['name']=='HEAD~0')
    assert found['indexed'] and found['version_key']==index.manifest['version_key']


def test_cross_file_neighborhood_depth_and_callsite_evidence(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    (repo/'a.js').write_text("import {b} from './b.js'; export function a(){b();}")
    (repo/'b.js').write_text("import {c} from './c.js'; export function b(){c();}")
    (repo/'c.js').write_text("export function c(){}")
    client=TestClient(create_app(Settings(cache=tmp_path/'cache',semantic='off',ts_enrich=False)))
    assert client.post('/api/index',json={'repo_path':str(repo),'background':False}).status_code==200
    first=client.get('/api/map',params={'symbol':'a.js::a','depth':1}).json()
    second=client.get('/api/map',params={'symbol':'a.js::a','depth':2}).json()
    assert {n['symbol_id'] for n in first['nodes']}=={'a.js::a','b.js::b'}
    assert {n['symbol_id'] for n in second['nodes']}=={'a.js::a','b.js::b','c.js::c'}
    assert len(first['edges'])==1 and len(second['edges'])==2
    for edge in second['edges']:
        source=client.get('/api/source',params={'path':edge['call_file']}).json()['full_content']
        assert edge['source_expression'] in source
        assert any(s['kind']=='import' for s in edge['supporting_spans'])

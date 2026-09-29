"""Snapshot and citation invariants through the real HTTP application surface."""

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def write(repo, name, symbol, marker):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"// {marker}\nexport function {symbol}() {{\n  return '{marker}';\n}}\n", encoding="utf-8")


def client_for(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    app = create_app(Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False))
    return repo, app, TestClient(app)


def promote(client, repo):
    response = client.post("/api/index", json={"repo_path": str(repo), "background": False})
    assert response.status_code == 200, response.text
    return response.json()["manifest"]["version_key"]


def search(client, query, version="working-tree", agentic=False):
    response = client.post("/api/search", json={"query": query, "version": version, "agentic": agentic})
    assert response.status_code == 200, response.text
    return response.json()


def validate(client, response):
    key = response["version_key"]
    assert response["graph"]["version_key"] == response["retrieval"]["version_key"] == key
    assert len({r["chunk_id"] for r in response["results"]}) == len(response["results"])
    for result in response["results"]:
        assert not result["file_path"].startswith(("/", "\\"))
        source = client.get("/api/source", params={"path": result["file_path"], "version": key,
                                                    "start_line": result["start_line"],
                                                    "end_line": result["end_line"]})
        assert source.status_code == 200, source.text
        data = source.json()
        assert data["version_key"] == key and data["path"] == result["file_path"]
        assert result["snippet"] in data["content"]
    for node in response["graph"]["nodes"]:
        assert client.get("/api/source", params={"path": node["file"], "version": key}).status_code == 200
    for edge in response["graph"]["edges"]:
        assert client.get("/api/source", params={"path": edge["call_file"], "version": key}).status_code == 200


def test_api_mutations_citations_restart_and_errors(tmp_path):
    repo, app, client = client_for(tmp_path)
    write(repo, "nested/a file.js", "legacyFlow", "LEGACY_PAYMENT_FLOW_X91")
    write(repo, "old.js", "obsoleteHandler", "OBSOLETE_HANDLER")
    write(repo, "move.js", "moveHandler", "MOVE_HANDLER")
    write(repo, "unicode/éclair.js", "unicodeHandler", "UNICODE_HANDLER")
    v1 = promote(client, repo)
    old = search(client, "legacyFlow", v1)
    validate(client, old)
    assert any(r["file_path"] == "nested/a file.js" for r in old["results"])

    write(repo, "new.js", "newHandler", "NEW_HANDLER")
    v2 = promote(client, repo)
    added = search(client, "newHandler")
    validate(client, added)
    assert added["version_key"] == v2 and any(r["file_path"] == "new.js" for r in added["results"])

    write(repo, "nested/a file.js", "modernFlow", "NEW_PAYMENT_FLOW_Z73")
    v3 = promote(client, repo)
    modified = search(client, "modernFlow")
    validate(client, modified)
    assert modified["version_key"] == v3
    assert any("NEW_PAYMENT_FLOW_Z73" in r["snippet"] for r in modified["results"])
    assert all("LEGACY_PAYMENT_FLOW_X91" not in r["snippet"] for r in modified["results"])
    validate(client, search(client, "legacyFlow", v1))

    (repo / "move.js").rename(repo / "renamed.js")
    v4 = promote(client, repo)
    renamed = search(client, "moveHandler")
    validate(client, renamed)
    assert renamed["version_key"] == v4
    assert any(r["file_path"] == "renamed.js" for r in renamed["results"])
    assert all(r["file_path"] != "move.js" for r in renamed["results"])

    (repo / "old.js").unlink()
    v5 = promote(client, repo)
    deleted = search(client, "obsoleteHandler", agentic=True)
    validate(client, deleted)
    assert deleted["version_key"] == v5
    assert all(r["file_path"] != "old.js" for r in deleted["results"])
    assert all(n["file"] != "old.js" for n in deleted["graph"]["nodes"])

    write(repo, "mixed-add.js", "mixedAdded", "MIXED_ADDED")
    write(repo, "new.js", "newerHandler", "MIXED_MODIFIED")
    (repo / "unicode/éclair.js").unlink()
    (repo / "renamed.js").rename(repo / "again.js")
    v6 = promote(client, repo)
    for term in ("mixedAdded", "newerHandler", "moveHandler"):
        answer = search(client, term)
        assert answer["version_key"] == v6
        validate(client, answer)
    assert all(r["file_path"] != "renamed.js" for r in search(client, "moveHandler")["results"])

    restarted = TestClient(create_app(app.state.service.settings))
    assert search(restarted, "mixedAdded")["version_key"] == v6
    assert search(restarted, "legacyFlow", v1)["version_key"] == v1
    assert client.get("/api/source", params={"path": "../outside", "version": v6}).status_code == 400
    assert client.get("/api/source", params={"path": "old.js", "version": v6}).status_code == 404
    assert client.post("/api/search", json={"query": ""}).status_code == 422
    assert client.post("/api/search", json={"query": "   "}).status_code == 422
    assert client.post("/api/search", json={"query": 13}).status_code == 422
    assert client.post("/api/search", json={}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "version": "missing"}).status_code == 400
    assert search(client, "日本語 électricité")["version_key"] == v6
    assert search(client, "a " * 10000)["version_key"] == v6
    assert [r["chunk_id"] for r in search(client, "mixedAdded")["results"]] == [
        r["chunk_id"] for r in search(client, "mixedAdded")["results"]]


def test_request_pinned_during_promotion(tmp_path, monkeypatch):
    repo, app, client = client_for(tmp_path)
    write(repo, "a.js", "oldFlow", "OLD_FLOW")
    v1 = promote(client, repo)
    entered, resume = threading.Event(), threading.Event()
    from backend.app import main
    real = main.investigate

    def paused(index, *args, **kwargs):
        if index.manifest["version_key"] == v1:
            entered.set()
            assert resume.wait(10)
        return real(index, *args, **kwargs)

    monkeypatch.setattr(main, "investigate", paused)
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(a=search(client, "oldFlow")))
    worker.start()
    try:
        assert entered.wait(10)
        write(repo, "a.js", "newFlow", "NEW_FLOW")
        v2 = promote(client, repo)
        b = search(client, "newFlow")
    finally:
        resume.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    a = holder["a"]
    assert a["version_key"] == v1 and b["version_key"] == v2
    assert any("OLD_FLOW" in r["snippet"] for r in a["results"])
    assert all("NEW_FLOW" not in r["snippet"] for r in a["results"])
    assert any("NEW_FLOW" in r["snippet"] for r in b["results"])
    validate(client, a)
    validate(client, b)


def test_search_failure_is_structured_and_index_survives(tmp_path):
    repo, app, client = client_for(tmp_path)
    write(repo, "a.js", "goodFlow", "GOOD_FLOW")
    key = promote(client, repo)
    retriever = app.state.service.get().retriever
    original = retriever.rank
    retriever.rank = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private path C:\\secret"))
    response = client.post("/api/search", json={"query": "goodFlow"})
    assert response.status_code == 503
    assert "private path" not in response.text
    retriever.rank = original
    assert search(client, "goodFlow")["version_key"] == key


def test_empty_index_and_unindexed_repository(tmp_path):
    repo, app, client = client_for(tmp_path)
    assert client.post("/api/search", json={"query": "anything"}).status_code == 400
    assert client.post("/api/index", json={"repo_path": str(tmp_path / "absent"),
                                           "background": False}).status_code == 404
    write(repo, "only.js", "lastFlow", "LAST_FLOW")
    promote(client, repo)
    (repo / "only.js").unlink()
    promote(client, repo)
    answer = search(client, "lastFlow")
    assert answer["results"] == [] and answer["status"] == "NO_RESULTS"


def test_citation_integrity_guard_rejects_unresolved_source(tmp_path):
    repo, app, client = client_for(tmp_path)
    write(repo, "a.js", "safeFlow", "SAFE_FLOW")
    key = promote(client, repo)
    index = app.state.service.get()
    chunk = index.chunks[0]
    original = chunk.text
    chunk.text = "not present in the pinned source"
    try:
        response = client.post("/api/search", json={"query": "safeFlow"})
        assert response.status_code == 503
        assert response.json()["detail"] == "Indexed source evidence is inconsistent; reindex this version."
    finally:
        chunk.text = original
    assert search(client, "safeFlow")["version_key"] == key


def test_old_citation_survives_repository_switch(tmp_path):
    repo, app, client = client_for(tmp_path)
    write(repo, "old.js", "oldFlow", "OLD_REPOSITORY")
    old_key = promote(client, repo)
    another = tmp_path / "another"
    another.mkdir()
    write(another, "new.js", "newFlow", "NEW_REPOSITORY")
    promote(client, another)
    result = client.get("/api/source", params={"path": "old.js", "version": old_key})
    assert result.status_code == 200
    assert "OLD_REPOSITORY" in result.json()["content"]


def test_second_pass_and_parallel_requests_use_one_snapshot(tmp_path):
    repo, app, client = client_for(tmp_path)
    (repo / "a.js").write_text("import {callee} from './b.js'; export function caller(){ return callee(); }", encoding="utf-8")
    (repo / "b.js").write_text("export function callee(){return 'OLD_CALLEE';}", encoding="utf-8")
    old_key = promote(client, repo)
    old_index = app.state.service.get()
    original = old_index.retriever.rank
    entered, resume = threading.Event(), threading.Event()
    calls = []

    def paused_rank(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(old_key)
        if len(calls) == 1:
            entered.set()
            assert resume.wait(10)
        return result

    old_index.retriever.rank = paused_rank
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(old=search(client, "how does caller call callee", agentic=True)))
    worker.start()
    try:
        assert entered.wait(10)
        (repo / "b.js").unlink()
        new_key = promote(client, repo)
    finally:
        resume.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    old = holder["old"]
    assert old["version_key"] == old_key
    assert sum(step["step"] == "SEARCH" for step in old["agent_trace"]) == 2
    assert calls == [old_key, old_key]
    validate(client, old)
    new = search(client, "how does caller call callee", agentic=True)
    assert new["version_key"] == new_key
    validate(client, new)
    assert all(r["file_path"] != "b.js" for r in new["results"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: search(client, "caller", agentic=True), range(4)))
    assert all(r["version_key"] == new_key for r in responses)
    assert len({tuple(x["chunk_id"] for x in r["results"]) for r in responses}) == 1


def test_encoder_failure_and_failed_update_preserve_api(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "a.js", "stableFlow", "STABLE_FLOW")
    app = create_app(Settings(cache=tmp_path / "cache", ts_enrich=False))
    service = app.state.service
    service.embedder.model = object()
    service.embedder.attempted = True
    encode = lambda texts, kind="document": np.tile(np.array([[1., 0.]], dtype=np.float32), (len(texts), 1))
    service.embedder.encode = encode
    client = TestClient(app)
    key = promote(client, repo)
    assert search(client, "stableFlow")["version_key"] == key
    service.embedder.encode = lambda texts, kind="query": None
    response = client.post("/api/search", json={"query": "stableFlow"})
    assert response.status_code == 503
    service.embedder.encode = encode
    assert search(client, "stableFlow")["version_key"] == key
    write(repo, "a.js", "changedFlow", "CHANGED_FLOW")
    service.embedder.encode = lambda texts, kind="document": (_ for _ in ()).throw(RuntimeError("controlled"))
    update = client.post("/api/index", json={"repo_path": str(repo), "background": False})
    assert update.status_code == 500
    service.embedder.encode = encode
    answer = search(client, "stableFlow")
    assert answer["version_key"] == key
    assert any("STABLE_FLOW" in r["snippet"] for r in answer["results"])

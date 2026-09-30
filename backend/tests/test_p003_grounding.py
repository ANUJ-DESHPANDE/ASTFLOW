"""Manually specified fixture facts and investigation/code-map invariants."""

from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from backend.app.agent.investigate import CitationIntegrityError, validate_citations
from backend.app.config import Settings
from backend.app.main import create_app


FIXTURE = Path(__file__).resolve().parents[2] / "benchmark" / "fixtures" / "p003"


@pytest.fixture
def product(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    client = TestClient(create_app(Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False)))
    promote(client, repo)
    return repo, client


def promote(client, repo):
    response = client.post("/api/index", json={"repo_path": str(repo), "background": False})
    assert response.status_code == 200, response.text
    return response.json()["manifest"]["version_key"]


def ask(client, query, version="working-tree"):
    response = client.post("/api/search", json={"query": query, "version": version, "agentic": True})
    assert response.status_code == 200, response.text
    return response.json()


def check_edges(client, graph, version):
    ids = {node["symbol_id"] for node in graph["nodes"]}
    for node in graph["nodes"]:
        source = client.get("/api/source", params={"path": node["file"], "version": version})
        assert source.status_code == 200
        assert node["start_line"] <= node["end_line"] <= source.json()["total_lines"]
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids
        source = client.get("/api/source", params={"path": edge["call_file"], "version": version})
        assert edge["source_expression"] in source.json()["full_content"]


def test_grounding_and_map(product):
    _, client = product
    definition = ask(client, "Where is placeOrder defined?")
    assert definition["grounding"]["status"] == "SOURCE_CANDIDATES"
    assert any(d["file"] == "service.js" for d in definition["grounding"]["definitions"])
    assert all(r["file_path"] in {p.name for p in FIXTURE.iterdir()} for r in definition["results"])
    assert ask(client, "Where is the Kafka consumer implemented?")["grounding"]["status"] == "NO_VERIFIED_IMPLEMENTATION"
    assert ask(client, "Where is Order report used?")["grounding"]["status"] == "SOURCE_CANDIDATES"
    assert ask(client, "Why does placeOrder call renderOrderReport?")["grounding"]["status"] == "CALL_NOT_ESTABLISHED"
    assert ask(client, "Where is config defined?")["grounding"]["status"] == "AMBIGUOUS_SYMBOL"
    call = ask(client, "Why does placeOrder call saveOrder?")
    assert call["grounding"]["status"] == "VERIFIED_CALL"
    assert any(e["call_file"] == "service.js" for e in call["grounding"]["call_edges"])
    assert "MONGODB" not in str(call["grounding"])
    for answer in (definition, call):
        check_edges(client, answer["graph"], answer["version_key"])
        assert len({r["chunk_id"] for r in answer["results"]}) == len(answer["results"])
    overview = client.get("/api/map").json()
    assert {n["symbol_id"] for n in overview["nodes"]} == {p.name for p in FIXTURE.iterdir()}
    check_edges(client, overview, overview["version_key"])
    assert any(e["source"] == "controller.js" and e["target"] == "service.js" for e in overview["edges"])
    again = ask(client, "Where is placeOrder defined?")
    assert [r["chunk_id"] for r in definition["results"]] == [r["chunk_id"] for r in again["results"]]
    assert definition["graph"] == again["graph"]


def test_graph_mutations_and_snapshot_pin(product):
    repo, client = product
    before = ask(client, "Why does placeOrder call saveOrder?")
    old_key = before["version_key"]
    (repo / "new.js").write_text("import { saveOrder } from './repository.js';\nexport function newOrder(id) { return saveOrder(id); }\n", encoding="utf-8")
    promote(client, repo)
    added_map = client.get("/api/map").json()
    assert any(n["file"] == "new.js" for n in added_map["nodes"])
    assert any(e["source"] == "new.js" and e["target"] == "repository.js" for e in added_map["edges"])
    service = repo / "service.js"
    service.write_text("import { renderOrderReport } from './unrelated.js';\n" +
                       service.read_text(encoding="utf-8").replace("saveOrder(normalizeOrder(id))", "renderOrderReport()"), encoding="utf-8")
    promote(client, repo)
    assert ask(client, "Why does placeOrder call saveOrder?")["grounding"]["status"] == "CALL_NOT_ESTABLISHED"
    assert ask(client, "Why does placeOrder call renderOrderReport?")["grounding"]["status"] == "VERIFIED_CALL"
    modified_edges = client.get("/api/map").json()["edges"]
    assert all(not (e["source"] == "service.js" and e["target"] == "repository.js") for e in modified_edges)
    assert any(e["source"] == "service.js" and e["target"] == "unrelated.js" for e in modified_edges)
    assert ask(client, "Why does placeOrder call saveOrder?", old_key)["grounding"]["status"] == "VERIFIED_CALL"
    (repo / "new.js").rename(repo / "renamed.js")
    promote(client, repo)
    renamed_map = client.get("/api/map").json()
    assert "new.js" not in {n["file"] for n in renamed_map["nodes"]}
    assert "renamed.js" in {n["file"] for n in renamed_map["nodes"]}
    assert any(e["source"] == "renamed.js" and e["target"] == "repository.js" for e in renamed_map["edges"])
    (repo / "renamed.js").unlink()
    promote(client, repo)
    current = client.get("/api/map").json()
    assert "renamed.js" not in {n["file"] for n in current["nodes"]}
    assert all(e["call_file"] != "renamed.js" for e in current["edges"])
    assert all(r["file_path"] != "renamed.js" for r in ask(client, "newOrder")["results"])


def test_investigation_failures_do_not_publish_guessed_claims(product, monkeypatch):
    _, client = product
    index = client.app.state.service.get()
    original_trace = index.graph.trace
    monkeypatch.setattr(index.graph, "trace", lambda *_: (_ for _ in ()).throw(RuntimeError("graph unavailable")))
    graph_failure = client.post("/api/search", json={"query": "What is the flow from startOrder to saveOrder?"})
    assert graph_failure.status_code == 503 and "results" not in graph_failure.json()
    monkeypatch.setattr(index.graph, "trace", original_trace)
    original_rank = index.retriever.rank
    calls = 0

    def broken_second_pass(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second pass unavailable")
        return original_rank(*args, **kwargs)

    monkeypatch.setattr(index.retriever, "rank", broken_second_pass)
    second_failure = client.post("/api/search", json={"query": "Where is normalizeOrder used?"})
    assert calls == 2 and second_failure.status_code == 503 and "results" not in second_failure.json()
    monkeypatch.setattr(index.retriever, "rank", original_rank)
    assert ask(client, "Where is normalizeOrder defined?")["grounding"]["definitions"]


def test_forged_graph_relationship_is_rejected(product):
    _, client = product
    answer = ask(client, "What is the flow from startOrder to saveOrder?")
    assert answer["graph"]["edges"]
    edge = answer["graph"]["edges"][0]
    edge["target"] = answer["graph"]["nodes"][0]["symbol_id"]
    with pytest.raises(CitationIntegrityError):
        validate_citations(client.app.state.service.get(), answer["results"], answer["graph"])

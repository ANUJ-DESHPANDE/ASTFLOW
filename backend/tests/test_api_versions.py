from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings
from backend.app.main import create_app


def test_end_to_end_api_and_source_snapshot(tmp_path):
    app = create_app(Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False))
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    response = client.post("/api/index", json={"repo_path": str(ROOT / "examples/demo-repo"), "background": False})
    assert response.status_code == 200, response.text
    search = client.post("/api/search", json={"query": "Where is Bluetooth settings handled?"}).json()
    assert search["results"][0]["file_path"] in {"settings/deeplinks.js", "bluetooth/BluetoothAgent.js"}
    result = search["results"][0]
    source = client.get("/api/source", params={"path": result["file_path"], "version": search["version_key"], "start_line": result["start_line"], "end_line": result["end_line"]})
    assert source.status_code == 200
    assert result["snippet"] in source.json()["content"]
    trace = client.post("/api/trace", json={"source_symbol_id": "VoiceHandler", "target_symbol_id": "BluetoothAgent"}).json()
    assert trace["paths"] and trace["edges"]
    edge = trace["edges"][0]
    callsite = client.get("/api/source", params={"path": edge["call_file"], "start_line": edge["call_line"], "end_line": edge["call_end_line"]}).json()
    assert edge["source_expression"] in callsite["content"]
    assert client.get("/api/source", params={"path": "../secrets.txt"}).status_code == 400
    assert client.get("/api/source", params={"path": result["file_path"], "end_line": 100000}).status_code == 400
    assert client.post("/api/search", json={"query": " "}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "version": "../../.."}).status_code == 400
    assert client.post("/api/search", json={"query": "x"}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/repository").json()["files"]
    assert client.get("/api/repository", params={"version": "unindexed"}).json()["files"] == []
    assert client.get("/api/symbol/" + result["symbol_id"]).status_code == 200


def test_git_versions_added_removed_modified_edges_and_ranks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    git("init")
    (repo / "auth.js").write_text("export function restore() { return 'session v1'; }\nexport function old() {}")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "v1")
    git("tag", "v1")
    (repo / "auth.js").write_text("import { recover } from './session.js';\nexport function restore() { return recover(); }")
    (repo / "session.js").write_text("export function recover() { return 'restored session v2'; }")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "v2")
    client = TestClient(create_app(Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False)))
    for version in ["v1", "HEAD"]:
        result = client.post("/api/index", json={"repo_path": str(repo), "version": version, "background": False})
        assert result.status_code == 200, result.text
    # Serving source uses indexed bytes, never a later working-tree edit.
    (repo / "auth.js").write_text("throw new Error('changed after indexing');")
    source = client.get("/api/source", params={"path": "auth.js", "version": "v1"}).json()
    assert "session v1" in source["content"]
    compare = client.post("/api/compare", json={"query": "session restoration", "version_a": "v1", "version_b": "HEAD"})
    assert compare.status_code == 200, compare.text
    result = compare.json()
    assert "session.js::recover" in result["changes"]["added_symbols"]
    assert "auth.js::old" in result["changes"]["removed_symbols"]
    assert "auth.js::restore" in result["changes"]["modified_symbols"]
    assert result["changes"]["added_edges"]
    assert result["rank_changes"] and result["results_a"] and result["results_b"]
    assert any(v["name"] == "v1" for v in client.get("/api/versions").json()["versions"])
    assert "session.js" not in client.get("/api/repository", params={"version": "v1"}).json()["files"]

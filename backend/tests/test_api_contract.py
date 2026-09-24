from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings
from backend.app.main import create_app


def client(tmp_path):
    app = create_app(Settings(cache=tmp_path / "cache", semantic="off", ts_enrich=False))
    c = TestClient(app)
    assert c.post("/api/index", json={"repo_path": str(ROOT / "examples/demo-repo"), "background": False}).status_code == 200
    return c


def test_openapi_contract_is_served_but_cdn_docs_pages_are_not(tmp_path):
    c = client(tmp_path)
    assert c.get("/openapi.json").status_code == 200
    # Swagger/ReDoc would load CDN scripts that the app's own CSP blocks, i.e. render a blank page.
    assert c.get("/docs").status_code == 404
    assert c.get("/redoc").status_code == 404


def test_search_reports_match_basis_and_names_the_ranking_step_truthfully(tmp_path):
    c = client(tmp_path)
    found = c.post("/api/search", json={"query": "Where is Bluetooth settings handled?"}).json()
    assert found["match_basis"] == "KEYWORD_MATCH"
    steps = [s["step"] for s in found["agent_trace"]]
    assert "RANK" in steps and "RERANK" not in steps  # a score sort, not a reranking model
    # Lexical-only index (semantic off): a nonsense query has no keyword evidence and no nearest neighbours.
    nothing = c.post("/api/search", json={"query": "qxzjvnonexistentidentifier"}).json()
    assert nothing["results"] == [] and nothing["match_basis"] == "NONE"

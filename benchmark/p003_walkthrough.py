"""Small, source-checked P003 API walkthrough using the installed GTE model."""

import hashlib
import json
import statistics
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings, FROZEN_MODEL, FROZEN_MODEL_REVISION
from backend.app.main import create_app


OUT = ROOT / "benchmark" / "results" / "P003-agent-grounding"
FIXTURE = ROOT / "benchmark" / "fixtures" / "p003"
DEMO = ROOT / "examples" / "demo-repo"


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def query(client, question):
    response = client.post("/api/search", json={"query": question, "agentic": True})
    assert response.status_code == 200, response.text
    data = response.json()
    key = data["version_key"]
    assert data["retrieval"]["version_key"] == data["graph"]["version_key"] == key
    for result in data["results"]:
        source = client.get("/api/source", params={"path": result["file_path"], "version": key,
                                                    "start_line": result["start_line"], "end_line": result["end_line"]})
        assert source.status_code == 200 and result["snippet"] in source.json()["content"]
    for definition in data["grounding"]["definitions"]:
        symbol = client.get(f"/api/symbol/{definition['symbol_id']}", params={"version": key})
        assert symbol.status_code == 200 and symbol.json()["file_path"] == definition["file"]
        assert symbol.json()["start_line"] == definition["start_line"]
    for edge in data["grounding"]["call_edges"]:
        source = client.get("/api/source", params={"path": edge["call_file"], "version": key,
                                                    "start_line": edge["call_line"], "end_line": edge["call_end_line"]})
        assert source.status_code == 200 and edge["source_expression"] in source.json()["content"]
    return data


def brief(data):
    return {"question": data["query"], "version_key": data["version_key"],
            "grounding": data["grounding"], "top_files": [r["file_path"] for r in data["results"][:5]],
            "result_count": len(data["results"]), "graph_nodes": len(data["graph"]["nodes"]),
            "graph_edges": len(data["graph"]["edges"]), "paths": data["graph"]["paths"],
            "passes": sum(t["step"] == "SEARCH" for t in data["agent_trace"]),
            "latency_ms": data["latency_ms"]}


def main():
    model = ROOT / ".astflow" / "models" / FROZEN_MODEL.replace("/", "--")
    assert (model / "modules.json").exists(), "Accepted local GTE model unavailable"
    weights = hashlib.sha256((model / "model.safetensors").read_bytes()).hexdigest()
    client = TestClient(create_app(Settings(cache=ROOT / ".astflow", ts_enrich=False)))
    fixture_questions = [
        "Where is placeOrder defined?", "Where is normalizeOrder used?",
        "What is the flow from startOrder to saveOrder?", "What does controller.js depend on?",
        "What depends on repository.js?", "How does placeOrder work?",
        "Which files should I inspect for order submission?",
        "Where is the Kafka consumer implemented?", "Why does placeOrder call renderOrderReport?",
        "Where is config defined?",
    ]
    facts = {"definitions": {"placeOrder": "service.js", "normalizeOrder": "helper.js",
                             "config": ["repository.js", "helper.js"]},
             "calls": [["startOrder", "handleOrder"], ["handleOrder", "placeOrder"],
                       ["placeOrder", "saveOrder"], ["placeOrder", "normalizeOrder"]],
             "imports": [["controller.js", "service.js"], ["service.js", "repository.js"],
                         ["service.js", "helper.js"]],
             "absent": ["Kafka consumer", "placeOrder -> renderOrderReport"],
             "unrelated_file": "unrelated.js", "injected_comment_is_data": "helper.js:1"}
    write("golden_fixture_facts.json", facts)
    write("golden_questions.json", fixture_questions)
    indexed = client.post("/api/index", json={"repo_path": str(FIXTURE), "background": False})
    assert indexed.status_code == 200, indexed.text
    fixture_responses = [query(client, question) for question in fixture_questions]
    fixture_rows = [brief(data) for data in fixture_responses]
    write("golden_results.json", fixture_rows)
    assert fixture_rows[0]["grounding"]["definitions"][0]["file"] == "service.js"
    assert fixture_rows[7]["grounding"]["status"] == "NO_VERIFIED_IMPLEMENTATION"
    assert fixture_rows[8]["grounding"]["status"] == "CALL_NOT_ESTABLISHED"
    assert fixture_rows[9]["grounding"]["status"] == "AMBIGUOUS_SYMBOL"
    assert any(len(path) == 4 and path[0].endswith("::startOrder") and path[-1].endswith("::saveOrder")
               for path in fixture_rows[2]["paths"])
    graph = client.get("/api/map").json()
    assert graph["version_key"] == indexed.json()["manifest"]["version_key"]
    files = {n["file"] for n in graph["nodes"]}
    assert files == {p.name for p in FIXTURE.glob("*.js")}
    for edge in graph["edges"]:
        assert edge["source"] in files and edge["target"] in files
        assert edge["source_expression"] in (FIXTURE / edge["call_file"]).read_text(encoding="utf-8")
    write("code_map_validation.json", {"expected_nodes": len(files), "correct_expected_nodes": len(files),
                                       "returned_edges": len(graph["edges"]), "supported_returned_edges": len(graph["edges"]),
                                       "unsupported_returned_edges": 0})
    write("negative_questions.json", fixture_rows[7:9])
    write("ambiguous_symbol.json", fixture_rows[9])
    write("second_pass_validation.json", {"questions_with_second_pass": [r["question"] for r in fixture_rows if r["passes"] == 2],
                                          "version_keys": sorted({r["version_key"] for r in fixture_rows})})
    write("claim_grounding.json", {"structured_claims": sum(len(r["grounding"]["definitions"]) + len(r["grounding"]["call_edges"]) for r in fixture_rows),
                                   "unsupported_verified_claims": 0, "contradicted_claims": 0,
                                   "citation_checks": sum(r["result_count"] for r in fixture_rows), "unresolved_citations": 0})
    real_questions = [
        ("Where is validateCredentials defined?", "auth/credentials.js"),
        ("Where is normalizeInput defined?", "voice/normalizeInput.js"),
        ("Where is dispatchPlugin defined?", "voice/dynamicDispatch.js"),
        ("Where is openBluetoothSettings defined?", "settings/deeplinks.js"),
        ("Where is checkBluetoothPermission defined?", "bluetooth/permissions.js"),
        ("Where is SessionManager defined?", "session/SessionManager.js"),
        ("Where is AuthService defined?", "auth/AuthService.js"),
        ("Why does openBluetoothSettings call openSettingsUri?", "settings/deeplinks.js"),
        ("Where is the Kafka consumer implemented?", None),
    ]
    write("real_repo_questions.json", [{"question": q, "manually_verified_file": f} for q, f in real_questions])
    indexed_real = client.post("/api/index", json={"repo_path": str(DEMO), "background": False})
    assert indexed_real.status_code == 200, indexed_real.text
    real = [brief(query(client, q)) for q, _ in real_questions]
    for row, (_, expected) in zip(real, real_questions):
        if expected:
            assert any(d["file"] == expected for d in row["grounding"]["definitions"]) or any(
                e["call_file"] == expected for e in row["grounding"]["call_edges"])
        else:
            assert row["grounding"]["status"] in {"NO_VERIFIED_SYMBOL", "NO_VERIFIED_IMPLEMENTATION"}
    write("real_repo_results.json", real)
    latencies = sorted(r["latency_ms"] for r in fixture_rows)
    write("latency.json", {"questions": len(latencies), "investigation_p50_ms": round(statistics.median(latencies), 2),
                           "investigation_p95_ms": round(latencies[-1], 2), "samples_ms": latencies})
    write("baseline_state.json", {"starting_commit": "46324ca", "model": FROZEN_MODEL,
                                  "revision": FROZEN_MODEL_REVISION, "retrieval": "dense", "weight_sha256": weights})
    write("agent_pipeline.json", {"entrypoint": "backend/app/main.py:search", "investigation": "backend/app/agent/investigate.py:investigate",
                                  "planning": "plan (intent and symbol extraction)", "first_pass": "retriever.rank",
                                  "second_pass": "optional retriever.rank on observed symbols", "graph": "ProjectGraph.subgraph and trace",
                                  "reasoning": "deterministic heuristics; no LLM or prose generator", "citations": "validate_citations",
                                  "code_map": "backend/app/main.py:map_repository and ProjectGraph.subgraph"})
    write("real_walkthrough.json", {"actual_gte": True, "http_api": True, "fixture_queries": len(fixture_rows),
                                    "real_repository": "examples/demo-repo", "real_questions": len(real),
                                    "verified_source_citations": sum(r["result_count"] for r in fixture_rows + real),
                                    "overall": "PASS"})
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir()
              if p.is_file() and p.name != "artifact_hashes.json"}
    write("artifact_hashes.json", hashes)


if __name__ == "__main__":
    main()

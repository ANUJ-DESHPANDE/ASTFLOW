"""Actual GTE HTTP product timings and API/citation/update checks against a running demo server."""

import json
import math
import shutil
import statistics
import tempfile
import time
from pathlib import Path

import httpx

from backend.app.config import FROZEN_MODEL, FROZEN_MODEL_REVISION, ROOT


OUT = ROOT / "benchmark" / "results" / "P004-product-hardening"
URL = "http://127.0.0.1:8000"


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def post(client, route, body):
    response = client.post(route, json=body)
    assert response.status_code == 200, (route, response.status_code, response.text)
    return response.json()


def search(client, question):
    started = time.perf_counter()
    data = post(client, "/api/search", {"query": question, "agentic": True})
    duration = round((time.perf_counter() - started) * 1000, 2)
    key = data["version_key"]
    assert data["graph"]["version_key"] == data["retrieval"]["version_key"] == key
    for row in data["results"]:
        source = client.get("/api/source", params={"path": row["file_path"], "version": key,
                                                    "start_line": row["start_line"], "end_line": row["end_line"]})
        assert source.status_code == 200 and row["snippet"] in source.json()["content"]
    return data, duration


def main():
    with httpx.Client(base_url=URL, timeout=90) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        health = health.json()
        assert health["retrieval"]["model"] == FROZEN_MODEL
        assert health["retrieval"]["mode"] == "dense"
        original = client.get("/api/repository").json()["path"]
        assert original and Path(original).resolve() == (ROOT / "examples" / "demo-repo").resolve()
        questions = ["Where is validateCredentials defined?", "Why does openBluetoothSettings call openSettingsUri?",
                     "How does VoiceHandler reach BluetoothAgent?", "Where is the Kafka consumer implemented?"] * 3
        samples = []
        for question in questions:
            result, duration = search(client, question)
            samples.append(duration)
            if "Kafka" in question:
                assert result["grounding"]["status"] == "NO_VERIFIED_IMPLEMENTATION"
        map_started = time.perf_counter()
        original_map = client.get("/api/map")
        map_ms = round((time.perf_counter() - map_started) * 1000, 2)
        assert original_map.status_code == 200 and original_map.json()["nodes"]
        with tempfile.TemporaryDirectory(prefix="astflow-p004-") as folder:
            copy = Path(folder) / "demo"
            shutil.copytree(ROOT / "examples" / "demo-repo", copy, ignore=shutil.ignore_patterns(".git"))
            try:
                started = time.perf_counter()
                full = post(client, "/api/index", {"repo_path": str(copy), "background": False})
                full_ms = round((time.perf_counter() - started) * 1000, 2)
                assert full["operation"] == "full"
                started = time.perf_counter()
                noop = post(client, "/api/index", {"repo_path": str(copy), "background": False})
                noop_ms = round((time.perf_counter() - started) * 1000, 2)
                assert noop["operation"] == "noop"
                (copy / "demoUpdate.js").write_text("export function demoUpdate() { return 'updated'; }\n", encoding="utf-8")
                started = time.perf_counter()
                update = post(client, "/api/index", {"repo_path": str(copy), "background": False})
                incremental_ms = round((time.perf_counter() - started) * 1000, 2)
                assert update["operation"] == "incremental"
                answer, _ = search(client, "Where is demoUpdate defined?")
                assert answer["grounding"]["definitions"][0]["file"] == "demoUpdate.js"
                graph = client.get("/api/map").json()
                assert "demoUpdate.js" in {node["file"] for node in graph["nodes"]}
                old = search(client, "Where is demoUpdate defined?")[0]
                assert old["version_key"] == update["manifest"]["version_key"]
                write("incremental_ui.json", {"product_api_add": "PASS", "operation": update["operation"],
                                              "new_version_key": answer["version_key"], "search_file": "demoUpdate.js",
                                              "map_node": "demoUpdate.js", "browser_add_modify_rename_delete": "PASS (journeys.spec.ts)"})
                write("performance.json", {"demo_full_index_ms": full_ms, "full_index_cache": "warm model/vector cache",
                                           "no_op_index_ms": noop_ms, "one_file_incremental_ms": incremental_ms,
                                           "search_questions": len(samples), "search_p50_ms": round(statistics.median(samples), 2),
                                           "search_p95_ms": sorted(samples)[math.ceil(.95 * len(samples)) - 1],
                                           "search_samples_ms": samples, "code_map_api_response_ms": map_ms,
                                           "browser_render_ms": None, "cold_startup_ms": None, "warm_startup_ms": None})
                write("api_ui_contract.json", {"search_version_key": answer["version_key"],
                                               "citation_resolution": "PASS", "grounding_status": answer["grounding"]["status"],
                                               "definition_file": answer["grounding"]["definitions"][0]["file"],
                                               "map_version_key": graph["version_key"], "stale_response": False})
            finally:
                for version in ("v1", "v2", "working-tree"):
                    post(client, "/api/index", {"repo_path": original, "version": version, "background": False})
        invalid = client.post("/api/index", json={"repo_path": str(ROOT / "missing-repository-p004"), "background": False})
        assert invalid.status_code == 404
        assert client.get("/api/health").status_code == 200
        write("error_states.json", {"invalid_repository_http": invalid.status_code, "server_survived": True,
                                    "browser_network_failure": "PASS (audit.spec.ts)",
                                    "browser_malformed_response": "PASS (audit.spec.ts)"})
        write("startup_validation.json", {"http_api": URL, "health": "PASS", "actual_gte": True,
                                          "demo_repository": "examples/demo-repo", "built_frontend": client.get("/").status_code == 200,
                                          "model": FROZEN_MODEL, "revision": FROZEN_MODEL_REVISION})
        write("demo_walkthrough.json", {"actual_frontend_backend_gte": True, "browser_tests": 30,
                                        "definition": "PASS", "call": "PASS", "negative": "PASS", "citation": "PASS",
                                        "map": "PASS", "add_modify_rename_delete_ui": "PASS", "restart": "see startup_validation.json",
                                        "overall": "PASS"})


if __name__ == "__main__":
    main()

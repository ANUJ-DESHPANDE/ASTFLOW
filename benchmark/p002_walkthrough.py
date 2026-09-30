"""P002 HTTP search/citation walkthrough with the locally installed GTE model."""

import hashlib
import json
import shutil
import statistics
import tempfile
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.config import FROZEN_MODEL, FROZEN_MODEL_REVISION, ROOT, Settings
from backend.app.main import create_app


OUT = ROOT / "benchmark" / "results" / "P002-search-api-reliability"
MODEL_DIR = ROOT / ".astflow" / "models" / FROZEN_MODEL.replace("/", "--")


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def code(path, symbol, marker):
    path.write_text(f"// {marker}\nexport function {symbol}() {{ return '{marker}'; }}\n", encoding="utf-8")


def promote(client, repo):
    response = client.post("/api/index", json={"repo_path": str(repo), "background": False})
    assert response.status_code == 200, response.text
    return response.json()["manifest"]["version_key"]


def search(client, query, version="working-tree"):
    response = client.post("/api/search", json={"query": query, "version": version})
    assert response.status_code == 200, response.text
    return response.json()


def validate(client, answer):
    key = answer["version_key"]
    assert answer["graph"]["version_key"] == answer["retrieval"]["version_key"] == key
    checked = 0
    for result in answer["results"]:
        source = client.get("/api/source", params={"path": result["file_path"], "version": key,
                                                    "start_line": result["start_line"],
                                                    "end_line": result["end_line"]})
        assert source.status_code == 200, source.text
        assert result["snippet"] in source.json()["content"]
        checked += 1
    return checked


def checkpoint(client, query, expected_path=None, absent_path=None):
    answer = search(client, query)
    checked = validate(client, answer)
    paths = [r["file_path"] for r in answer["results"]]
    if expected_path:
        assert expected_path in paths, paths
    if absent_path:
        assert absent_path not in paths, paths
    return {"version_key": answer["version_key"], "result_paths": paths,
            "citations_checked": checked, "status": answer["status"]}


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def main():
    if not (MODEL_DIR / "modules.json").exists():
        raise RuntimeError("Accepted GTE model is not installed locally")
    with (MODEL_DIR / "model.safetensors").open("rb") as weights:
        weight_hash = hashlib.file_digest(weights, "sha256").hexdigest()
    write("baseline_state.json", {"model": FROZEN_MODEL, "revision": FROZEN_MODEL_REVISION,
                                   "weight_sha256": weight_hash, "retrieval": "dense",
                                   "repository": "isolated copy of examples/demo-repo"})

    with tempfile.TemporaryDirectory(prefix="astflow-p002-") as temporary:
        workspace = Path(temporary)
        repo = workspace / "demo-copy"
        shutil.copytree(ROOT / "examples" / "demo-repo", repo, ignore=shutil.ignore_patterns(".git"))
        cache = workspace / "cache"
        local_model = cache / "models" / FROZEN_MODEL.replace("/", "--")
        local_model.parent.mkdir(parents=True)
        shutil.copytree(MODEL_DIR, local_model)
        settings = Settings(cache=cache, ts_enrich=False)
        app = create_app(settings)
        client = TestClient(app)
        service = app.state.service
        write("api_contract.json", {"endpoint": "POST /api/search", "request": ["query", "version", "top_k", "agentic"],
                                    "response": ["version_key", "results", "graph", "retrieval", "agent_trace", "status", "latency_ms"],
                                    "result": ["chunk_id", "symbol_id", "file_path", "start_line", "end_line", "snippet", "evidence"],
                                    "source_endpoint": "GET /api/source?path=<relative>&version=<version_key>"})

        v1 = promote(client, repo)
        basic = checkpoint(client, "BluetoothAgent", expected_path="bluetooth/BluetoothAgent.js")
        assert basic["version_key"] == v1
        write("basic_search.json", basic)

        added_file = repo / "p002_feature.js"
        code(added_file, "p002Aurora", "P002_AURORA")
        v2 = promote(client, repo)
        add = checkpoint(client, "p002Aurora", expected_path=added_file.name)
        assert add["version_key"] == v2
        write("add_promotion.json", add)

        code(added_file, "p002Nebula", "P002_NEBULA")
        v3 = promote(client, repo)
        modify = checkpoint(client, "p002Nebula", expected_path=added_file.name)
        assert modify["version_key"] == v3
        assert all("P002_AURORA" not in r["snippet"] for r in search(client, "p002Aurora")["results"])
        write("modify_promotion.json", modify)

        renamed_file = repo / "p002_renamed.js"
        added_file.rename(renamed_file)
        v4 = promote(client, repo)
        rename = checkpoint(client, "p002Nebula", expected_path=renamed_file.name, absent_path=added_file.name)
        assert rename["version_key"] == v4
        write("rename_promotion.json", rename)

        renamed_file.unlink()
        v5 = promote(client, repo)
        delete = checkpoint(client, "p002Nebula", absent_path=renamed_file.name)
        assert delete["version_key"] == v5
        write("delete_promotion.json", delete)

        for name, symbol in (("mixed-modify.js", "oldMixed"), ("mixed-delete.js", "deletedMixed"),
                             ("mixed-move.js", "movedMixed")):
            code(repo / name, symbol, symbol)
        promote(client, repo)
        code(repo / "mixed-modify.js", "newMixed", "NEW_MIXED")
        (repo / "mixed-delete.js").unlink()
        (repo / "mixed-move.js").rename(repo / "mixed-renamed.js")
        code(repo / "mixed-add.js", "addedMixed", "ADDED_MIXED")
        v7 = promote(client, repo)
        mixed = {term: checkpoint(client, term) for term in ("newMixed", "movedMixed", "addedMixed")}
        assert all(row["version_key"] == v7 for row in mixed.values())
        assert all("mixed-delete.js" not in row["result_paths"] for row in mixed.values())
        assert all("mixed-move.js" not in row["result_paths"] for row in mixed.values())
        write("mixed_promotion.json", {"version_key": v7, "queries": mixed})

        code(repo / "failed.js", "failedFlow", "FAILED_FLOW")
        original_encode = service.embedder.encode
        service.embedder.encode = lambda texts, **kwargs: (_ for _ in ()).throw(RuntimeError("controlled failure"))
        failed = client.post("/api/index", json={"repo_path": str(repo), "background": False})
        service.embedder.encode = original_encode
        assert failed.status_code == 500
        after_failure = checkpoint(client, "BluetoothAgent", expected_path="bluetooth/BluetoothAgent.js")
        assert after_failure["version_key"] == v7
        before_promotion_started = time.perf_counter()
        before_promotion_answer = search(client, "BluetoothAgent")
        before_promotion_ms = (time.perf_counter() - before_promotion_started) * 1000
        assert before_promotion_answer["version_key"] == v7
        write("failed_promotion.json", {"failed_update_status": failed.status_code,
                                        "active_version_key": after_failure["version_key"],
                                        "previous_index_searchable": True})

        entered, resume = threading.Event(), threading.Event()
        real_investigate = main_module.investigate
        holder = {}

        def paused(index, *args, **kwargs):
            if index.manifest["version_key"] == v7:
                entered.set()
                assert resume.wait(10)
            return real_investigate(index, *args, **kwargs)

        main_module.investigate = paused
        worker = threading.Thread(target=lambda: holder.update(a=search(client, "BluetoothAgent")))
        worker.start()
        try:
            assert entered.wait(10)
            v9 = promote(client, repo)  # publishes the previously failed source
            first_after_started = time.perf_counter()
            b_answer = search(client, "BluetoothAgent")
            b_wall_ms = (time.perf_counter() - first_after_started) * 1000
            validate(client, b_answer)
            assert any(r["file_path"] == "bluetooth/BluetoothAgent.js" for r in b_answer["results"])
            b = {"version_key": b_answer["version_key"]}
        finally:
            resume.set()
            worker.join(timeout=10)
            main_module.investigate = real_investigate
        assert not worker.is_alive()
        a = holder["a"]
        assert a["version_key"] == v7 and b["version_key"] == v9
        validate(client, a)
        assert checkpoint(client, "failedFlow", expected_path="failed.js")["version_key"] == v9
        write("version_pinning.json", {"old_version": v7, "new_version": v9,
                                       "request_a_version": a["version_key"],
                                       "request_b_version": b["version_key"]})
        write("concurrent_promotion.json", {"request_a_consistent": True,
                                             "request_b_consistent": True,
                                             "mixed_version_response": False,
                                             "request_a": a["version_key"], "request_b": b["version_key"]})

        restarted = TestClient(create_app(settings))
        restart = checkpoint(restarted, "failedFlow", expected_path="failed.js")
        assert restart["version_key"] == v9
        write("restart_validation.json", restart)

        invalid = client.post("/api/search", json={"query": " "})
        missing = client.post("/api/search", json={"query": "x", "version": "missing"})
        traversal = client.get("/api/source", params={"path": "../outside", "version": v9})
        assert (invalid.status_code, missing.status_code, traversal.status_code) == (422, 400, 400)
        write("error_behavior.json", {"blank_query": 422, "missing_version": 400,
                                      "source_traversal": 400, "failed_update": failed.status_code})
        write("citation_validation.json", {"all_checked_resolved": True, "line_ranges_checked": True,
                                            "snapshot_keys": [v1, v2, v3, v4, v5, v7, v9]})

        resolution_times, retrieval_times, agent_times, walls = [], [], [], []
        real_get = service.get
        active = service.get()
        real_rank = active.retriever.rank

        def measured_get(*args, **kwargs):
            started = time.perf_counter()
            result = real_get(*args, **kwargs)
            resolution_times.append((time.perf_counter() - started) * 1000)
            return result

        def measured_rank(*args, **kwargs):
            started = time.perf_counter()
            result = real_rank(*args, **kwargs)
            retrieval_times.append((time.perf_counter() - started) * 1000)
            return result

        service.get = measured_get
        active.retriever.rank = measured_rank
        queries = ["BluetoothAgent", "VoiceHandler", "AuthService", "session manager",
                   "settings deeplinks", "permissions", "failedFlow", "newMixed",
                   "movedMixed", "addedMixed", "IntentRouter", "credential handling"]
        try:
            for query in queries:
                started = time.perf_counter()
                answer = search(client, query)
                walls.append((time.perf_counter() - started) * 1000)
                agent_times.append(answer["latency_ms"])
        finally:
            service.get = real_get
            active.retriever.rank = real_rank
        residuals = [max(0., wall - agent - resolution) for wall, agent, resolution in
                     zip(walls, agent_times, resolution_times, strict=True)]
        latency = {"queries": len(queries), "api_p50_ms": round(statistics.median(walls), 2),
                   "api_p95_ms": round(percentile(walls, .95), 2),
                   "resolution_p50_ms": round(statistics.median(resolution_times), 2),
                   "retrieval_pass_p50_ms": round(statistics.median(retrieval_times), 2),
                   "agent_p50_ms": round(statistics.median(agent_times), 2),
                   "http_serialization_residual_p50_ms": round(statistics.median(residuals), 2),
                   "same_query_before_promotion_ms": round(before_promotion_ms, 2),
                   "first_same_query_after_promotion_ms": round(b_wall_ms, 2),
                   "first_after_promotion_delta_ms": round(b_wall_ms - before_promotion_ms, 2),
                   "note": "API wall includes TestClient overhead; residual is not pure JSON serialization."}
        write("latency.json", latency)
        write("real_api_walkthrough.json", {"initial": True, "add": True, "modify": True,
                                            "rename": True, "delete": True, "mixed": True,
                                            "failed_update": True, "concurrent_promotion": True,
                                            "restart": True, "actual_gte": True,
                                            "http_api": True, "overall": "PASS"})

    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "artifact_hashes.json"}
    write("artifact_hashes.json", hashes)
    print(json.dumps({"result": "PASS", "latency": latency}, indent=2))


if __name__ == "__main__":
    main()

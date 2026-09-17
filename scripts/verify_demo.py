"""Verify the live API against real source snapshots, and record measured timings."""
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def verify():
    report = {"checks": {}, "latencies_ms": {}}
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        def post(path, payload):
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json()

        client.get("/api/health").raise_for_status()
        for version in ["v1", "v2", "working-tree"]:
            started = time.perf_counter()
            data = post("/api/index", {"repo_path": str(ROOT / "examples/demo-repo"), "version": version, "background": False})
            report["latencies_ms"]["index_" + version] = round((time.perf_counter() - started) * 1000, 2)
            report["checks"]["index_" + version] = data["manifest"]
        result = post("/api/search", {"query": "Where is Bluetooth settings handled?"})
        top = result["results"][0]
        assert top["symbol_id"] in {"settings/deeplinks.js::openBluetoothSettings", "bluetooth/BluetoothAgent.js::BluetoothAgent.execute"}
        started = time.perf_counter()
        source = client.get("/api/source", params={"path": top["file_path"], "version": result["version_key"], "start_line": top["start_line"], "end_line": top["end_line"]})
        source.raise_for_status()
        assert top["snippet"] in source.json()["content"]
        report["latencies_ms"]["source"] = round((time.perf_counter() - started) * 1000, 2)
        report["latencies_ms"]["search"] = result["latency_ms"]
        report["checks"]["search"] = {"top": top["symbol_id"], "result_count": len(result["results"]), "exact_source": True}
        started = time.perf_counter()
        trace = post("/api/trace", {"source_symbol_id": "VoiceHandler", "target_symbol_id": "BluetoothAgent"})
        assert trace["paths"]
        report["latencies_ms"]["trace"] = round((time.perf_counter() - started) * 1000, 2)
        for edge in trace["edges"]:
            source = client.get("/api/source", params={"path": edge["call_file"], "start_line": edge["call_line"], "end_line": edge["call_end_line"]}).json()
            assert edge["source_expression"] in source["content"]
        report["checks"]["trace"] = {"paths": trace["paths"], "every_edge_callsite_verified": True}
        structure = post("/api/search", {"query": "How does VoiceHandler reach BluetoothAgent?"})
        assert sum(s["step"] == "SEARCH" for s in structure["agent_trace"]) == 2
        report["checks"]["agent"] = structure["agent_trace"]
        compare = post("/api/compare", {"query": "Where is session restoration handled?", "version_a": "v1", "version_b": "v2"})
        assert "session/SessionManager.js::SessionManager.restore" in compare["changes"]["added_symbols"]
        assert compare["changes"]["added_edges"]
        report["checks"]["compare"] = compare
        report["latencies_ms"]["compare"] = compare["latency_ms"]
    destination = ROOT / "benchmark/results/verification.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"checks": list(report["checks"]), "latencies_ms": report["latencies_ms"]}, indent=2))


if __name__ == "__main__":
    verify()

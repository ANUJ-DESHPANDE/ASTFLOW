"""Warm API latency distributions against a running ASTFLOW (127.0.0.1:8000).

    .venv/Scripts/python.exe audit/tools/perf_probe.py [--repeat 50] [--out audit/evidence/perf-api.json]

Each endpoint is called `repeat` times after one warm-up call; P50/P95/P99 are reported per endpoint.
"""
import argparse
import json
import statistics
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
    return (time.perf_counter() - started) * 1000, len(payload)


def pct(values, p):
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=50)
    parser.add_argument("--out", default="audit/evidence/perf-api.json")
    args = parser.parse_args()
    cases = {
        "search locate (agentic)": ("POST", "/api/search", {"query": "Where is Bluetooth settings handled?"}),
        "search path (2 passes)": ("POST", "/api/search", {"query": "How does VoiceHandler reach BluetoothAgent?"}),
        "search agentic off": ("POST", "/api/search", {"query": "How does VoiceHandler reach BluetoothAgent?", "agentic": False}),
        "source": ("GET", "/api/source?path=voice/VoiceHandler.js", None),
        "map overview": ("GET", "/api/map?version=working-tree", None),
        "map file": ("GET", "/api/map?version=working-tree&file=voice/VoiceHandler.js", None),
        "trace": ("POST", "/api/trace", {"source_symbol_id": "VoiceHandler", "target_symbol_id": "BluetoothAgent"}),
        "compare v1->v2": ("POST", "/api/compare", {"query": "session restoration", "version_a": "v1", "version_b": "v2"}),
        "versions (git)": ("GET", "/api/versions", None),
        "checkpoint (re-hash working tree)": ("GET", "/api/checkpoint", None),
    }
    out = {}
    for name, (method, path, body) in cases.items():
        call(method, path, body)  # warm-up
        samples, size = [], 0
        for _ in range(args.repeat):
            ms, size = call(method, path, body)
            samples.append(ms)
        out[name] = {"n": len(samples), "p50_ms": round(pct(samples, 50), 1), "p95_ms": round(pct(samples, 95), 1),
                     "p99_ms": round(pct(samples, 99), 1), "max_ms": round(max(samples), 1),
                     "mean_ms": round(statistics.fmean(samples), 1), "payload_bytes": size}
        print(f"{name:34s} p50 {out[name]['p50_ms']:7.1f}  p95 {out[name]['p95_ms']:7.1f}  p99 {out[name]['p99_ms']:7.1f}  bytes {size}")
    json.dump(out, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()

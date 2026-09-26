"""Live API probe for the ASTFLOW audit. Read-only against a running `npm run demo` (127.0.0.1:8000).

    .venv/Scripts/python.exe audit/tools/api_probe.py [--out audit/evidence/api-probe.json]

Every case records the expected status, the actual status, the latency and a short body excerpt.
Indexing is exercised only against the bundled demo repository and only for versions it already has.
"""
import argparse
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"Content-Type": "application/json"} if data is not None else {}
    hdrs.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status, text = resp.status, resp.read().decode("utf-8", "replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as err:
        status, text, resp_headers = err.code, err.read().decode("utf-8", "replace"), {k.lower(): v for k, v in err.headers.items()}
    return status, text, (time.perf_counter() - started) * 1000, resp_headers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="audit/evidence/api-probe.json")
    args = parser.parse_args()
    repo = json.loads(call("GET", "/api/repository")[1])
    demo = repo["demo_path"]
    long_q = "bluetooth " * 250
    sym = "voice/VoiceHandler.js::VoiceHandler.handle"
    cases = [
        # (name, method, path, body, headers, raw, expected)
        ("health", "GET", "/api/health", None, None, None, 200),
        ("repository", "GET", "/api/repository", None, None, None, 200),
        ("repository unknown version", "GET", "/api/repository?version=nope", None, None, None, 200),
        ("versions", "GET", "/api/versions", None, None, None, 200),
        ("index status", "GET", "/api/index/status", None, None, None, 200),
        ("checkpoint", "GET", "/api/checkpoint", None, None, None, 200),
        ("openapi", "GET", "/openapi.json", None, None, None, 200),
        ("docs page (disabled)", "GET", "/docs", None, None, None, 404),
        ("frontend root", "GET", "/", None, None, None, 200),
        ("unknown route", "GET", "/api/nope", None, None, None, 404),
        # search
        ("search valid", "POST", "/api/search", {"query": "Where is Bluetooth settings handled?", "version": "working-tree"}, None, None, 200),
        ("search nonsense", "POST", "/api/search", {"query": "qxzjvnonexistentidentifier", "version": "working-tree"}, None, None, 200),
        ("search blank", "POST", "/api/search", {"query": "   "}, None, None, 422),
        ("search missing query", "POST", "/api/search", {}, None, None, 422),
        ("search wrong type", "POST", "/api/search", {"query": 5}, None, None, 422),
        ("search top_k 0", "POST", "/api/search", {"query": "auth", "top_k": 0}, None, None, 422),
        ("search top_k 51", "POST", "/api/search", {"query": "auth", "top_k": 51}, None, None, 422),
        ("search top_k 50", "POST", "/api/search", {"query": "auth", "top_k": 50}, None, None, 200),
        ("search extra field", "POST", "/api/search", {"query": "auth", "mode": "reranked"}, None, None, 422),
        ("search 2000 chars", "POST", "/api/search", {"query": "a" * 2000}, None, None, 200),
        ("search 12000-char problem statement", "POST", "/api/search", {"query": "read n integers and print the maximum subarray sum " * 240}, None, None, 200),
        ("search 2001 chars", "POST", "/api/search", {"query": "a" * 2001}, None, None, 422),
        ("search long real query", "POST", "/api/search", {"query": long_q[:1999]}, None, None, 200),
        ("search unicode", "POST", "/api/search", {"query": "Где bluetooth 设置 🔵 <script>alert(1)</script>"}, None, None, 200),
        ("search unindexed version", "POST", "/api/search", {"query": "auth", "version": "7826d38cae72db7ba0e53a0bcc5aa339783e09f0"}, None, None, 400),
        ("search unknown version", "POST", "/api/search", {"query": "auth", "version": "does-not-exist"}, None, None, 400),
        ("search runtime trace", "POST", "/api/search", {"query": "auth", "runtime_trace_id": "x"}, None, None, 400),
        ("search malformed json", "POST", "/api/search", None, None, b"{not json", 422),
        ("search wrong content type", "POST", "/api/search", None, {"Content-Type": "text/plain"}, b'{"query":"auth"}', 415),
        ("search body > 128KB", "POST", "/api/search", None, None, json.dumps({"query": "a" * 140000}).encode(), 413),
        ("search cross origin", "POST", "/api/search", {"query": "auth"}, {"Origin": "https://evil.example"}, None, 403),
        ("search cross-site fetch", "POST", "/api/search", {"query": "auth"}, {"Sec-Fetch-Site": "cross-site"}, None, 403),
        ("search allowed dev origin", "POST", "/api/search", {"query": "auth"}, {"Origin": "http://127.0.0.1:5173"}, None, 200),
        ("bad host header", "GET", "/api/health", None, {"Host": "evil.example"}, None, 400),
        # source
        ("source valid", "GET", "/api/source?path=voice/VoiceHandler.js&version=working-tree", None, None, None, 200),
        ("source range", "GET", "/api/source?path=voice/VoiceHandler.js&start_line=2&end_line=3", None, None, None, 200),
        ("source traversal", "GET", "/api/source?path=../../README.md", None, None, None, 400),
        ("source absolute", "GET", "/api/source?path=/etc/passwd", None, None, None, 400),
        ("source backslash", "GET", "/api/source?path=voice%5CVoiceHandler.js", None, None, None, 400),
        ("source windows drive", "GET", "/api/source?path=C:/Windows/win.ini", None, None, None, 404),
        ("source not in snapshot", "GET", "/api/source?path=package.json", None, None, None, 404),
        ("source range outside", "GET", "/api/source?path=voice/VoiceHandler.js&start_line=999", None, None, None, 400),
        ("source end < start", "GET", "/api/source?path=voice/VoiceHandler.js&start_line=3&end_line=2", None, None, None, 400),
        ("source start 0", "GET", "/api/source?path=voice/VoiceHandler.js&start_line=0", None, None, None, 422),
        ("source missing path", "GET", "/api/source", None, None, None, 422),
        ("source unindexed version", "GET", "/api/source?path=voice/VoiceHandler.js&version=7826d38cae72db7ba0e53a0bcc5aa339783e09f0", None, None, None, 400),
        # map / symbol / trace
        ("map overview", "GET", "/api/map?version=working-tree", None, None, None, 200),
        ("map file", "GET", "/api/map?version=working-tree&file=voice/VoiceHandler.js", None, None, None, 200),
        ("map unknown file", "GET", "/api/map?version=working-tree&file=nope.js", None, None, None, 404),
        ("map symbol depth 3", "GET", f"/api/map?version=working-tree&symbol={sym}&depth=3", None, None, None, 200),
        ("map symbol depth 4", "GET", f"/api/map?version=working-tree&symbol={sym}&depth=4", None, None, None, 422),
        ("map unknown symbol", "GET", "/api/map?version=working-tree&symbol=nope", None, None, None, 404),
        ("symbol valid", "GET", f"/api/symbol/{sym}", None, None, None, 200),
        ("symbol unknown", "GET", "/api/symbol/nope::x", None, None, None, 404),
        ("trace valid", "POST", "/api/trace", {"source_symbol_id": "VoiceHandler", "target_symbol_id": "BluetoothAgent"}, None, None, 200),
        ("trace unknown symbols", "POST", "/api/trace", {"source_symbol_id": "Nope", "target_symbol_id": "Missing"}, None, None, 200),
        ("trace depth 9", "POST", "/api/trace", {"source_symbol_id": "a", "target_symbol_id": "b", "max_depth": 9}, None, None, 422),
        ("trace missing target", "POST", "/api/trace", {"source_symbol_id": "a"}, None, None, 422),
        # compare
        ("compare v1 v2", "POST", "/api/compare", {"query": "session restoration", "version_a": "v1", "version_b": "v2"}, None, None, 200),
        ("compare same version", "POST", "/api/compare", {"query": "auth", "version_a": "v2", "version_b": "v2"}, None, None, 200),
        ("compare unindexed", "POST", "/api/compare", {"query": "auth", "version_a": "v1", "version_b": "7826d38cae72db7ba0e53a0bcc5aa339783e09f0"}, None, None, 400),
        ("compare missing field", "POST", "/api/compare", {"query": "auth", "version_a": "v1"}, None, None, 422),
        # index (only safe cases; a real re-index of an existing demo version is exercised by the E2E suite)
        ("index missing path", "POST", "/api/index", {"version": "v1"}, None, None, 422),
        ("index nonexistent path", "POST", "/api/index", {"repo_path": "C:/definitely/not/here", "version": "working-tree", "background": False}, None, None, 404),
        ("index file not dir", "POST", "/api/index", {"repo_path": demo + "/voice/VoiceHandler.js", "version": "working-tree", "background": False}, None, None, 400),
        ("index bad revision", "POST", "/api/index", {"repo_path": demo, "version": "no-such-rev", "background": False}, None, None, 400),
        ("index revision injection", "POST", "/api/index", {"repo_path": demo, "version": "--output=/tmp/x", "background": False}, None, None, 400),
    ]
    out = []
    for name, method, path, body, headers, raw, expected in cases:
        status, text, ms, resp_headers = call(method, path, body, headers, raw)
        row = {"case": name, "method": method, "path": path[:120], "expected": expected, "status": status,
               "pass": status == expected, "latency_ms": round(ms, 1), "body": text[:300]}
        if name == "search nonsense":
            data = json.loads(text)
            row["result_count"] = len(data["results"])
            row["evidence_kinds"] = sorted({("lex" if r["evidence"].get("lexical_rank") else "") + ("sem" if r["evidence"].get("semantic_rank") else "") for r in data["results"]})
            row["top_semantic_scores"] = [round(r["evidence"].get("semantic_score") or 0, 3) for r in data["results"][:5]]
        if name == "search valid":
            data = json.loads(text)
            row["top3"] = [r["qualified_name"] for r in data["results"][:3]]
            row["security_headers"] = {k: resp_headers.get(k) for k in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "cache-control")}
        out.append(row)
        print(f"{'PASS' if row['pass'] else 'FAIL'} {status} (exp {expected}) {ms:7.1f} ms  {name}")
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"{sum(r['pass'] for r in out)}/{len(out)} cases matched expectation -> {args.out}")


if __name__ == "__main__":
    main()

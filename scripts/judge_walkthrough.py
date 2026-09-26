"""First-time-evaluator walkthrough against a *running* ASTFLOW (`npm run demo`), through its HTTP API only.

Every task has an expected answer taken from the repository's source before the run; the script records what
ASTFLOW returned, checks each returned snippet against the served source of the *selected* version, and times
every call. Output: a JSON record and a Markdown table (audit/walkthrough/).

    python scripts/judge_walkthrough.py --express /path/to/express/clone [--server-pid PID]
"""
import argparse
import json
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000/api"
EXPRESS_VERSIONS = ["4.18.2", "4.19.2", "4.21.2"]
# A dataset-length query (competitive-programming style statement, ~2,400 characters) for long-query latency.
LONG_QUERY = ("You are given an array of n integers a1, a2, ..., an and q queries. Each query is either an update that "
              "sets the value at position p to x, or a request to report the maximum sum of a contiguous subarray "
              "inside the segment from l to r. ") * 8


def call(method, path, body=None, timeout=7200):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"content-type": "application/json"} if data else {})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            payload = json.loads(reply.read())
            status = reply.status
    except urllib.error.HTTPError as exc:
        payload, status = json.loads(exc.read() or b"{}"), exc.code
    return payload, status, round((time.perf_counter() - started) * 1000, 1)


def search(query, version, top_k=10):
    found, status, wall = call("POST", "/search", {"query": query, "version": version, "top_k": top_k})
    assert status == 200, (status, found)
    return found, wall


def summarize(found, n=5):
    rows = []
    for r in found["results"][:n]:
        e = r["evidence"]
        rows.append({"rank": r["rank"], "symbol": r["qualified_name"], "location": f"{r['file_path']}:{r['start_line']}-{r['end_line']}",
                     "exact_symbol": e.get("exact_symbol_match"), "semantic_rank": e.get("semantic_rank"),
                     "keyword_rank": e.get("lexical_rank"), "call_hops": e.get("structural_distance")})
    return rows


def source_check(found, version, n=3):
    """Every returned snippet must be the served source of that exact version and line range."""
    checks = []
    for r in found["results"][:n]:
        query = urllib.parse.urlencode({"path": r["file_path"], "version": version, "start_line": r["start_line"],
                                        "end_line": r["end_line"]})
        source, status, _ = call("GET", f"/source?{query}")
        checks.append(bool(status == 200 and r["snippet"].strip() in source["content"]
                           and source["version_key"] == found["version_key"] and r["version"] == version))
    return all(checks), checks


def grade(found, expected, within=1):
    """Expected answers are "file::qualified name". PASS: one is ranked within `within` (1 for "where is X", 3 for
    usage questions, whose definition legitimately comes first); PARTIAL: within the top 5; FAIL otherwise."""
    names = [f"{r['file_path']}::{r['qualified_name']}" for r in found["results"]]
    ranks = [names.index(e) + 1 for e in expected if e in names]
    best = min(ranks) if ranks else None
    return ("PASS" if best and best <= within else "PARTIAL" if best and best <= 5 else "FAIL"), best


def task(record, tid, title, repo, version, query, expected, note="", within=1):
    found, wall = search(query, version)
    verdict, rank = grade(found, expected, within)
    ok, _ = source_check(found, version)
    row = {"id": tid, "title": title, "repository": repo, "version": version, "query": query, "expected": expected,
           "expected_rank": rank, "verdict": verdict, "sources_match_selected_version": ok,
           "match_basis": found["match_basis"], "intent": found["intent"], "retrieval": found["retrieval"],
           "server_latency_ms": found["latency_ms"], "wall_ms": wall, "top": summarize(found),
           "trace": [f"{s['step']} · {s['details']}" for s in found["agent_trace"]], "note": note}
    record["tasks"].append(row)
    print(f"{tid} {verdict:7} rank={rank} {found['latency_ms']:.0f} ms  {query[:70]}")
    return found, row


def symbol_id(version, qualified_name, file=None):
    overview, _, _ = call("GET", f"/map?version={version}" + (f"&file={urllib.parse.quote(file)}" if file else ""))
    return next(n["symbol_id"] for n in overview["nodes"] if n["qualified_name"] == qualified_name)


def neighbours(version, sid):
    graph, _, _ = call("GET", f"/map?version={version}&symbol={urllib.parse.quote(sid)}&depth=1")
    names = {n["symbol_id"]: n["qualified_name"] for n in graph["nodes"]}
    callers = sorted(names[e["source"]] for e in graph["edges"] if e["target"] == sid)
    callees = sorted(names[e["target"]] for e in graph["edges"] if e["source"] == sid)
    return callers, callees


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--express", required=True, help="a full git clone of github.com/expressjs/express")
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--out", default=str(ROOT / "audit" / "walkthrough"))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    health, _, _ = call("GET", "/health")
    record = {"health_at_start": health, "tasks": [], "indexing": [], "graph": {}, "latency": {}}
    print("health:", json.dumps(health["retrieval"]))

    # --- Demo repository (indexed by `npm run demo`) ---
    task(record, "T2-demo", "Usage query", "demo", "working-tree", "Where is openBluetoothSettings used?",
         ["bluetooth/BluetoothAgent.js::BluetoothAgent.execute"], within=3)
    found, row = task(record, "T3", "Structural query (call order)", "demo", "working-tree",
                      "Which functions call checkBluetoothPermission before openBluetoothSettings?",
                      ["bluetooth/BluetoothAgent.js::BluetoothAgent.execute"], within=3)
    row["sequence_evidence"] = found["sequences"]
    if not found["sequences"]:
        row["verdict"] = "FAIL"
    found, row = task(record, "T6-demo", "No-evidence query (honesty)", "demo", "working-tree", "qxzjvnonexistentidentifier", [])
    row["verdict"] = "PASS" if found["match_basis"] in {"SEMANTIC_ONLY", "NONE"} else "FAIL"
    for version, expected in [("v1", "auth/AuthService.js::AuthService.restore"),
                              ("v2", "session/SessionManager.js::SessionManager.restore")]:
        task(record, f"T4-demo-{version}", "Version retrieval (demo refactor)", "demo", version,
             "Where is the saved session restored after restart?", [expected])
    route = symbol_id("working-tree", "IntentRouter.route", "voice/IntentRouter.js")
    callers, callees = neighbours("working-tree", route)
    trace_from = symbol_id("working-tree", "VoiceHandler.handle", "voice/VoiceHandler.js")
    trace_to = symbol_id("working-tree", "openBluetoothSettings", "settings/deeplinks.js")
    path, _, _ = call("POST", "/trace", {"source_symbol_id": trace_from, "target_symbol_id": trace_to, "version": "working-tree"})
    record["graph"]["demo"] = {
        "symbol": "IntentRouter.route", "callers": callers, "callees": callees,
        "expected_callers": ["VoiceHandler.handleRequest"], "expected_callees": ["BluetoothAgent.execute", "openWifiSettings"],
        "trace": "VoiceHandler.handle -> openBluetoothSettings", "trace_status": path.get("status"),
        "trace_paths": [[p.split("::")[-1] for p in p_] for p_ in path.get("paths", [])][:3]}
    g = record["graph"]["demo"]
    g["verdict"] = "PASS" if (set(g["expected_callers"]) <= set(callers) and set(g["expected_callees"]) <= set(callees)
                              and g["trace_paths"]) else "FAIL"
    print("graph demo:", g["verdict"], callers, callees, g["trace_paths"][:1])

    # --- Express: an unfamiliar, real repository, three real Git tags (P1) ---
    for version in EXPRESS_VERSIONS:
        reply, status, wall = call("POST", "/index", {"repo_path": args.express, "version": version, "background": False})
        assert status == 200, reply
        m = reply["manifest"]
        record["indexing"].append({"repository": "expressjs/express", "version": version, "wall_s": round(wall / 1000, 1),
                                   "files": m["file_count"], "chunks": m["chunk_count"], "edges": m["edge_count"],
                                   "embedding_cache": m["embedding_cache"], "embedding_model": m["embedding_model"],
                                   "retrieval": m["retrieval"]})
        print(f"indexed express {version}: {m['chunk_count']} chunks in {wall / 1000:.1f} s {m['embedding_cache']}")
    if args.server_pid:
        for line in Path(f"/proc/{args.server_pid}/status").read_text().splitlines():
            if line.startswith(("VmHWM", "VmRSS")):
                record.setdefault("memory", {})[line.split(":")[0]] = line.split(":")[1].strip()

    latest = EXPRESS_VERSIONS[-1]
    task(record, "T1", "Plain-English retrieval", "expressjs/express", latest,
         "Which code picks the response format based on what the client says it accepts?", ["lib/response.js::format"])
    task(record, "T2", "Usage query", "expressjs/express", latest, "Where is compileQueryParser used?",
         ["lib/application.js::set"], within=3)
    for version in EXPRESS_VERSIONS:
        found, row = task(record, f"T4-{version}", "Version retrieval (P1)", "expressjs/express", version,
                          "where is the redirect location URL encoded", ["lib/response.js::location"])
        top = found["results"][0]
        at_tag = subprocess.run(["git", "-C", args.express, "show", f"{version}:{top['file_path']}"], check=True,
                                capture_output=True, text=True).stdout.splitlines()
        row["top_matches_git_show_at_tag"] = top["snippet"].strip() in "\n".join(at_tag[top["start_line"] - 1:top["end_line"]])
        row["top_version_key"] = top["version"]
    found, row = task(record, "T5", "Large-repository navigation", "expressjs/express", latest,
                      "Where is view template rendering implemented?", ["lib/view.js::render", "lib/application.js::render", "lib/response.js::render",
                       "lib/application.js::tryRender"])
    if found["results"]:
        first = found["results"][0]
        callers, callees = neighbours(latest, first["symbol_id"])
        row["relationships_of_top_result"] = {"symbol": first["qualified_name"], "callers": callers, "callees": callees}
    found, row = task(record, "T6", "No-evidence query (honesty)", "expressjs/express", latest,
                      "Where is the Kafka consumer offset committed?", [])
    row["verdict"] = "PASS" if found["match_basis"] in {"SEMANTIC_ONLY", "NONE"} else "PARTIAL"
    row["note"] = "PASS if the UI labels the list as meaning-only (no shared word or symbol) rather than 'relevant code'"

    # --- Latency: server-side, after warm-up ---
    for name, query in [("short", "where is the redirect location URL encoded"), ("long", LONG_QUERY)]:
        search(query, latest)
        samples = [search(query, latest)[0]["latency_ms"] for _ in range(7)]
        record["latency"][name] = {"characters": len(query), "samples_ms": samples,
                                   "p50_ms": statistics.median(samples), "max_ms": max(samples)}
        print(f"latency {name}: p50 {statistics.median(samples):.0f} ms")
    record["health_at_end"] = call("GET", "/health")[0]
    (out / "results.json").write_text(json.dumps(record, indent=1), encoding="utf-8")

    lines = ["| Task | Repository @ version | Query | Expected | Rank | Verdict | Sources match version | Latency |",
             "|---|---|---|---|---:|---|---|---:|"]
    for t in record["tasks"]:
        lines.append(f"| {t['id']} | {t['repository']} @ {t['version']} | {t['query'][:70]} | {', '.join(t['expected']) or '(none)'} | "
                     f"{t['expected_rank'] or '—'} | {t['verdict']} | {t['sources_match_selected_version']} | {t['server_latency_ms']:.0f} ms |")
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

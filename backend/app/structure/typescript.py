import json
import subprocess

from backend.app.config import ROOT
from backend.app.models.entities import Edge
from backend.app.parsing.javascript import CALLABLE


def enrich(files, symbols, edges):
    try:
        process = subprocess.run(["node", str(ROOT / "tools" / "ts_enrich.mjs")],
                                 input=json.dumps({"files": files}), capture_output=True, text=True,
                                 encoding="utf-8", timeout=45, cwd=ROOT)
        if process.returncode:
            return edges, {"status": "unavailable", "message": process.stderr.strip()[-400:], "edges_added": 0, "edges_confirmed": 0}
        data = json.loads(process.stdout)
        added, confirmed = 0, 0
        existing = {(e.source_symbol_id, e.target_symbol_id, e.call_start_byte): e for e in edges}

        def at(path, offset):
            matches = [s for s in symbols if s.file_path == path and s.kind in CALLABLE and s.start_byte <= offset < s.end_byte]
            return min(matches, key=lambda s: s.end_byte - s.start_byte) if matches else None

        for row in data["calls"]:
            source = at(row["call_file"], row["call_start_byte"])
            target = at(row["target_file"], row["target_start_byte"])
            if not source or not target:
                continue
            key = (source.symbol_id, target.symbol_id, row["call_start_byte"])
            if key in existing:
                existing[key].evidence_sources.append("TS_LANGUAGE_SERVICE")
                confirmed += 1
            else:
                edge = Edge(source.symbol_id, target.symbol_id, "CALLS", row["call_file"], row["call_line"],
                            row["call_end_line"], row["call_start_byte"], row["call_end_byte"], row["expression"],
                            "typescript_declaration", "LANGUAGE_SERVICE_VERIFIED", ["TS_LANGUAGE_SERVICE"])
                edges.append(edge)
                existing[key] = edge
                added += 1
        return sorted(edges, key=lambda e: (e.call_file, e.call_start_byte, e.target_symbol_id)), {"status": "ready", "edges_added": added, "edges_confirmed": confirmed}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return edges, {"status": "unavailable", "message": str(exc), "edges_added": 0, "edges_confirmed": 0}

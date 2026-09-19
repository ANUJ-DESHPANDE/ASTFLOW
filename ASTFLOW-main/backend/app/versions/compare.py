from difflib import SequenceMatcher
from collections import defaultdict

from backend.app.agent.investigate import investigate


def compare_indexes(a, b, query: str, version_a: str, version_b: str):
    result_a = investigate(a, query, version_a)
    result_b = investigate(b, query, version_b)
    sa = {s.symbol_id: s for s in a.symbols}
    sb = {s.symbol_id: s for s in b.symbols}
    added, removed = set(sb) - set(sa), set(sa) - set(sb)
    modified = {sid for sid in set(sa) & set(sb) if sa[sid].content_hash != sb[sid].content_hash}
    moved = []
    for old in sorted(removed):
        matches = [new for new in sorted(added) if sb[new].qualified_name == sa[old].qualified_name
                   and (sb[new].content_hash == sa[old].content_hash or SequenceMatcher(None, sa[old].source_text, sb[new].source_text).ratio() >= .96)]
        if len(matches) == 1:
            new = matches[0]
            moved.append({"from": old, "to": new, "evidence": "matching_name_and_body"})
            added.remove(new)
    removed -= {m["from"] for m in moved}

    def edge_key(e):
        return (e.source_symbol_id, e.target_symbol_id, e.edge_type, e.source_expression)

    ea, eb = defaultdict(list), defaultdict(list)
    for edge in a.edges:
        ea[edge_key(edge)].append(edge)
    for edge in b.edges:
        eb[edge_key(edge)].append(edge)
    ranks_a = {r["symbol_id"]: r["rank"] for r in result_a["results"]}
    ranks_b = {r["symbol_id"]: r["rank"] for r in result_b["results"]}
    relevant = set(ranks_a) | set(ranks_b)
    added_edges = [edge.to_dict() for k in sorted(eb) for edge in eb[k][len(ea[k]):]]
    removed_edges = [edge.to_dict() for k in sorted(ea) for edge in ea[k][len(eb[k]):]]
    return {
        "query": query, "version_a": version_a, "version_b": version_b,
        "version_key_a": a.manifest["version_key"], "version_key_b": b.manifest["version_key"],
        "results_a": result_a["results"], "results_b": result_b["results"],
        "rank_changes": [{"symbol_id": sid, "rank_a": ranks_a.get(sid), "rank_b": ranks_b.get(sid),
                          "delta": ranks_a[sid] - ranks_b[sid] if sid in ranks_a and sid in ranks_b else None}
                         for sid in sorted(relevant, key=lambda sid: (ranks_b.get(sid, 100), sid))],
        "changes": {"added_symbols": sorted(added), "removed_symbols": sorted(removed),
                    "modified_symbols": sorted(modified), "moved_symbols": moved,
                    "added_edges": added_edges, "removed_edges": removed_edges},
        "relevant_changes": {"added_symbols": sorted(added & relevant), "removed_symbols": sorted(removed & relevant),
                             "modified_symbols": sorted(modified & relevant),
                             "added_edges": [e for e in added_edges if e["source"] in relevant or e["target"] in relevant],
                             "removed_edges": [e for e in removed_edges if e["source"] in relevant or e["target"] in relevant]},
        "graph_a": a.graph.subgraph(set(ranks_a)), "graph_b": b.graph.subgraph(set(ranks_b)),
        "latency_ms": round(result_a["latency_ms"] + result_b["latency_ms"], 2),
    }

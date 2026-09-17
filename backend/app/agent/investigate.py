import re
import time
from copy import deepcopy

from backend.app.retrieval.search import serialize_result


def plan(query: str, graph):
    lower = query.lower()
    if re.search(r"\b(version|commit|refactor|previous|changed)\b", lower):
        intent = "VERSION"
    elif re.search(r"\b(before|after)\b", lower):
        intent = "SEQUENCE"
    elif re.search(r"\b(reach|path|connect|flow|trace)\b", lower) or "how does" in lower:
        intent = "PATH"
    elif re.search(r"\b(used|usage|callers|calls|called)\b", lower):
        intent = "USAGE"
    elif re.search(r"\b(where|find|locate)\b", lower):
        intent = "LOCATE"
    else:
        intent = "GENERAL"
    matched = []
    for name in {s.name for s in graph.symbols.values()} | {s.qualified_name for s in graph.symbols.values()}:
        match = re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", query)
        if match and len(name) > 2 and not name.startswith(("<", "test:", "callback@")):
            matched.append((match.start(), -len(name), name))
    names = []
    for _, _, name in sorted(matched):
        if not any(name in previous for previous in names):
            names.append(name)
    return {"intent": intent, "symbols": names[:6], "max_passes": 2}


def investigate(index, query: str, version: str, top_k: int = 10, agentic: bool = True, mode: str = "full"):
    started = time.perf_counter()
    retriever, graph = index.retriever, index.graph
    settings = retriever.settings
    query_plan = plan(query, graph)
    trace = [{"step": "PLAN", "details": f"{query_plan['intent'].title()} investigation; at most two retrieval passes", "data": query_plan}]
    rows, diagnostics = retriever.rank(query, mode=mode if mode in {"bm25", "dense"} else "hybrid", boosts=mode == "full")
    trace.append({"step": "SEARCH", "details": f"Retrieved {len(rows)} candidates", "data": {"pass": 1, **diagnostics}})
    paths = None
    if len(query_plan["symbols"]) >= 2 and query_plan["intent"] in {"PATH", "SEQUENCE"}:
        paths = graph.trace(query_plan["symbols"][0], query_plan["symbols"][-1])
    lexical_top, semantic_top = set(diagnostics["lexical_top"][:5]), set(diagnostics["semantic_top"][:5])
    agreement = len(lexical_top & semantic_top) / max(1, len(lexical_top | semantic_top)) if diagnostics["semantic_available"] else None
    seeds = [r for r in rows[:3] if r["evidence"]["lexical_rank"] or (r["evidence"]["semantic_score"] or 0) > .25]
    found_ids = {r["chunk"].symbol_id for r in rows[:10]}
    targets = {sid for name in query_plan["symbols"] for sid in graph.resolve(name)}
    missing = sorted(targets - found_ids)
    observation = {"top_score": rows[0]["score"] if rows else 0, "ranking_agreement": agreement,
                   "file_diversity": len({r["chunk"].file_path for r in rows[:10]}),
                   "exact_matches": sum(r["evidence"]["exact_symbol_match"] for r in rows[:10]),
                   "missing_targets": missing, "path_supported": bool(paths and paths["paths"]),
                   "seed_ids": [r["chunk"].symbol_id for r in seeds]}
    trace.append({"step": "OBSERVE", "details": f"Found {observation['exact_matches']} exact matches across {observation['file_diversity']} files; {len(missing)} target(s) outside the top ten", "data": observation})
    structural_intent = query_plan["intent"] in {"PATH", "USAGE", "SEQUENCE"}
    expand = mode in {"full", "hybrid_structure"} and bool(seeds)
    second_pass = agentic and mode == "full" and bool(seeds) and (structural_intent or bool(missing) or (agreement is not None and agreement < .2))
    candidates = {row["chunk"].chunk_id: row for row in rows}
    if second_pass:
        # The follow-up query is derived from observed candidates and missing targets.
        discovered = [graph.symbols[s].qualified_name for s in missing[:2]] or [r["chunk"].qualified_name for r in seeds[:2]]
        followup_query = query + " " + " ".join(discovered)
        action = "EXACT_SYMBOL_EXPANSION" if missing else "CALLER_EXPANSION" if query_plan["intent"] == "USAGE" else "GRAPH_NEIGHBOR_EXPANSION" if structural_intent else "PSEUDO_RELEVANCE_EXPANSION"
        trace.append({"step": "REFINE", "details": f"{action.replace('_', ' ').title()} around {', '.join(discovered)}", "data": {"action": action, "query": followup_query, "based_on": observation["seed_ids"]}})
        refined, _ = retriever.rank(followup_query)
        for rank, row in enumerate(refined, 1):
            cid = row["chunk"].chunk_id
            if cid not in candidates:
                row["score"] = 0.
                row["evidence"]["lexical_rank"] = None
                row["evidence"]["semantic_rank"] = None
                row["evidence"]["contributions"] = {}
                candidates[cid] = row
            contribution = settings.refinement_weight / (settings.rrf_k + rank)
            candidates[cid]["score"] += contribution
            candidates[cid]["evidence"].update(refinement_query=followup_query, refinement_rank=rank)
            candidates[cid]["evidence"]["contributions"]["refinement"] = contribution
        trace.append({"step": "SEARCH", "details": f"Second pass retrieved {len(refined)} candidates using observed symbols", "data": {"pass": 2}})
    if expand:
        seed_ids = [r["chunk"].symbol_id for r in seeds]
        seed_ids.extend(sorted(targets & set(graph.graph)))
        path_ids = {sid for path in (paths or {}).get("paths", []) for sid in path}
        distance_map = {}
        for seed in dict.fromkeys(seed_ids):
            frontier, visited = [seed], {seed}
            for distance in range(1, 3):
                next_frontier = []
                for current in frontier:
                    neighbors = graph.callers(current) if query_plan["intent"] == "USAGE" else graph.neighbors(current)
                    for neighbor in neighbors[:50]:
                        if neighbor in visited:
                            continue
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
                        if neighbor not in distance_map or distance < distance_map[neighbor][0]:
                            distance_map[neighbor] = (distance, current)
                frontier = next_frontier
        for sid in path_ids:
            if sid not in distance_map:
                distance_map[sid] = (1, None)
        for sid, (distance, via) in distance_map.items():
            chunk = retriever.by_id.get(sid)
            if not chunk:
                continue
            if sid not in candidates:
                candidates[sid] = {"chunk": chunk, "score": 0., "evidence": {
                    "lexical_rank": None, "semantic_rank": None, "lexical_score": 0, "semantic_score": None,
                    "exact_symbol_match": False, "test_reference": False, "runtime_observed": False,
                    "contributions": {}, "relationship_status": "SEARCH_INFERRED"}}
            row = candidates[sid]
            edge_evidence = [e.to_dict() for e in graph.edges if {e.source_symbol_id, e.target_symbol_id} == {sid, via}]
            boost = settings.graph_boost * settings.graph_decay ** (distance - 1)
            row["score"] += boost
            row["evidence"].update({"structural_distance": distance, "structural_edges": edge_evidence,
                                     "relationship_status": edge_evidence[0]["evidence_type"] if edge_evidence else "SEARCH_INFERRED"})
            row["evidence"]["contributions"]["structural"] = boost
            if via and graph.symbols.get(via) and graph.symbols[via].is_test:
                row["evidence"]["test_reference"] = True
                row["evidence"]["test_symbol_id"] = via
        diagnostics["expanded_candidates"] = len(distance_map)
    ordered = sorted(candidates.values(), key=lambda r: (-r["score"], r["chunk"].chunk_id))
    results = [serialize_result(r, i + 1, version) for i, r in enumerate(ordered[:top_k])]
    relevant_ids = {r["symbol_id"] for r in results[:6]}
    relevant_ids.update(sid for p in (paths or {}).get("paths", []) for sid in p)
    subgraph = graph.subgraph(relevant_ids, (paths or {}).get("paths", []))
    sequence = [s for s in index.extra.get("sequences", []) if s["caller"] in relevant_ids] if query_plan["intent"] == "SEQUENCE" else []
    trace.append({"step": "RERANK", "details": f"Ranked {len(ordered)} candidates using stored evidence", "data": {"candidates": len(ordered)}})
    trace.append({"step": "STOP", "details": f"Returned {len(results)} source snippets after {2 if second_pass else 1} retrieval pass(es)"})
    return {"query": query, "version": version, "version_key": index.manifest["version_key"],
            "results": results, "intent": query_plan["intent"], "agent_trace": trace,
            "graph": subgraph, "sequences": sequence, "path_status": (paths or {}).get("status"),
            "semantic": {**index.manifest["semantic"], "available": diagnostics["semantic_available"]}, "diagnostics": diagnostics,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

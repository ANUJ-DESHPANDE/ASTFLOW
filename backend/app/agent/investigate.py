import re
import time
from pathlib import PurePosixPath

from backend.app.retrieval.embeddings import ModelUnavailable
from backend.app.retrieval.search import serialize_result


class CitationIntegrityError(RuntimeError):
    """An indexed result cannot be resolved against its pinned source snapshot."""


def _safe_source_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return bool(path) and not parsed.is_absolute() and "\\" not in path and ".." not in parsed.parts


def validate_citations(index, results: list[dict], graph: dict) -> None:
    """Check only evidence exposed to users; never read the working tree."""
    chunks = {c.chunk_id: c for c in index.chunks}
    for result in results:
        chunk = chunks.get(result["chunk_id"])
        path = result["file_path"]
        source = index.files.get(path)
        if (not _safe_source_path(path) or chunk is None or source is None
                or chunk.file_path != path or chunk.symbol_id != result["symbol_id"]):
            raise CitationIntegrityError("Search result is not in the pinned index")
        lines = source.splitlines(keepends=True)
        start, end = result["start_line"], result["end_line"]
        if (start != chunk.start_line or end != chunk.end_line or start < 1
                or end < start or end > len(lines) or result["snippet"] != chunk.text
                or result["snippet"] not in "".join(lines[start - 1:end])):
            raise CitationIntegrityError("Search citation does not match indexed source")
    for node in graph["nodes"]:
        symbol = index.graph.symbols.get(node["symbol_id"])
        if (not _safe_source_path(node["file"]) or node["file"] not in index.files
                or symbol is None or symbol.file_path != node["file"]
                or symbol.start_line != node["start_line"] or symbol.end_line != node["end_line"]):
            raise CitationIntegrityError("Graph citation is not in the pinned index")
    indexed_edges = [stored.to_dict() for stored in index.graph.edges]
    node_ids = {node["symbol_id"] for node in graph["nodes"]}
    for edge in graph["edges"]:
        if edge not in indexed_edges or edge["source"] not in node_ids or edge["target"] not in node_ids:
            raise CitationIntegrityError("Graph relationship is not in the pinned index")
        source = index.files.get(edge["call_file"])
        if not _safe_source_path(edge["call_file"]) or source is None:
            raise CitationIntegrityError("Graph call site is not in the pinned index")
        lines = source.splitlines(keepends=True)
        start, end = edge["call_line"], edge["call_end_line"]
        if start < 1 or end < start or end > len(lines) or edge["source_expression"] not in "".join(lines[start - 1:end]):
            raise CitationIntegrityError("Graph call site does not match indexed source")


def ground_question(query: str, graph) -> dict:
    """Classify only explicit symbol/relationship premises; retrieved neighbors are candidates, not answers."""
    names = {s.name for s in graph.symbols.values()}
    explicit = [token for token in re.findall(r"\b(?:[a-z][A-Za-z0-9_$]*[A-Z][A-Za-z0-9_$]*|[A-Z][A-Za-z0-9_$]*[a-z][A-Za-z0-9_$]*)\b", query)
                if token not in {"Where", "What", "Which", "How", "Why"}]
    requested = list(dict.fromkeys([*explicit, *plan(query, graph)["symbols"]]))
    candidates = []
    for name in requested:
        candidates.extend(s for s in graph.symbols.values() if s.name == name)
    candidates = sorted({s.symbol_id: s for s in candidates}.values(), key=lambda s: s.symbol_id)
    definitions = [{"symbol_id": s.symbol_id, "file": s.file_path, "start_line": s.start_line,
                    "end_line": s.end_line} for s in candidates]
    call = re.search(r"\b(?:why\s+)?does\s+([\w$]+)\s+call\s+([\w$]+)\b", query, re.I)
    if call:
        source_name, target_name = call.groups()
        sources = set(graph.resolve(source_name))
        targets = set(graph.resolve(target_name))
        edges = [e.to_dict() for e in graph.edges if e.source_symbol_id in sources and e.target_symbol_id in targets]
        source_matches = [s for s in graph.symbols.values() if s.name == source_name]
        target_matches = [s for s in graph.symbols.values() if s.name == target_name]
        status = ("AMBIGUOUS_SYMBOL" if len(source_matches) > 1 or len(target_matches) > 1
                  else "VERIFIED_CALL" if edges else "CALL_NOT_ESTABLISHED")
        return {"status": status, "requested_symbols": [source_name, target_name],
                "definitions": definitions, "call_edges": edges if status == "VERIFIED_CALL" else []}
    ambiguous = [name for name in requested if sum(s.name == name
                                              for s in graph.symbols.values()) > 1]
    if ambiguous:
        status = "AMBIGUOUS_SYMBOL"
    elif requested and any(name not in names for name in requested):
        status = "NO_VERIFIED_SYMBOL"
    else:
        feature = re.search(r"\bwhere is (?:the )?(.+?) implemented\??$", query, re.I)
        words = re.findall(r"[A-Za-z]{4,}", feature.group(1).lower()) if feature else []
        known_names = " ".join(names).lower()
        status = "NO_VERIFIED_IMPLEMENTATION" if words and not any(w in known_names for w in words) else "SOURCE_CANDIDATES"
    return {"status": status, "requested_symbols": requested, "definitions": definitions, "call_edges": []}


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
        # Substring pre-filter: only names that occur in the query can match, and compiling one regex per symbol
        # per query dominated search time on real repositories (~300-500 ms for 3-4k symbols).
        if len(name) <= 2 or name.startswith(("<", "test:", "callback@")) or name not in query:
            continue
        match = re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", query)
        if match:
            matched.append((match.start(), -len(name), name))
    names = []
    for _, _, name in sorted(matched):
        if not any(name in previous for previous in names):
            names.append(name)
    return {"intent": intent, "symbols": names[:6], "max_passes": 2}


def match_basis(results: list[dict]) -> str:
    """KEYWORD_MATCH if any result shares a query term or names a symbol in the query; SEMANTIC_ONLY if every
    result is only a nearest neighbour by embedding (or reached from one through the graph); NONE if empty."""
    if not results:
        return "NONE"
    keyword = any(r["evidence"].get("lexical_rank") or r["evidence"].get("exact_symbol_match") for r in results)
    return "KEYWORD_MATCH" if keyword else "SEMANTIC_ONLY"


def investigate(index, query: str, version: str, top_k: int = 10, agentic: bool = True, mode: str = "full", structure: bool = True):
    started = time.perf_counter()
    retriever, graph = index.retriever, index.graph
    settings = retriever.settings
    query_plan = plan(query, graph)
    trace = [{"step": "PLAN", "details": f"{query_plan['intent'].title()} investigation; at most two retrieval passes", "data": query_plan}]
    # First stage: an explicit ranking mode, else the configured one (frozen: GTE dense). Without embeddings (only
    # possible with ASTFLOW_SEMANTIC=off) hybrid ranking reduces to BM25, and the trace says so.
    first_stage = mode if mode in {"bm25", "dense", "hybrid"} else settings.retrieval
    if retriever.embeddings is None and first_stage != "bm25":
        first_stage = "hybrid"
    rows, diagnostics = retriever.rank(query, mode=first_stage, boosts=mode == "full")
    if (retriever.embeddings is not None and settings.semantic != "off"
            and not diagnostics["semantic_available"]):
        raise ModelUnavailable(retriever.embedder.reason)
    label = ("lexical only, no embedding model" if retriever.embeddings is None
             else f"{settings.model} {first_stage}")
    trace.append({"step": "SEARCH", "details": f"Retrieved {len(rows)} candidates ({label})",
                  "data": {"pass": 1, "ranking": first_stage, **diagnostics}})
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
    expand = structure and mode in {"full", "hybrid_structure"} and bool(seeds)
    second_pass = agentic and mode == "full" and bool(seeds) and (structural_intent or bool(missing) or (agreement is not None and agreement < .2))
    candidates = {row["chunk"].chunk_id: row for row in rows}
    if second_pass:
        # The follow-up query is derived from observed candidates and missing targets.
        discovered = [graph.symbols[s].qualified_name for s in missing[:2]] or [r["chunk"].qualified_name for r in seeds[:2]]
        followup_query = query + " " + " ".join(discovered)
        action = "EXACT_SYMBOL_EXPANSION" if missing else "CALLER_EXPANSION" if query_plan["intent"] == "USAGE" else "GRAPH_NEIGHBOR_EXPANSION" if structural_intent else "PSEUDO_RELEVANCE_EXPANSION"
        trace.append({"step": "REFINE", "details": f"{action.replace('_', ' ').title()} around {', '.join(discovered)}", "data": {"action": action, "query": followup_query, "based_on": observation["seed_ids"]}})
        refined, _ = retriever.rank(followup_query, mode=first_stage)
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
    validate_citations(index, results, subgraph)
    grounding = ground_question(query, graph)
    sequence = [s for s in index.extra.get("sequences", []) if s["caller"] in relevant_ids] if query_plan["intent"] == "SEQUENCE" else []
    if sequence:
        pair = query_plan["symbols"]
        if len(pair) == 2:
            first, second = pair
            if re.search(r"\bafter\b", query, re.I):
                first, second = second, first
            before_ids, after_ids = set(graph.resolve(first)), set(graph.resolve(second))
            sequence = [s for s in sequence if s["before"] in before_ids and s["after"] in after_ids]
        else:
            sequence = []  # No guessed ordered pair from semantic similarity.
    trace.append({"step": "RANK", "details": f"Ranked {len(ordered)} candidates using stored evidence", "data": {"candidates": len(ordered)}})
    trace.append({"step": "STOP", "details": f"Returned {len(results)} source snippets after {2 if second_pass else 1} retrieval pass(es)"})
    return {"query": query, "version": version, "version_key": index.manifest["version_key"],
            "results": results, "intent": query_plan["intent"], "agent_trace": trace,
            "graph": {**subgraph, "version_key": index.manifest["version_key"]}, "sequences": sequence, "path_status": (paths or {}).get("status"),
            "grounding": grounding,
            "status": "OK" if results else "NO_RESULTS",
            # Dense retrieval always returns its nearest neighbours, even for nonsense input. Say what the
            # results rest on so a meaning-only list is not presented as "the relevant code".
            "match_basis": match_basis(results),
            "semantic": {**index.manifest["semantic"], "available": diagnostics["semantic_available"]}, "diagnostics": diagnostics,
            "retrieval": {"model": settings.model if retriever.embeddings is not None else None, "ranking": first_stage,
                          "index_model": index.manifest.get("embedding_model"), "version_key": index.manifest["version_key"],
                          "resolved_revision": index.manifest.get("resolved_revision")},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

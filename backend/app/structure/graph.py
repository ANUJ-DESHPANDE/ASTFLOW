from collections import deque

import networkx as nx

from backend.app.models.entities import Edge, Symbol
from backend.app.parsing.javascript import CALLABLE


class ProjectGraph:
    def __init__(self, symbols: list[Symbol], edges: list[Edge]):
        self.symbols = {s.symbol_id: s for s in symbols}
        self.edges = edges
        self.graph = nx.DiGraph()
        self.graph.add_nodes_from(s.symbol_id for s in symbols if s.kind in CALLABLE)
        for edge in edges:
            if edge.source_symbol_id in self.graph and edge.target_symbol_id in self.graph:
                self.graph.add_edge(edge.source_symbol_id, edge.target_symbol_id)

    def callers(self, symbol: str):
        return sorted(self.graph.predecessors(symbol)) if symbol in self.graph else []

    def callees(self, symbol: str):
        return sorted(self.graph.successors(symbol)) if symbol in self.graph else []

    def neighbors(self, symbol: str):
        return sorted(set(self.callers(symbol) + self.callees(symbol)))

    def bounded_paths(self, source: str, target: str, max_depth: int = 5, limit: int = 20):
        if source not in self.graph or target not in self.graph:
            return []
        queue, paths, visited = deque([[source]]), [], 0
        while queue and len(paths) < limit and visited < 10000:
            path = queue.popleft()
            visited += 1
            if path[-1] == target:
                paths.append(path)
            elif len(path) - 1 < max_depth:
                for next_id in self.callees(path[-1]):
                    if next_id not in path:
                        queue.append([*path, next_id])
        return paths

    def shortest_paths(self, source: str, target: str, max_depth: int = 5):
        paths = self.bounded_paths(source, target, max_depth)
        return [p for p in paths if len(p) == len(paths[0])] if paths else []

    def resolve(self, name: str):
        if name in self.symbols:
            matches = [self.symbols[name]]
        else:
            matches = [s for s in self.symbols.values() if s.qualified_name == name or s.name == name]
        ids = []
        for symbol in matches:
            if symbol.kind == "class":
                ids.extend(s.symbol_id for s in self.symbols.values() if s.parent_symbol_id == symbol.symbol_id and s.kind in CALLABLE and s.name != "constructor")
            elif symbol.symbol_id in self.graph:
                ids.append(symbol.symbol_id)
        return sorted(set(ids))

    def subgraph(self, ids: set[str], paths=None):
        ids = ids & set(self.graph.nodes)
        return {
            "nodes": [{"symbol_id": s.symbol_id, "qualified_name": s.qualified_name,
                       "file": s.file_path, "start_line": s.start_line, "end_line": s.end_line, "kind": s.kind}
                      for sid in sorted(ids) if (s := self.symbols.get(sid))],
            "edges": [e.to_dict() for e in self.edges if e.source_symbol_id in ids and e.target_symbol_id in ids],
            "paths": paths or [],
        }

    def trace(self, source: str, target: str, max_depth: int = 5):
        sources, targets = self.resolve(source), self.resolve(target)
        paths = []
        for a in sources[:20]:
            for b in targets[:20]:
                paths.extend(self.bounded_paths(a, b, max_depth))
        paths = sorted(paths, key=lambda p: (len(p), p))[:20]
        ids = {s for p in paths for s in p}
        if not ids:
            ids = set((sources + targets)[:30])
        return {**self.subgraph(ids, paths), "status": "SUPPORTED" if paths else "NO_SUPPORTED_PATH",
                "message": f"{len(paths)} supported path(s)" if paths else "No supported call path in this snapshot. Search results may still identify related code.",
                "max_depth": max_depth}

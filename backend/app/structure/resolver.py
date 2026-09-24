"""Two-pass resolver: target nodes must already exist in the complete symbol table."""
import posixpath
import re

from backend.app.models.entities import Edge, ParsedFile
from backend.app.parsing.javascript import CALLABLE

NESTED_IDENTIFIER_CALLS = True


def resolve_structure(files: list[ParsedFile]) -> tuple[list[Edge], list[dict], list[dict]]:
    by_file = {f.path: f for f in files}
    symbols = {s.symbol_id: s for f in files for s in f.symbols}
    edges, unresolved, sequences = [], [], []

    def module_path(current: str, relative: str):
        if not relative.startswith("."):
            return None
        path = posixpath.normpath(posixpath.join(posixpath.dirname(current), relative))
        for candidate in ([path] if path.endswith(".js") else [path + ".js"] if not posixpath.splitext(path)[1] else []):
            if candidate in by_file:
                return candidate
        return None

    def imported(file: ParsedFile, name: str, member: str | None = None):
        imp = file.imports.get(name)
        if not imp or not imp.get("supported", False):
            return None
        path = module_path(file.path, imp["module"])
        if not path:
            return None
        target = by_file[path]
        if target.has_errors:
            return None
        key = member if imp["name"] == "*" else imp["name"]
        if sum(s.name == key and s.parent_symbol_id is None for s in target.symbols) != 1:
            return None
        if any(key in names for names in target.reassigned.values()):
            return None
        return symbols.get(target.exports.get(key, ""))

    def lookup(file: ParsedFile, name: str, scope: str | None):
        if any(name in names for names in file.reassigned.values()):
            return None
        current = symbols.get(scope)
        while current:
            if name in file.reassigned.get(current.symbol_id, set()):
                return None
            matches = [s for s in file.symbols if s.name == name and s.parent_symbol_id == current.symbol_id]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return None
            if name in file.shadowed.get(current.symbol_id, set()):
                return None
            current = symbols.get(current.parent_symbol_id)
        if name in file.reassigned.get("<module>", set()):
            return None
        if name in file.shadowed.get("<module>", set()) and name not in {s.name for s in file.symbols if s.parent_symbol_id is None}:
            return None
        if name in file.imports:
            return imported(file, name)
        matches = [s for s in file.symbols if s.name == name and s.parent_symbol_id is None]
        return matches[0] if len(matches) == 1 else None

    def method(class_symbol, name: str):
        if not class_symbol or class_symbol.kind != "class":
            return None
        candidates = [s for s in symbols.values() if s.parent_symbol_id == class_symbol.symbol_id and s.name == name and s.kind in CALLABLE]
        if any(s.method_kind != "normal" for s in candidates):
            return None
        return candidates[0] if len(candidates) == 1 else None

    def binding(file: ParsedFile, scope: str, receiver: str):
        current = symbols.get(scope)
        while current:
            bindings = file.bindings.get(current.symbol_id, {})
            if receiver in bindings:
                return bindings[receiver]
            if receiver in file.shadowed.get(current.symbol_id, set()):
                return None
            current = symbols.get(current.parent_symbol_id)
        return file.bindings.get("<module>", {}).get(receiver)

    for file in sorted(files, key=lambda f: f.path):
        resolved_calls = []
        for call in file.calls:
            if file.has_errors:
                unresolved.append({**call, "evidence_type": "UNRESOLVED", "reason": "PARSE_ERROR"})
                continue
            caller = symbols.get(call["source"])
            parent = symbols.get(caller.parent_symbol_id) if caller else None
            nested = bool(parent and parent.kind != "class")
            # Calls from nested functions/callbacks resolve only plain identifiers, through the same scope-chain
            # lookup (parameters, local declarations and reassignments are honoured at every enclosing level).
            # Member calls from nested scopes stay unresolved: their receiver/`this` is not statically known.
            if caller and (caller.method_kind != "normal" or (nested and (not NESTED_IDENTIFIER_CALLS or call["callee_type"] != "identifier"))):
                unresolved.append({**call, "evidence_type": "UNRESOLVED", "reason": "Unsupported method or nested callback scope"})
                continue
            callee, target, how = call["callee"], None, ""
            scope = call["source"]
            if call["callee_type"] == "identifier":
                target = lookup(file, callee, scope)
                how = "named_or_default_import" if callee in file.imports else "lexical_scope"
                if nested:
                    how += "_nested"
            elif call["callee_type"] == "member_expression" and re.fullmatch(r"(?:this\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", callee):
                receiver, name = callee.rsplit(".", 1)
                if receiver == "this":
                    target = method(symbols.get(call["class"]), name)
                    if "this." + name in file.bindings.get(call["class"], {}) or "<computed-write>" in file.bindings.get(call["class"], {}):
                        target = None
                    how = "same_class_method"
                elif receiver in file.imports and file.imports[receiver]["name"] == "*" and receiver not in file.shadowed.get(scope, set()):
                    target = imported(file, receiver, name)
                    how = "namespace_import"
                elif receiver.startswith("this."):
                    if "<computed-write>" in file.bindings.get(call["class"], {}):
                        unresolved.append({**call, "evidence_type": "UNRESOLVED", "reason": "Computed property mutation in class"})
                        continue
                    class_name = binding(file, call["class"] if receiver.startswith("this.") and call["class"] else scope, receiver)
                    assignment = file.binding_spans.get(call["class"], {}).get(receiver)
                    cls = lookup(file, class_name, assignment["source_symbol_id"]) if class_name and assignment else None
                    target = method(cls, name)
                    how = "constructor_instance"
            if target and by_file[target.file_path].has_errors:
                target = None
            if target and target.kind in CALLABLE and target.symbol_id in symbols:
                edge = Edge(scope, target.symbol_id, "CALLS", call["file"], call["line"], call["end_line"],
                            call["start_byte"], call["end_byte"], call["expression"], how)
                edges.append(edge)
                edge.supporting_spans.append({"file_path": call["file"], "start_line": call["line"],
                    "end_line": call["end_line"], "start_byte": call["start_byte"], "end_byte": call["end_byte"], "kind": "call_site"})
                import_name = callee
                if how == "constructor_instance":
                    import_name = class_name
                    assignment = file.binding_spans.get(call["class"], {}).get(receiver)
                    if assignment:
                        edge.supporting_spans.append(assignment)
                declaration = file.imports.get(import_name, {}).get("span")
                if declaration:
                    edge.supporting_spans.append(declaration)
                resolved_calls.append((call, edge))
            else:
                unresolved.append({**call, "evidence_type": "UNRESOLVED", "reason": "No unambiguous supported binding; shadowed, reassigned, dynamic or external call"})
        grouped = {}
        for call, edge in resolved_calls:
            if call["sequence_eligible"]:
                grouped.setdefault(call["source"], []).append((call, edge))
        for caller, calls in grouped.items():
            calls.sort(key=lambda pair: pair[0]["statement_byte"])
            for i, (first, before) in enumerate(calls):
                for second, after in calls[i + 1:]:
                    if first["statement_byte"] < second["statement_byte"]:
                        sequences.append({"caller": caller, "before": before.target_symbol_id,
                                          "after": after.target_symbol_id, "before_line": before.call_line,
                                          "after_line": after.call_line, "file_path": file.path,
                                          "evidence_type": "STATIC_VERIFIED", "relation": "LEXICAL_BEFORE",
                                          "explanation": "Direct calls in separate statements of the same function body. Lexical order only; completion is not guaranteed."})
    return sorted(edges, key=lambda e: (e.call_file, e.call_start_byte, e.target_symbol_id)), unresolved, sequences

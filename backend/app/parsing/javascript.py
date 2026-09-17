"""Tree-sitter extraction. Coordinates are UTF-8 bytes and inclusive 1-based lines."""
import hashlib
import re
from collections import Counter

import tree_sitter_javascript
from tree_sitter import Language, Node, Parser

from backend.app.models.entities import Chunk, ParsedFile, Symbol

LANGUAGE = Language(tree_sitter_javascript.language())
FUNCTIONS = {"function_declaration", "generator_function_declaration", "function_expression", "generator_function", "arrow_function"}
CALLABLE = {"function", "arrow_function", "method", "test", "module"}


def walk(node: Node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def value(node: Node | None, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8") if node else ""


def field(node: Node, name: str) -> Node | None:
    return node.child_by_field_name(name)


def identifiers(node: Node | None, source: bytes) -> list[str]:
    return [value(n, source) for n in walk(node) if n.type in {"identifier", "shorthand_property_identifier_pattern"}] if node else []


def parse_file(path: str, source_text: str) -> ParsedFile:
    source = source_text.encode("utf-8")
    tree = Parser(LANGUAGE).parse(source)
    parsed = ParsedFile(path, source_text)
    is_test = bool(re.search(r"(?:^|/)__tests__/|\.(?:test|spec)\.[cm]?jsx?$", path))
    if tree.root_node.has_error:
        parsed.diagnostics.append(f"{path}: parser recovered from syntax errors; invalid spans are not resolved")
    node_symbols: dict[int, Symbol] = {}
    name_counts: Counter = Counter()

    def create(node: Node, name: str, kind: str, parent: Symbol | None, params: Node | None = None):
        qualified = f"{parent.qualified_name}.{name}" if parent else name
        name_counts[qualified] += 1
        if name_counts[qualified] > 1:
            qualified += f"@{node.start_point.row + 1}"
        text = value(node, source)
        symbol = Symbol(f"{path}::{qualified}", qualified, name, kind, path,
                        node.start_point.row + 1, node.end_point.row + 1,
                        node.start_byte, node.end_byte, parent.symbol_id if parent else None,
                        text, hashlib.sha256(text.encode()).hexdigest(), identifiers(params, source), is_test)
        parsed.symbols.append(symbol)
        node_symbols[node.id] = symbol
        parsed.shadowed[symbol.symbol_id] = set(symbol.parameters)
        return symbol

    def discover(node: Node, parent: Symbol | None = None):
        current = parent
        if node.type in {"class_declaration", "class"}:
            current = create(node, value(field(node, "name"), source) or "default", "class", parent)
        elif node.type == "method_definition":
            current = create(node, value(field(node, "name"), source), "method", parent, field(node, "parameters"))
        elif node.type in FUNCTIONS:
            name = value(field(node, "name"), source)
            container = node.parent
            kind = "arrow_function" if node.type == "arrow_function" else "function"
            span = node
            if container and container.type == "variable_declarator":
                name = value(field(container, "name"), source)
                span = container
            elif container and container.type in {"field_definition", "public_field_definition"}:
                name = value(field(container, "property"), source) or value(field(container, "name"), source)
                span, kind = container, "method"
            elif container and container.type == "arguments" and container.parent.type == "call_expression":
                call = container.parent
                callee = value(field(call, "function"), source)
                if is_test and callee in {"test", "it", "test.only", "it.only"}:
                    args = container.named_children
                    name = "test:" + value(args[0], source).strip("\"'`")
                    kind = "test"
                else:
                    # Preserve callback scope so calls inside it aren't attributed to outer functions.
                    name = f"callback@{node.start_point.row + 1}:{node.start_point.column}"
            elif container and container.type == "export_statement" and not name:
                name = "default"
            if not name:
                name = f"anonymous@{node.start_point.row + 1}:{node.start_point.column}"
            current = create(span, name, kind, parent, field(node, "parameters") or field(node, "parameter"))
            node_symbols[node.id] = current
        for child in node.named_children:
            discover(child, current)

    discover(tree.root_node)
    top = {s.name: s for s in parsed.symbols if s.parent_symbol_id is None}
    for node in tree.root_node.named_children:
        if node.type == "import_statement":
            module = value(field(node, "source"), source).strip("\"'")
            clause = next((n for n in node.named_children if n.type == "import_clause"), None)
            if clause:
                for child in clause.named_children:
                    if child.type == "identifier":
                        parsed.imports[value(child, source)] = {"module": module, "name": "default"}
                    elif child.type == "namespace_import":
                        parsed.imports[value(child.named_children[-1], source)] = {"module": module, "name": "*"}
                    elif child.type == "named_imports":
                        for spec in child.named_children:
                            original = value(field(spec, "name"), source)
                            alias = value(field(spec, "alias"), source) or original
                            if original:
                                parsed.imports[alias] = {"module": module, "name": original}
        if node.type == "export_statement":
            declaration = field(node, "declaration") or field(node, "value")
            if declaration:
                if declaration.type == "identifier" and value(declaration, source) in top:
                    parsed.exports["default"] = top[value(declaration, source)].symbol_id
                exported = [s for s in parsed.symbols if s.parent_symbol_id is None and declaration.start_byte <= s.start_byte < declaration.end_byte]
                for s in exported:
                    key = "default" if any(c.type == "default" for c in node.children) else s.name
                    parsed.exports[key] = s.symbol_id
            for spec in (n for n in walk(node) if n.type == "export_specifier"):
                original = value(field(spec, "name"), source)
                alias = value(field(spec, "alias"), source) or original
                if original in top and not field(node, "source"):
                    parsed.exports[alias] = top[original].symbol_id

    callables = [s for s in parsed.symbols if s.kind in CALLABLE]
    if not callables and source.strip():
        # Only files without callable units receive bounded module chunks.
        lines = source_text.splitlines(keepends=True)
        offset = 0
        for index in range(0, len(lines), 80):
            text = "".join(lines[index:index + 80])
            data = text.encode()
            name = f"<module:{index // 80 + 1}>"
            symbol = Symbol(f"{path}::{name}", name, name, "module", path, index + 1,
                            index + len(lines[index:index + 80]), offset, offset + len(data), None, text,
                            hashlib.sha256(data).hexdigest(), [], is_test)
            parsed.symbols.append(symbol)
            offset += len(data)
        callables = [s for s in parsed.symbols if s.kind in CALLABLE]

    def owner(node: Node):
        candidates = [s for s in callables if s.start_byte <= node.start_byte and node.end_byte <= s.end_byte]
        return min(candidates, key=lambda s: s.end_byte - s.start_byte) if candidates else None

    by_id = {s.symbol_id: s for s in parsed.symbols}
    body_by_symbol = {node_symbols[n.id].symbol_id: field(n, "body")
                      for n in walk(tree.root_node) if n.id in node_symbols and field(n, "body")}

    def class_for(symbol: Symbol | None):
        while symbol:
            if symbol.kind == "class":
                return symbol
            if symbol.kind == "function":
                return None  # Ordinary nested functions do not inherit the class's `this`.
            symbol = by_id.get(symbol.parent_symbol_id)
        return None

    def bind(scope: str, name: str, expression: Node | None):
        bindings = parsed.bindings.setdefault(scope, {})
        # Multiple assignments invalidate a simple instance binding.
        if name in bindings:
            bindings[name] = ""
        elif expression and expression.type == "new_expression":
            bindings[name] = value(field(expression, "constructor"), source)
        else:
            bindings[name] = ""

    for node in walk(tree.root_node):
        current = owner(node)
        scope = current.symbol_id if current else "<module>"
        if node.type == "variable_declarator":
            name_node = field(node, "name")
            for name in identifiers(name_node, source):
                parsed.shadowed.setdefault(scope, set()).add(name)
            if name_node and name_node.type == "identifier":
                bind(scope, value(name_node, source), field(node, "value"))
        if node.type == "assignment_expression":
            name = value(field(node, "left"), source)
            cls = class_for(current)
            parsed.reassigned.setdefault(scope, set()).add(name)
            # A constructor assignment is a class-wide binding. Reassignments anywhere invalidate it.
            bind(cls.symbol_id if cls and name.startswith("this.") else scope, name, field(node, "right"))
        if node.type in {"field_definition", "public_field_definition"}:
            candidates = [s for s in parsed.symbols if s.kind == "class" and s.start_byte <= node.start_byte < s.end_byte]
            if candidates:
                cls = min(candidates, key=lambda s: s.end_byte - s.start_byte)
                name = value(field(node, "property") or field(node, "name"), source)
                bind(cls.symbol_id, "this." + name, field(node, "value"))
        if node.type == "call_expression" and current and not node.has_error:
            callee = field(node, "function")
            expression = value(callee, source)
            cls = class_for(current)
            statement = node
            # Only direct call expressions (possibly assigned, returned, or awaited)
            # qualify for lexical sequence evidence. Nested calls/branches do not.
            while statement.parent and statement.parent.type in {"await_expression", "return_statement", "expression_statement", "variable_declarator", "lexical_declaration", "variable_declaration"}:
                statement = statement.parent
            block = statement.parent
            body = body_by_symbol.get(current.symbol_id)
            direct = bool(block and body and block.id == body.id and statement.type in {"return_statement", "expression_statement", "lexical_declaration", "variable_declaration"})
            parsed.calls.append({"source": current.symbol_id, "callee": expression,
                                 "callee_type": callee.type if callee else "", "class": cls.symbol_id if cls else None,
                                 "file": path, "line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
                                 "start_byte": node.start_byte, "end_byte": node.end_byte,
                                 "expression": value(node, source),
                                 "statement_byte": statement.start_byte if direct else None,
                                 "sequence_eligible": direct})

    # Chunk source spans remain exact; comment/import context only enriches search_text.
    nodes_by_start = {n.start_byte: n for n in walk(tree.root_node)}
    for symbol in callables:
        node = nodes_by_start.get(symbol.start_byte)
        comments = []
        previous = node.prev_named_sibling if node else None
        if node and node.parent and node.parent.type in {"export_statement", "lexical_declaration"}:
            previous = node.parent.prev_named_sibling
        while previous and previous.type == "comment" and symbol.start_line - previous.end_point.row <= 3:
            comments.insert(0, value(previous, source))
            previous = previous.prev_named_sibling
        used_imports = [name for name in parsed.imports if re.search(r"\b" + re.escape(name) + r"\b", symbol.source_text)]
        search_text = "\n".join([path, symbol.qualified_name, " ".join(used_imports), *comments, symbol.source_text])
        parsed.chunks.append(Chunk(symbol.symbol_id, symbol.symbol_id, path, symbol.qualified_name,
                                   symbol.kind, symbol.start_line, symbol.end_line, symbol.source_text,
                                   search_text, symbol.content_hash, is_test=is_test))
    return parsed

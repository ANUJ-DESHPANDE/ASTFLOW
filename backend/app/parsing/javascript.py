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


EXPORT_MEMBER = re.compile(r"(?:module\.)?exports\.([A-Za-z_$][\w$]*)")
ALIAS_MEMBER = re.compile(r"([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)")


def commonjs(root: Node, source: bytes, parsed: ParsedFile, top: dict[str, Symbol], span):
    """Top-level CommonJS: relative `require()` bindings and `module.exports` / `exports.x` / export-object members.

    Only statically unambiguous forms are recorded; an export key assigned two different values is dropped.
    """
    def required(node):
        if node is not None and node.type == "call_expression" and value(field(node, "function"), source) == "require":
            args = field(node, "arguments")
            items = args.named_children if args else []
            if len(items) == 1 and items[0].type == "string":
                module = value(items[0], source).strip("\"'")
                return module if module.startswith(".") else None
        return None

    def add_import(alias, module, name, node):
        parsed.imports[alias] = {"module": module, "name": name, "supported": True, "cjs": True, "span": span(node, "require")}

    def chain(node):  # a = b = c = VALUE -> (["a", "b", "c"], VALUE)
        lefts = []
        while node is not None and node.type == "assignment_expression":
            lefts.append(value(field(node, "left"), source))
            node = field(node, "right")
        return lefts, node

    def target(expression):
        if expression is None:
            return None
        if expression.type == "identifier":
            symbol = top.get(value(expression, source))
            return symbol if symbol and symbol.kind in CALLABLE | {"class"} else None
        if expression.type in FUNCTIONS | {"class"}:
            return next((s for s in parsed.symbols if s.parent_symbol_id is None and s.start_byte == expression.start_byte), None)
        return None

    statements = []  # (declared name or None, assignment targets, assigned value, statement)
    for node in root.named_children:
        if node.type in {"lexical_declaration", "variable_declaration"}:
            for declarator in (d for d in node.named_children if d.type == "variable_declarator"):
                lefts, rhs = chain(field(declarator, "value"))
                name_node = field(declarator, "name")
                statements.append((name_node, lefts, rhs, node))
        elif node.type == "expression_statement" and node.named_children and node.named_children[0].type == "assignment_expression":
            lefts, rhs = chain(node.named_children[0])
            statements.append((None, lefts, rhs, node))

    aliases = set()  # top-level variables that *are* the export object (`var app = module.exports = {}`, `module.exports = res`)
    for name_node, lefts, rhs, _ in statements:
        if "module.exports" in lefts:
            if name_node is not None and name_node.type == "identifier":
                aliases.add(value(name_node, source))
            if rhs is not None and rhs.type == "identifier" and value(rhs, source) not in top:
                aliases.add(value(rhs, source))

    exports: dict[str, str | None] = {}

    def export(key, symbol):
        if symbol is None:
            return
        exports[key] = symbol.symbol_id if exports.get(key, symbol.symbol_id) == symbol.symbol_id else None

    for name_node, lefts, rhs, node in statements:
        if name_node is not None and not lefts:
            module = required(rhs)
            if module and name_node.type == "identifier":
                add_import(value(name_node, source), module, "*", node)
            elif module and name_node.type == "object_pattern":
                for item in name_node.named_children:
                    if item.type == "shorthand_property_identifier_pattern":
                        add_import(value(item, source), module, value(item, source), node)
                    elif item.type == "pair_pattern" and field(item, "value").type == "identifier":
                        add_import(value(field(item, "value"), source), module, value(field(item, "key"), source), node)
            elif rhs is not None and rhs.type == "member_expression" and name_node.type == "identifier":
                module = required(field(rhs, "object"))
                if module:
                    add_import(value(name_node, source), module, value(field(rhs, "property"), source), node)
        for left in lefts:
            member = EXPORT_MEMBER.fullmatch(left)
            alias = ALIAS_MEMBER.fullmatch(left)
            if left == "module.exports":
                if rhs is not None and rhs.type == "object":
                    for item in rhs.named_children:
                        if item.type == "shorthand_property_identifier":
                            export(value(item, source), target(item) or top.get(value(item, source)))
                        elif item.type == "pair":
                            export(value(field(item, "key"), source).strip("\"'"), target(field(item, "value")))
                else:
                    export("*", target(rhs))
            elif member:
                export(member.group(1), target(rhs))
            elif alias and alias.group(1) in aliases:
                export(alias.group(2), target(rhs))
    for key, symbol_id in exports.items():
        if symbol_id and key not in parsed.exports:
            parsed.exports[key] = symbol_id


def parse_file(path: str, source_text: str) -> ParsedFile:
    source = source_text.encode("utf-8")
    tree = Parser(LANGUAGE).parse(source)
    parsed = ParsedFile(path, source_text)
    is_test = bool(re.search(r"(?:^|/)__tests__/|\.(?:test|spec)\.[cm]?jsx?$", path))
    if tree.root_node.has_error:
        parsed.has_errors = True
        parsed.diagnostics.append(f"{path}: syntax errors; structural resolution disabled for this file")
    node_symbols: dict[int, Symbol] = {}
    name_counts: Counter = Counter()

    def create(node: Node, name: str, kind: str, parent: Symbol | None, params: Node | None = None):
        qualified = f"{parent.qualified_name}.{name}" if parent else name
        name_counts[qualified] += 1
        if name_counts[qualified] > 1:
            qualified += f"@{node.start_byte}"
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
            current.method_kind = next((c.type for c in node.children if c.type in {"static", "get", "set", "*"}), "normal")
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
            elif container and container.type == "assignment_expression" and not name:
                # `exports.parse = function () {}`, `res.links = function () {}` -> "parse", "links";
                # `var proto = module.exports = function () {}` -> "proto".
                left = field(container, "left")
                if value(left, source) == "module.exports":
                    outer = container.parent
                    while outer and outer.type == "assignment_expression":
                        outer = outer.parent
                    if outer and outer.type == "variable_declarator" and field(outer, "name").type == "identifier":
                        name = value(field(outer, "name"), source)
                elif left and left.type == "member_expression":
                    name = value(field(left, "property"), source)
            if not name:
                name = f"anonymous@{node.start_point.row + 1}:{node.start_point.column}"
            current = create(span, name, kind, parent, field(node, "parameters") or field(node, "parameter"))
            if kind == "method":
                current.method_kind = "field"
            node_symbols[node.id] = current
        for child in node.named_children:
            discover(child, current)

    discover(tree.root_node)
    def span(node, kind):
        return {"file_path": path, "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1, "start_byte": node.start_byte,
                "end_byte": node.end_byte, "kind": kind}

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
                                parsed.imports[alias] = {"module": module, "name": original,
                                                         "supported": alias == original and module.startswith("."),
                                                         "span": span(node, "import")}
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

    commonjs(tree.root_node, source, parsed, top, span)

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
        if node.type in {"catch_clause", "for_in_statement"}:
            binding_node = field(node, "parameter") if node.type == "catch_clause" else field(node, "left")
            parsed.shadowed.setdefault(scope, set()).update(identifiers(binding_node, source))
        if node.type == "variable_declarator":
            name_node = field(node, "name")
            for name in identifiers(name_node, source):
                parsed.shadowed.setdefault(scope, set()).add(name)
            if name_node and name_node.type == "identifier":
                bind(scope, value(name_node, source), field(node, "value"))
        if node.type in {"assignment_expression", "augmented_assignment_expression", "update_expression", "unary_expression"}:
            if node.type == "unary_expression" and not value(node, source).lstrip().startswith("delete "):
                continue
            name = value(field(node, "left") or field(node, "argument"), source)
            cls = class_for(current)
            left = field(node, "left") or field(node, "argument")
            if cls and left and left.type == "subscript_expression" and value(field(left, "object"), source) == "this":
                parsed.bindings.setdefault(cls.symbol_id, {})["<computed-write>"] = ""
            parsed.reassigned.setdefault(scope, set()).add(name)
            binding_scope = cls.symbol_id if cls and name.startswith("this.") else scope
            body = body_by_symbol.get(scope)
            direct_constructor = bool(current and current.name == "constructor" and body
                                      and node.parent and node.parent.type == "expression_statement"
                                      and node.parent.parent == body and node.type == "assignment_expression")
            bind(binding_scope, name, field(node, "right") if direct_constructor else None)
            if direct_constructor:
                parsed.binding_spans.setdefault(binding_scope, {})[name] = {**span(node, "constructor_assignment"), "source_symbol_id": scope}
        if node.type in {"field_definition", "public_field_definition"}:
            candidates = [s for s in parsed.symbols if s.kind == "class" and s.start_byte <= node.start_byte < s.end_byte]
            if candidates:
                cls = min(candidates, key=lambda s: s.end_byte - s.start_byte)
                name = value(field(node, "property") or field(node, "name"), source)
                bind(cls.symbol_id, "this." + name, None)
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
            if body and any(n.type in {"return_statement", "throw_statement", "if_statement", "switch_statement", "try_statement", "for_statement", "for_in_statement", "while_statement", "do_statement", "await_expression", "yield_expression"} for n in walk(body)):
                direct = False
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

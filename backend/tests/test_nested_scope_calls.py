"""Calls made inside nested functions and callbacks (F-023).

Real repositories put most calls inside nested scopes (IIFE-wrapped libraries, route handlers, callbacks). Plain
identifier calls from those scopes resolve through the same scope-chain lookup as top-level calls; member calls from
nested scopes stay unresolved because their receiver is not statically known.
"""
from backend.app.parsing.javascript import parse_file
from backend.app.structure.resolver import resolve_structure


def resolve(source: str):
    edges, unresolved, _ = resolve_structure([parse_file("lib.js", source)])
    return {(e.source_symbol_id.split("::")[1], e.target_symbol_id.split("::")[1], e.resolution_method) for e in edges}, unresolved


def test_identifier_call_from_nested_function_resolves_to_top_level_function():
    edges, _ = resolve("function helper() { return 1; }\nfunction outer() {\n  function inner() { return helper(); }\n  return inner();\n}\n")
    assert ("outer.inner", "helper", "lexical_scope_nested") in edges
    # The enclosing function's own call is a top-level scope call, unchanged.
    assert ("outer", "outer.inner", "lexical_scope") in edges


def test_callback_resolves_function_declared_in_enclosing_scope():
    edges, _ = resolve("function run(items) {\n  function check(x) { return x > 0; }\n  return items.filter(function (x) { return check(x); });\n}\n")
    assert any(src.startswith("run.callback@") and dst == "run.check" for src, dst, _ in edges)


def test_iife_wrapped_library_functions_call_each_other():
    edges, _ = resolve(";(function () {\n  function a() { return b(); }\n  function b() { return 2; }\n  window.lib = { a: a };\n}());\n")
    assert any(src.endswith(".a") and dst.endswith(".b") for src, dst, _ in edges)


def test_parameter_shadowing_in_nested_scope_abstains():
    edges, unresolved = resolve("function helper() {}\nfunction outer(helper) {\n  function inner() { return helper(); }\n  return inner();\n}\n")
    assert not any(dst == "helper" for _, dst, _ in edges)
    assert any(u["callee"] == "helper" for u in unresolved)


def test_reassigned_name_abstains_even_from_nested_scope():
    edges, _ = resolve("function helper() {}\nhelper = function () {};\nfunction outer() { function inner() { helper(); } inner(); }\n")
    assert not any(dst == "helper" for _, dst, _ in edges)


def test_member_call_from_nested_scope_stays_unresolved():
    edges, unresolved = resolve("const api = { go() { return 1; } };\nfunction outer() { function inner() { return api.go(); } return inner(); }\n")
    assert not any(dst.endswith("go") for _, dst, _ in edges)
    assert any(u["callee"] == "api.go" and u["reason"] == "Unsupported method or nested callback scope" for u in unresolved)

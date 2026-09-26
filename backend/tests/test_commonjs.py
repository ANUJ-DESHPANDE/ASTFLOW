from backend.app.parsing.javascript import parse_file
from backend.app.structure.resolver import resolve_structure

UTILS = """
exports.isAbsolute = function(path) { return path[0] === '/'; };
exports.compile = function compile(val) { return val; };
exports.twice = function a() {};
exports.twice = function b() {};
function local() {}
module.exports.local = local;
"""
LAYER = "module.exports = Layer;\nfunction Layer(path) { return path; }\n"
ROUTER_INDEX = "var proto = module.exports = function(options) { return options; };\n"
APP = """
var app = exports = module.exports = {};
app.handle = function handle() { return 1; };
"""
CALLER = """
var utils = require('./utils');
var compile = require('./utils').compile;
var { isAbsolute, local: renamed } = require('./utils');
var Layer = require('./layer');
var Router = require('./router');
var app = require('./app');
var external = require('lodash');
function run(p) {
  compile(p);
  isAbsolute(p);
  renamed();
  utils.twice();
  Layer(p);
  Router({});
  app.handle();
  external.map(p);
}
"""


def resolve():
    files = [parse_file(path, text) for path, text in [
        ("lib/utils.js", UTILS), ("lib/layer.js", LAYER), ("lib/router/index.js", ROUTER_INDEX),
        ("lib/app.js", APP), ("lib/caller.js", CALLER)]]
    edges, unresolved, _ = resolve_structure(files)
    return {(e.source_expression.split("(")[0], e.target_symbol_id): e.resolution_method for e in edges}, unresolved


def test_commonjs_require_forms_resolve_across_files():
    edges, _ = resolve()
    expected = {
        ("compile", "lib/utils.js::compile"),        # require('./utils').compile
        ("isAbsolute", "lib/utils.js::isAbsolute"),  # destructured; anonymous export named by its key
        ("renamed", "lib/utils.js::local"),          # destructured with rename; exported identifier
        ("Layer", "lib/layer.js::Layer"),            # module.exports = Layer (hoisted declaration)
        ("Router", "lib/router/index.js::proto"),    # directory index; `var proto = module.exports = fn`
        ("app.handle", "lib/app.js::handle"),        # member of the export-object alias
    }
    assert expected <= set(edges)
    assert all(edges[key] == "commonjs_require" for key in expected)


def test_commonjs_stays_conservative():
    edges, unresolved = resolve()
    assert not any(target.startswith("lib/utils.js::") and expr == "utils.twice" for expr, target in edges)  # assigned twice
    assert not any(expr == "external.map" for expr, _ in edges)  # package, not a relative module
    assert {c["callee"] for c in unresolved} >= {"utils.twice", "external.map"}


def test_member_assigned_functions_are_named():
    names = {s.qualified_name for s in parse_file("lib/utils.js", UTILS).symbols}
    assert {"isAbsolute", "compile", "local"} <= names
    assert not any(n.startswith("anonymous@") for n in names)

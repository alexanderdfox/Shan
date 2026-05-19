"""Rewrite expression identifiers to _env['name'] for compiled Python."""
from __future__ import annotations

import ast

_BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
_EXTRA = {
    "True", "False", "None", "Half", "Yes", "No", "Span",
    "range", "len", "str", "int", "float", "list", "dict", "set", "tuple",
    "print", "abs", "min", "max", "sum", "sorted", "enumerate", "zip",
    "map", "filter", "reversed", "round", "type", "isinstance", "pow",
    "sqrt", "sin", "cos", "tan", "log", "pi",
    "json_loads", "json_dumps", "sha256",
}
_SKIP = _BUILTINS | _EXTRA


def _collect_comp_targets(node: ast.AST, out: set[str]) -> None:
    if isinstance(node, ast.comprehension):
        _collect_target(node.target, out)
        for iff in node.ifs:
            _collect_comp_targets(iff, out)
        _collect_comp_targets(node.iter, out)
    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        for gen in node.generators:
            _collect_comp_targets(gen, out)
        _collect_comp_targets(node.elt, out)
    elif isinstance(node, ast.DictComp):
        for gen in node.generators:
            _collect_comp_targets(gen, out)
        _collect_comp_targets(node.key, out)
        _collect_comp_targets(node.value, out)
    else:
        for child in ast.iter_child_nodes(node):
            _collect_comp_targets(child, out)


def _collect_target(node: ast.AST, out: set[str]) -> None:
    if isinstance(node, ast.Name):
        out.add(node.id)
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            _collect_target(elt, out)
    elif isinstance(node, ast.List):
        for elt in node.elts:
            _collect_target(elt, out)


def env_expr(source: str, params: set[str] | None = None) -> str:
    if not source or not source.strip():
        return "None"
    params = set(params or ())
    tree = ast.parse(source.strip(), mode="eval")
    comp_locals: set[str] = set()
    _collect_comp_targets(tree, comp_locals)
    scope = params | comp_locals

    class T(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            if node.id in _SKIP or node.id in scope:
                return node
            return ast.Subscript(
                value=ast.Name(id="_env", ctx=ast.Load()),
                slice=ast.Constant(value=node.id),
                ctx=ast.Load(),
            )

    new_body = T().visit(tree.body)
    ast.fix_missing_locations(new_body)
    if hasattr(ast, "unparse"):
        return ast.unparse(new_body)
    raise RuntimeError("Python 3.9+ required for ast.unparse")

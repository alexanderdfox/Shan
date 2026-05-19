"""Compile Python-like expr attributes to JavaScript."""
from __future__ import annotations

import ast

from shan.security import is_dunder

_SKIP_ENV = frozenset(
    {
        "true", "false", "null", "undefined", "console", "JSON", "Math", "Array",
        "Object", "String", "Number", "parseInt", "parseFloat", "env", "api",
        "range", "len",
    }
)

# Python str methods → JavaScript String.prototype (name, arg count or None for variadic)
_STR_METHODS: dict[str, tuple[str, int | None]] = {
    "strip": ("trim", 0),
    "lstrip": ("trimStart", 0),
    "rstrip": ("trimEnd", 0),
    "lower": ("toLowerCase", 0),
    "upper": ("toUpperCase", 0),
    "startswith": ("startsWith", None),
    "endswith": ("endsWith", None),
    "split": ("split", None),
    "replace": ("replace", None),
}


def js_expr(source: str, params: set[str] | None = None) -> str:
    if not source or not source.strip():
        return "null"
    tree = ast.parse(source.strip(), mode="eval")
    comp_locals: set[str] = set()

    def collect_comp(n: ast.AST) -> None:
        if isinstance(n, ast.comprehension):
            _target_names(n.target, comp_locals)
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for g in c.generators:
                    collect_comp(g)
            elif isinstance(c, ast.comprehension):
                collect_comp(c)

    collect_comp(tree)
    params = set(params or ())
    env_scope = params | comp_locals  # names that are NOT env.* prefixed
    return _emit(tree.body, env_scope, params, comp_locals)


def _target_names(node: ast.AST, out: set[str]) -> None:
    if isinstance(node, ast.Name):
        out.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            _target_names(e, out)


def _emit(node: ast.AST, env_scope: set[str], params: set[str], comp_locals: set[str] | None = None) -> str:
    comp_locals = comp_locals or set()
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "null"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, str):
            return repr(node.value)
        return repr(node.value)

    if isinstance(node, ast.Name):
        if node.id in ("True",):
            return "true"
        if node.id in ("False",):
            return "false"
        if node.id in ("None",):
            return "null"
        if node.id in params or node.id in comp_locals:
            return node.id
        if node.id not in _SKIP_ENV:
            return f"env.{node.id}"
        if node.id == "json_dumps":
            return "JSON.stringify"
        if node.id == "json_loads":
            return "JSON.parse"
        if node.id == "len":
            return "len"
        if node.id == "range":
            return "range"
        return f"env.{node.id}"

    if isinstance(node, ast.Attribute):
        if is_dunder(node.attr) or node.attr.startswith("_"):
            raise ValueError(f"disallowed attribute access: {node.attr!r}")
        return f"{_emit(node.value, env_scope, params, comp_locals)}.{node.attr}"

    if isinstance(node, ast.UnaryOp):
        op = "+" if isinstance(node.op, ast.UAdd) else "-" if isinstance(node.op, ast.USub) else "!"
        return f"({op}{_emit(node.operand, env_scope, params, comp_locals)})"

    if isinstance(node, ast.BinOp):
        ops = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.FloorDiv: "/", ast.Mod: "%", ast.Pow: "**",
        }
        return f"({_emit(node.left, env_scope, params, comp_locals)} {ops[type(node.op)]} {_emit(node.right, env_scope, params, comp_locals)})"

    if isinstance(node, ast.BoolOp):
        join = " && " if isinstance(node.op, ast.And) else " || "
        return "(" + join.join(_emit(v, env_scope, params, comp_locals) for v in node.values) + ")"

    if isinstance(node, ast.Compare):
        parts = []
        left = _emit(node.left, env_scope, params, comp_locals)
        for op, comp in zip(node.ops, node.comparators):
            cmps = {
                ast.Eq: "===", ast.NotEq: "!==", ast.Lt: "<", ast.LtE: "<=",
                ast.Gt: ">", ast.GtE: ">=",
            }
            right = _emit(comp, env_scope, params, comp_locals)
            parts.append(f"{left} {cmps[type(op)]} {right}")
            left = right
        return "(" + " && ".join(parts) + ")"

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr in _STR_METHODS:
            js_name, arity = _STR_METHODS[node.func.attr]
            base = _emit(node.func.value, env_scope, params, comp_locals)
            args = [_emit(a, env_scope, params, comp_locals) for a in node.args]
            if arity == 0 and args:
                raise ValueError(f"{node.func.attr}() takes no arguments")
            if arity is not None and arity != len(args) and arity != 0:
                pass  # allow variadic mismatch only for None arity
            return f"String({base}).{js_name}({', '.join(args)})"
        fn = _emit(node.func, env_scope, params, comp_locals)
        args = ", ".join(_emit(a, env_scope, params, comp_locals) for a in node.args)
        return f"{fn}({args})"

    if isinstance(node, ast.List):
        return "[" + ", ".join(_emit(e, env_scope, params, comp_locals) for e in node.elts) + "]"

    if isinstance(node, ast.Tuple):
        return "[" + ", ".join(_emit(e, env_scope, params, comp_locals) for e in node.elts) + "]"

    if isinstance(node, ast.Dict):
        pairs = []
        for k, v in zip(node.keys, node.values):
            key = _emit(k, env_scope, params, comp_locals) if k else "null"
            pairs.append(f"{key}: {_emit(v, env_scope, params, comp_locals)}")
        return "{" + ", ".join(pairs) + "}"

    if isinstance(node, ast.IfExp):
        return f"({_emit(node.test, env_scope, params, comp_locals)} ? {_emit(node.body, env_scope, params, comp_locals)} : {_emit(node.orelse, env_scope, params, comp_locals)})"

    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        gen = node.generators[0]
        if isinstance(gen.target, ast.Name):
            v = gen.target.id
            inner_comp = comp_locals | {v}
            iter_s = _emit(gen.iter, env_scope, params, comp_locals)
            if gen.ifs:
                test = " && ".join(_emit(i, env_scope, params, inner_comp) for i in gen.ifs)
                elt_s = _emit(node.elt, env_scope, params, inner_comp)
                return f"({iter_s}).filter({v} => {test}).map({v} => {elt_s})"
            elt_s = _emit(node.elt, env_scope, params, inner_comp)
            return f"({iter_s}).map({v} => {elt_s})"

    if isinstance(node, ast.Subscript):
        return f"{_emit(node.value, env_scope, params, comp_locals)}[{_emit(node.slice, env_scope, params, comp_locals)}]"

    raise ValueError(f"unsupported expression: {type(node).__name__}")

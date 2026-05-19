"""Safe Python expression evaluator for expr/test/in attributes."""
from __future__ import annotations

import ast
import operator as op
from typing import Any

from shan.security import is_dunder

_ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Subscript,
    ast.Slice,
    ast.Attribute,
    ast.IfExp,
    ast.JoinedStr,
    ast.FormattedValue,
    # operators
    ast.And, ast.Or,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd, ast.MatMult,
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
}
if hasattr(ast, "Index"):
    _ALLOWED_NODES.add(ast.Index)

_BINOPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.MatMult: op.matmul,
    ast.BitOr: op.or_,
    ast.BitXor: op.xor,
    ast.BitAnd: op.and_,
    ast.LShift: op.lshift,
    ast.RShift: op.rshift,
}

_UNARYOPS = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
    ast.Not: op.not_,
    ast.Invert: op.invert,
}

_CMPOPS = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.Is: op.is_,
    ast.IsNot: op.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


_STR_METHODS = frozenset(
    {"strip", "lstrip", "rstrip", "lower", "upper", "startswith", "endswith", "split", "replace"}
)


def _call_method(base: Any, method: str, args: list, kwargs: dict) -> Any:
    if method not in _STR_METHODS:
        raise ValueError(f"method not allowed: {method!r}")
    fn = getattr(base, method, None)
    if fn is None or not callable(fn):
        raise TypeError(f"{type(base).__name__!r} has no method {method!r}")
    return fn(*args, **kwargs)


def _check(node: ast.AST) -> None:
    if type(node) not in _ALLOWED_NODES:
        raise ValueError(f"disallowed expression: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _check(child)


class ExprEval:
    def __init__(self, env: dict[str, Any], builtins: dict[str, Any]):
        self.env = env
        self.builtins = builtins

    def eval(self, source: str) -> Any:
        if not source or not source.strip():
            return None
        tree = ast.parse(source.strip(), mode="eval")
        _check(tree)
        return self._visit(tree.body)

    def _visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            if node.id in self.builtins:
                return self.builtins[node.id]
            raise NameError(f"name '{node.id}' is not defined")
        if isinstance(node, ast.Attribute):
            if is_dunder(node.attr) or node.attr.startswith("_"):
                raise ValueError(f"disallowed attribute access: {node.attr!r}")
            base = self._visit(node.value)
            return getattr(base, node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if is_dunder(node.func.attr) or node.func.attr.startswith("_"):
                    raise ValueError(f"disallowed attribute access: {node.func.attr!r}")
                base = self._visit(node.func.value)
                method = node.func.attr
                args = [self._visit(a) for a in node.args]
                kwargs = {kw.arg: self._visit(kw.value) for kw in node.keywords}
                return _call_method(base, method, args, kwargs)
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct calls to allowed names are permitted")
            if node.func.id not in self.builtins and node.func.id not in self.env:
                raise NameError(f"name '{node.func.id}' is not defined")
            fn = self.builtins.get(node.func.id) or self.env[node.func.id]
            if not callable(fn):
                raise TypeError(f"'{node.func.id}' is not callable")
            args = [self._visit(a) for a in node.args]
            kwargs = {kw.arg: self._visit(kw.value) for kw in node.keywords}
            return fn(*args, **kwargs)
        if isinstance(node, ast.UnaryOp):
            return _UNARYOPS[type(node.op)](self._visit(node.operand))
        if isinstance(node, ast.BinOp):
            return _BINOPS[type(node.op)](self._visit(node.left), self._visit(node.right))
        if isinstance(node, ast.BoolOp):
            vals = [self._visit(v) for v in node.values]
            if isinstance(node.op, ast.And):
                out = vals[0]
                for v in vals[1:]:
                    out = out and v
                return out
            out = vals[0]
            for v in vals[1:]:
                out = out or v
            return out
        if isinstance(node, ast.Compare):
            left = self._visit(node.left)
            for op_node, comp in zip(node.ops, node.comparators):
                right = self._visit(comp)
                if not _CMPOPS[type(op_node)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.List):
            return [self._visit(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._visit(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return {self._visit(k): self._visit(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Set):
            return {self._visit(e) for e in node.elts}
        if isinstance(node, ast.Subscript):
            return self._visit(node.value)[self._visit(node.slice)]
        if isinstance(node, ast.IfExp):
            return self._visit(node.body) if self._visit(node.test) else self._visit(node.orelse)
        if isinstance(node, ast.ListComp):
            return self._listcomp(node)
        if isinstance(node, ast.GeneratorExp):
            return list(self._genexp(node))
        raise ValueError(f"unsupported node {type(node).__name__}")

    def _listcomp(self, node: ast.ListComp) -> list:
        return list(self._genexp_inner(node.generators, 0, lambda: self._visit(node.elt)))

    def _genexp(self, node: ast.GeneratorExp) -> list:
        return list(self._genexp_inner(node.generators, 0, lambda: self._visit(node.elt)))

    def _genexp_inner(self, generators, idx, make_val):
        if idx >= len(generators):
            yield make_val()
            return
        gen = generators[idx]
        iter_val = self._visit(gen.iter)
        for item in iter_val:
            old = self.env.get(gen.target.id) if isinstance(gen.target, ast.Name) else None
            if isinstance(gen.target, ast.Name):
                self.env[gen.target.id] = item
            if gen.ifs:
                ok = all(self._visit(iff) for iff in gen.ifs)
                if not ok:
                    continue
            yield from self._genexp_inner(generators, idx + 1, make_val)
            if isinstance(gen.target, ast.Name):
                if old is None:
                    self.env.pop(gen.target.id, None)
                else:
                    self.env[gen.target.id] = old


def eval_expr(source: str, env: dict[str, Any], builtins: dict[str, Any]) -> Any:
    return ExprEval(env, builtins).eval(source)

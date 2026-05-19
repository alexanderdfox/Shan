"""Shàn reference runtime — fan security + Python-like execution."""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shan.expr import eval_expr
from shan.parser import ShanNode, parse_file, parse_string
from shan.security import resolve_path_under
from shan.stdlib_builtins import build_builtins
from shan.values import Span, Truth, truthy


ROOM_TAGS = {
    "file-read": "files",
    "file-write": "files",
    "fetch": "net",
    "seal": "keys",
    "unseal": "keys",
    "observe": "keys",
}


@dataclass
class AuditEntry:
    room: str
    why: str
    tag: str
    rib: str
    detail: str = ""


@dataclass
class RibContext:
    id: str
    env: dict[str, Any] = field(default_factory=dict)
    functions: dict[str, ShanNode] = field(default_factory=dict)
    classes: dict[str, dict] = field(default_factory=dict)
    modules: dict[str, Any] = field(default_factory=dict)


class ShanRuntime:
    def __init__(self, strict_rooms: bool = True, files_base: Path | None = None):
        self.strict_rooms = strict_rooms
        self.files_base = (files_base or Path.cwd()).resolve()
        self.ribs: dict[str, RibContext] = {}
        self.current_rib: RibContext | None = None
        self.open_rooms: set[str] = set()
        self.audit: list[AuditEntry] = []
        self.builtins = build_builtins(self)
        self._return_value: Any = None
        self._return_flag = False
        self._break_flag = False
        self._continue_flag = False

    def run_file(self, path: Path) -> Any:
        self.files_base = path.parent.resolve()
        node = parse_file(path)
        return self.run_node(node)

    def run_string(self, source: str) -> Any:
        node = parse_string(source)
        return self.run_node(node)

    def run_node(self, node: ShanNode) -> Any:
        if node.tag != "page":
            raise ValueError(f"root must be <page>, got <{node.tag}>")
        for child in node.children:
            if child.tag == "fan":
                self._run_fan(child)
            else:
                self._run_stmt(child)
        return self._return_value

    def _rib(self, rid: str = "default") -> RibContext:
        if rid not in self.ribs:
            self.ribs[rid] = RibContext(id=rid)
        return self.ribs[rid]

    def _env(self) -> dict[str, Any]:
        assert self.current_rib
        return self.current_rib.env

    def _eval(self, expr: str | None, default: Any = None) -> Any:
        if expr is None or expr == "":
            return default
        env = {**self._env(), **self._fn_callables()}
        return eval_expr(expr, env, {**self.builtins, **self._imported()})

    def _fn_callables(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if not self.current_rib:
            return out
        for name, fnode in self.current_rib.functions.items():
            def _make(n: str, node: ShanNode):
                def _call(*args: Any) -> Any:
                    return self._call_fn(node, node.attrs.get("args", "").split(","), None, list(args))

                _call.__name__ = n
                return _call

            out[name] = _make(name, fnode)
        return out

    def _imported(self) -> dict[str, Any]:
        out = {}
        if self.current_rib:
            for name, mod in self.current_rib.modules.items():
                out[name] = mod
        return out

    def _run_fan(self, node: ShanNode) -> None:
        ribs_attr = node.attrs.get("ribs", "4")
        _ = int(ribs_attr)
        rib_nodes = [c for c in node.children if c.tag == "rib"]
        if not rib_nodes:
            self.current_rib = self._rib("default")
            for c in node.children:
                self._run_stmt(c)
            return
        for rib_node in rib_nodes:
            rid = rib_node.attrs.get("id", "default")
            self.current_rib = self._rib(rid)
            self._run_children(rib_node.children)

    def _run_stmt(self, node: ShanNode) -> Any:
        tag = node.tag
        self._check_room(tag)

        if tag in ("page", "fan", "rib", "block"):
            self._run_children(node.children)
            return None

        if tag == "value":
            name = node.attrs["name"]
            if node.attrs.get("expr"):
                val = self._eval(node.attrs["expr"])
            elif node.text:
                val = self._parse_literal(node.text)
            else:
                val = None
            self._env()[name] = val
            return val

        if tag == "set":
            name = node.attrs["name"]
            self._env()[name] = self._eval(node.attrs.get("expr", node.text or "None"))
            return None

        if tag == "list":
            self._env()[node.attrs["name"]] = self._eval(node.attrs["expr"])
            return None

        if tag == "dict":
            self._env()[node.attrs["name"]] = self._eval(node.attrs["expr"])
            return None

        if tag == "del":
            self._env().pop(node.attrs["name"], None)
            return None

        if tag == "half":
            self._env()[node.attrs["name"]] = Truth.HALF
            return None

        if tag == "yes":
            self._env()[node.attrs["name"]] = Truth.YES
            return None

        if tag == "no":
            self._env()[node.attrs["name"]] = Truth.NO
            return None

        if tag == "secret":
            name = node.attrs["name"]
            uses = node.attrs.get("uses")
            uses_int = int(uses) if uses else None
            raw = node.text.strip() if node.text else ""
            self._env()[name] = Span(value=raw, uses_left=uses_int, is_secret=True)
            return None

        if tag == "observe":
            self._require_open("keys")
            name = node.attrs["name"]
            why = node.attrs.get("why", "")
            self.audit.append(
                AuditEntry(room="keys", why=why, tag="observe", rib=self.current_rib.id if self.current_rib else "default")
            )
            val = self._env().get(name)
            if not isinstance(val, Span):
                raise RuntimeError(f"observe: '{name}' is not a secret")
            val.contract()
            self._env()[name + "_observed"] = val.value
            return val.value

        if tag == "show":
            if node.attrs.get("expr"):
                v = self._eval(node.attrs["expr"])
            else:
                v = node.text
            if isinstance(v, Span) and v.is_secret:
                raise RuntimeError("cannot show a secret — use observe inside open room=keys")
            print(v)
            return None

        if tag == "text":
            print(node.text)
            return None

        if tag == "ask":
            prompt = node.attrs.get("prompt", "")
            self._env()[node.attrs["name"]] = input(prompt)
            return None

        if tag == "when":
            if truthy(self._eval(node.attrs["test"])):
                for c in node.children:
                    self._run_stmt(c)
            return None

        if tag == "otherwise":
            for c in node.children:
                self._run_stmt(c)
            return None

        if tag == "each":
            var = node.attrs["var"]
            items = self._eval(node.attrs["in"])
            for item in items:
                if self._break_flag:
                    self._break_flag = False
                    break
                self._env()[var] = item
                for c in node.children:
                    if self._continue_flag:
                        self._continue_flag = False
                        break
                    self._run_stmt(c)
            return None

        if tag == "while":
            while truthy(self._eval(node.attrs["test"])):
                if self._break_flag:
                    self._break_flag = False
                    break
                for c in node.children:
                    if self._continue_flag:
                        self._continue_flag = False
                        break
                    self._run_stmt(c)
            return None

        if tag == "break":
            self._break_flag = True
            return None

        if tag == "continue":
            self._continue_flag = True
            return None

        if tag == "return":
            self._return_value = self._eval(node.attrs.get("expr"))
            self._return_flag = True
            return self._return_value

        if tag == "fn":
            name = node.attrs["name"]
            self.current_rib.functions[name] = node
            return None

        if tag == "call":
            return self._do_call(node)

        if tag == "import":
            if "module" in node.attrs:
                mod = importlib.import_module(node.attrs["module"])
                alias = node.attrs.get("as", node.attrs["module"].split(".")[-1])
                self.current_rib.modules[alias] = mod
                self._env()[alias] = mod
            return None

        if tag == "class":
            self._define_class(node)
            return None

        if tag == "try":
            try:
                for c in node.children:
                    if c.tag not in ("except", "finally"):
                        self._run_stmt(c)
            except Exception as e:
                handled = False
                for c in node.children:
                    if c.tag == "except":
                        exc_name = c.attrs.get("test", "Exception")
                        if self._match_exception(e, exc_name):
                            self._env()["error"] = e
                            for s in c.children:
                                self._run_stmt(s)
                            handled = True
                            break
                if not handled:
                    raise
            finally:
                for c in node.children:
                    if c.tag == "finally":
                        for s in c.children:
                            self._run_stmt(s)
            return None

        if tag == "open":
            room = node.attrs["room"]
            why = node.attrs.get("why", "")
            self.open_rooms.add(room)
            self.audit.append(
                AuditEntry(room=room, why=why, tag="open", rib=self.current_rib.id if self.current_rib else "default")
            )
            try:
                for c in node.children:
                    self._run_stmt(c)
            finally:
                self.open_rooms.discard(room)
            return None

        if tag == "when-half":
            name = node.attrs["name"]
            val = self._env().get(name, Truth.HALF)
            if not isinstance(val, Truth):
                val = Truth.YES if truthy(val) else Truth.NO
            key = {Truth.YES: "yes", Truth.NO: "no", Truth.HALF: "half"}[val]
            for c in node.children:
                if c.tag == "case" and c.attrs.get("value") == key:
                    for s in c.children:
                        self._run_stmt(s)
                    break
            return None

        if tag == "deny":
            raise RuntimeError("access denied (fail closed)")

        if tag == "assert":
            if not truthy(self._eval(node.attrs["test"])):
                raise AssertionError(node.attrs.get("msg", "assertion failed"))
            return None

        if tag == "file-read":
            self._require_open("files")
            path = self._eval(node.attrs["path"])
            result = node.attrs.get("result")
            content = self._safe_read(path)
            if result:
                self._env()[result] = content
            return content

        if tag == "file-write":
            self._require_open("files")
            path = self._eval(node.attrs["path"])
            content = node.attrs.get("content") or self._eval(node.attrs.get("expr", '""'))
            self._safe_write(path, str(content))
            return None

        if tag == "seal":
            self._require_open("keys")
            import hashlib
            data = str(self._eval(node.attrs["expr"]))
            key = str(self._eval(node.attrs["key"]))
            sealed = hashlib.sha256((key + data).encode()).hexdigest()
            if "result" in node.attrs:
                self._env()[node.attrs["result"]] = sealed
            return sealed

        if tag == "unseal":
            raise NotImplementedError("unseal: use observe + application logic in v1")

        if tag == "render":
            return None  # web-only; no-op on desktop runtime

        if tag == "bind":
            return None  # web-only markup

        # unknown: try children only
        for c in node.children:
            self._run_stmt(c)
        return None

    def _run_children(self, children: list[ShanNode]) -> None:
        i = 0
        while i < len(children):
            if self._return_flag:
                return
            n = children[i]
            if n.tag == "when":
                if truthy(self._eval(n.attrs["test"])):
                    for c in n.children:
                        self._run_stmt(c)
                    i += 1
                    if i < len(children) and children[i].tag == "otherwise":
                        i += 1
                elif i + 1 < len(children) and children[i + 1].tag == "otherwise":
                    for c in children[i + 1].children:
                        self._run_stmt(c)
                    i += 2
                else:
                    i += 1
            else:
                self._run_stmt(n)
                i += 1

    def _do_call(self, node: ShanNode) -> Any:
        name = node.attrs["name"]
        args_str = node.attrs.get("args", "")
        args = []
        if args_str.strip():
            args = list(self._eval(f"[{args_str}]"))
        # method call p.dist
        if "." in name:
            obj_name, method = name.split(".", 1)
            obj = self._env().get(obj_name)
            if isinstance(obj, dict) and method in obj.get("_methods", {}):
                mnode = obj["_methods"][method]
                arg_names = mnode.attrs.get("args", "self").split(",")
                res = self._call_fn(mnode, arg_names, obj, args)
                if "result" in node.attrs:
                    self._env()[node.attrs["result"]] = res
                return res
            raise AttributeError(f"{name}")
        # class ctor
        if name in self.current_rib.classes:
            return self._instantiate_class(name, args)
        if name not in self.current_rib.functions:
            # builtin call from expr style
            fn = self.builtins.get(name) or self._env().get(name)
            if callable(fn):
                res = fn(*args)
                if "result" in node.attrs:
                    self._env()[node.attrs["result"]] = res
                return res
            raise NameError(f"function '{name}' not defined")
        fn_node = self.current_rib.functions[name]
        res = self._call_fn(fn_node, fn_node.attrs.get("args", "").split(","), None, args)
        if "result" in node.attrs:
            self._env()[node.attrs["result"]] = res
        return res

    def _call_fn(self, fn_node: ShanNode, arg_names: list[str], self_obj: Any, extra_args: list | None = None) -> Any:
        arg_names = [a.strip() for a in arg_names if a.strip()]
        extra_args = extra_args or []
        saved = dict(self._env())
        try:
            for i, an in enumerate(arg_names):
                if an == "self" and self_obj is not None:
                    self._env()[an] = self_obj
                elif i < len(extra_args):
                    self._env()[an] = extra_args[i]
            self._return_flag = False
            self._run_children(fn_node.children)
            if self._return_flag:
                pass
            return self._return_value
        finally:
            self.current_rib.env = saved

    def _define_class(self, node: ShanNode) -> None:
        name = node.attrs["name"]
        methods = {}
        for c in node.children:
            if c.tag == "fn":
                methods[c.attrs["name"]] = c
        self.current_rib.classes[name] = {"methods": methods}

    def _instantiate_class(self, name: str, args: list) -> dict:
        cls = self.current_rib.classes[name]
        obj = {"_class": name, "_methods": cls["methods"]}
        if "__init__" in cls["methods"]:
            init_node = cls["methods"]["__init__"]
            arg_names = init_node.attrs.get("args", "self").split(",")
            self._call_fn(init_node, arg_names, obj, args)
        return obj

    def _match_exception(self, e: Exception, exc_name: str) -> bool:
        if exc_name == "Exception":
            return True
        return type(e).__name__ == exc_name

    def _require_open(self, room: str) -> None:
        if self.strict_rooms and room not in self.open_rooms:
            raise RuntimeError(f"<{room}> operation requires <open room=\"{room}\" why=\"...\">")

    def _check_room(self, tag: str) -> None:
        room = ROOM_TAGS.get(tag)
        if room:
            self._require_open(room)

    def file_read(self, path: str) -> str:
        self._require_open("files")
        return self._safe_read(path)

    def file_write(self, path: str, content: str) -> None:
        self._require_open("files")
        self._safe_write(path, content)

    def _safe_read(self, path: str | Path) -> str:
        p = resolve_path_under(self.files_base, path)
        return p.read_text(encoding="utf-8")

    def _safe_write(self, path: str | Path, content: str) -> None:
        p = resolve_path_under(self.files_base, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    @staticmethod
    def _parse_literal(text: str) -> Any:
        t = text.strip()
        if t.isdigit() or (t.startswith("-") and t[1:].isdigit()):
            return int(t)
        try:
            return float(t)
        except ValueError:
            pass
        if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
            return t[1:-1]
        return t

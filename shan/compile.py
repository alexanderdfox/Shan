"""Compile .shan → Python for native speed."""
from __future__ import annotations

import textwrap
from pathlib import Path

from shan.compile_expr import env_expr
from shan.parser import ShanNode, parse_file, parse_string

SUPPORT_IMPORT = "from shan.compiled_support import *"

COMPILE_PRELUDE = """
import json as _json
import math as _math

def json_dumps(o):
    return _json.dumps(o)

def json_loads(s):
    return _json.loads(s)

def sqrt(x):
    return _math.sqrt(x)

def sin(x):
    return _math.sin(x)

def cos(x):
    return _math.cos(x)

def tan(x):
    return _math.tan(x)

def log(x):
    return _math.log(x)

pi = _math.pi
""".strip()


class CompileError(Exception):
    pass


class ShanCompiler:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.indent = 0
        self._fn_defs: list[str] = []
        self._params: set[str] = set()

    def compile_file(self, path: Path) -> str:
        return self.compile_node(parse_file(path), module_name=path.stem)

    def compile_string(self, source: str, module_name: str = "main") -> str:
        return self.compile_node(parse_string(source), module_name=module_name)

    def compile_node(self, root: ShanNode, module_name: str = "main") -> str:
        self.lines = []
        self._fn_defs = []
        self._in_fn = False
        if root.tag != "page":
            raise CompileError("root must be <page>")
        title = root.attrs.get("title", module_name)
        self._emit_header(title)
        for child in root.children:
            if child.tag == "fan":
                self._compile_fan(child)
            else:
                self._compile_stmt(child)
        self.indent = 0
        self._emit("")
        self._emit('if __name__ == "__main__":')
        self.indent += 1
        self._emit("_main()")
        self.indent -= 1
        body = "\n".join(self.lines)
        fns = "\n".join(self._fn_defs)
        header = f"{SUPPORT_IMPORT}\n\n{COMPILE_PRELUDE}\n"
        if fns:
            return f"{header}\n{fns}\n\n{body}\n"
        return f"{header}\n{body}\n"

    def _emit_header(self, title: str) -> None:
        self._emit(f'"""Generated from Shàn — {title}"""')
        self._emit("_env: dict = {}")
        self._emit("")
        self._emit("def _main():")
        self.indent = 1

    def _compile_fan(self, node: ShanNode) -> None:
        ribs = [c for c in node.children if c.tag == "rib"]
        if not ribs:
            for c in node.children:
                self._compile_stmt(c)
            return
        for rib in ribs:
            rid = rib.attrs.get("id", "default")
            self._emit(f"# rib: {rid}")
            for c in rib.children:
                self._compile_stmt(c)

    def _compile_children(self, children: list[ShanNode]) -> None:
        i = 0
        while i < len(children):
            n = children[i]
            if n.tag == "when":
                test = self._ex(n.attrs["test"])
                self._emit(f"if {test}:")
                self.indent += 1
                for c in n.children:
                    self._compile_stmt(c)
                self.indent -= 1
                i += 1
                if i < len(children) and children[i].tag == "otherwise":
                    self._emit("else:")
                    self.indent += 1
                    for c in children[i].children:
                        self._compile_stmt(c)
                    self.indent -= 1
                    i += 1
            else:
                self._compile_stmt(n)
                i += 1

    def _compile_stmt(self, node: ShanNode) -> None:
        tag = node.tag
        if tag in ("page", "fan", "rib", "block"):
            self._compile_children(node.children)
            return

        if tag == "fn":
            self._compile_fn(node)
            return

        if tag == "class":
            self._compile_class(node)
            return

        if tag == "value":
            name = node.attrs["name"]
            if node.attrs.get("expr"):
                self._emit(f"_env[{name!r}] = {self._ex(node.attrs['expr'])}")
            elif node.text:
                self._emit(f"_env[{name!r}] = {_py_literal(node.text.strip())}")
            else:
                self._emit(f"_env[{name!r}] = None")
            return

        if tag == "set":
            name = node.attrs["name"]
            expr = self._ex(node.attrs.get("expr", node.text or "None"))
            self._emit(f"_env[{name!r}] = {expr}")
            return

        if tag == "list":
            self._emit(f"_env[{node.attrs['name']!r}] = {self._ex(node.attrs['expr'])}")
            return

        if tag == "dict":
            self._emit(f"_env[{node.attrs['name']!r}] = {self._ex(node.attrs['expr'])}")
            return

        if tag == "del":
            self._emit(f"_env.pop({node.attrs['name']!r}, None)")
            return

        if tag == "half":
            self._emit(f"_env[{node.attrs['name']!r}] = Half")
            return

        if tag == "yes":
            self._emit(f"_env[{node.attrs['name']!r}] = Yes")
            return

        if tag == "no":
            self._emit(f"_env[{node.attrs['name']!r}] = No")
            return

        if tag == "secret":
            name = node.attrs["name"]
            uses = node.attrs.get("uses")
            uses_expr = "None" if uses is None else uses
            val = _py_literal((node.text or "").strip())
            self._emit(f"_env[{name!r}] = Span({val}, uses_left={uses_expr})")
            return

        if tag == "observe":
            name = node.attrs["name"]
            why = node.attrs.get("why", "")
            self._emit(
                f"_env[{name + '_observed'!r}] = shan_observe(_env[{name!r}], {why!r})"
            )
            return

        if tag == "show":
            if node.attrs.get("expr"):
                self._emit(f"print({self._ex(node.attrs['expr'])})")
            else:
                self._emit(f"print({_py_literal(node.text)})")
            return

        if tag == "text":
            self._emit(f"print({_py_literal(node.text)})")
            return

        if tag == "ask":
            self._emit(f"_env[{node.attrs['name']!r}] = input({node.attrs.get('prompt', '')!r})")
            return

        if tag == "each":
            var = node.attrs["var"]
            self._emit(f"for {var} in {self._ex(node.attrs['in'])}:")
            self.indent += 1
            self._compile_children(node.children)
            self.indent -= 1
            return

        if tag == "while":
            self._emit(f"while {self._ex(node.attrs['test'])}:")
            self.indent += 1
            self._compile_children(node.children)
            self.indent -= 1
            return

        if tag == "break":
            self._emit("break")
            return

        if tag == "continue":
            self._emit("continue")
            return

        if tag == "return":
            expr = self._ex(node.attrs.get("expr", "None"))
            self._emit(f"return {expr}")
            return

        if tag == "call":
            self._compile_call(node)
            return

        if tag == "import":
            mod = node.attrs.get("module")
            if mod:
                alias = node.attrs.get("as", mod.split(".")[-1])
                self._emit(f"import {mod} as {alias}")
                self._emit(f"_env[{alias!r}] = {alias}")
            return

        if tag == "open":
            room = node.attrs["room"]
            why = node.attrs.get("why", "")
            self._emit(f"with shan_open({room!r}, {why!r}):")
            self.indent += 1
            self._compile_children(node.children)
            self.indent -= 1
            return

        if tag == "when-half":
            name = node.attrs["name"]
            self._emit(f"_half_key = match_half(_env.get({name!r}, Half))")
            first = True
            for c in node.children:
                if c.tag == "case":
                    val = c.attrs["value"]
                    kw = "if" if first else "elif"
                    first = False
                    self._emit(f"{kw} _half_key == {val!r}:")
                    self.indent += 1
                    self._compile_children(c.children)
                    self.indent -= 1
            if first:
                self._emit("pass")
            return

        if tag == "deny":
            self._emit('raise RuntimeError("access denied")')
            return

        if tag == "assert":
            msg = node.attrs.get("msg", "assertion failed")
            self._emit(f"assert {self._ex(node.attrs['test'])}, {msg!r}")
            return

        if tag == "try":
            self._emit("try:")
            self.indent += 1
            for c in node.children:
                if c.tag not in ("except", "finally"):
                    self._compile_stmt(c)
            self.indent -= 1
            for c in node.children:
                if c.tag == "except":
                    exc = c.attrs.get("test", "Exception")
                    self._emit(f"except {exc} as error:")
                    self.indent += 1
                    self._emit("_env['error'] = error")
                    self._compile_children(c.children)
                    self.indent -= 1
            for c in node.children:
                if c.tag == "finally":
                    self._emit("finally:")
                    self.indent += 1
                    self._compile_children(c.children)
                    self.indent -= 1
            return

        if tag == "file-read":
            path = self._ex(node.attrs["path"])
            res = node.attrs.get("result")
            if res:
                self._emit(f"_env[{res!r}] = shan_file_read({path})")
            else:
                self._emit(f"shan_file_read({path})")
            return

        if tag == "file-write":
            path = self._ex(node.attrs["path"])
            content = self._ex(node.attrs.get("expr") or node.attrs.get("content", '""'))
            self._emit(f"shan_file_write(str({path}), str({content}))")
            return

        if tag == "seal":
            res = node.attrs.get("result", "_sealed")
            self._emit(
                f"_env[{res!r}] = shan_seal({self._ex(node.attrs['expr'])}, {self._ex(node.attrs['key'])})"
            )
            return

        for c in node.children:
            self._compile_stmt(c)

    def _compile_fn(self, node: ShanNode) -> None:
        name = node.attrs["name"]
        args = node.attrs.get("args", "").strip()
        arglist = ", ".join(a.strip() for a in args.split(",") if a.strip()) if args else ""
        params = {a.strip() for a in args.split(",") if a.strip()} | {name}
        body_lines: list[str] = []
        saved = self.lines
        saved_indent = self.indent
        saved_params = self._params
        self._params = params
        self.lines = body_lines
        self.indent = 1
        self._compile_children(node.children)
        self._params = saved_params
        self.lines = saved
        self.indent = saved_indent
        fn_body = textwrap.indent("\n".join(body_lines) or "pass", "    ")
        self._fn_defs.append(f"def {name}({arglist}):\n{fn_body}")
        self._emit(f"_env[{name!r}] = {name}")

    def _ex(self, source: str) -> str:
        try:
            return env_expr(source, self._params)
        except Exception:
            return source

    def _compile_class(self, node: ShanNode) -> None:
        name = node.attrs["name"]
        self._emit(f"class {name}:")
        self.indent += 1
        for c in node.children:
            if c.tag == "fn":
                mname = c.attrs["name"]
                args = c.attrs.get("args", "self")
                body_lines: list[str] = []
                saved, saved_i = self.lines, self.indent
                self.lines, self.indent = body_lines, 2
                self._compile_children(c.children)
                self.lines, self.indent = saved, saved_i
                fn_body = textwrap.indent("\n".join(body_lines) or "pass", "        ")
                self._fn_defs.append(f"class {name}:\n    def {mname}({args}):\n{fn_body}")
        self._emit(f"_env[{name!r}] = {name}")
        self.indent -= 1

    def _compile_call(self, node: ShanNode) -> None:
        name = node.attrs["name"]
        args = node.attrs.get("args", "")
        result = node.attrs.get("result")
        if "." in name:
            obj, meth = name.split(".", 1)
            call = f"_env[{obj!r}].{meth}({args})"
        else:
            call = f"_env[{name!r}]({args})"
        if result:
            self._emit(f"_env[{result!r}] = {call}")
        else:
            self._emit(call)

    def _emit(self, line: str) -> None:
        if line:
            self.lines.append("    " * self.indent + line)
        else:
            self.lines.append("")


def _py_literal(s: str) -> str:
    return repr(s)


def compile_file(path: Path, out: Path | None = None) -> Path:
    code = ShanCompiler().compile_file(path)
    out_path = out or path.with_suffix(".py")
    out_path.write_text(code, encoding="utf-8")
    return out_path

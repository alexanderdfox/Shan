"""Compile .shan → JavaScript for browser (Phase 1 web target)."""
from __future__ import annotations

import html
import json
import textwrap
from pathlib import Path

from shan.js_expr import js_expr
from shan.parser import ShanNode, parse_file, parse_string
from shan.security import (
    assert_safe_markup,
    check_html_attr,
    check_html_tag,
    parse_on_attr,
    require_ident,
    require_mount_selector,
    require_safe_input_type,
)

LOGIC_TAGS = frozenset(
    {
        "page", "fan", "rib", "block",
        "value", "set", "list", "dict", "del",
        "half", "yes", "no", "secret", "observe",
        "show", "ask", "when", "otherwise", "each", "while",
        "break", "continue", "return",
        "fn", "call", "import", "class", "try", "except", "finally",
        "open", "when-half", "case", "deny", "assert",
        "file-read", "file-write", "seal", "unseal", "fetch", "render",
    }
)

VOID_HTML = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "bind", "input-bind",
    }
)


class WebCompileError(Exception):
    pass


class ShanWebCompiler:
    def __init__(self) -> None:
        self._fns: dict[str, list[str]] = {}
        self._fn_args: dict[str, list[str]] = {}
        self._init_stmts: list[str] = []
        self._params: set[str] = set()
        self._mount = "#app"
        self._runtime_imports: set[str] = set()

    def _ex(self, source: str) -> str:
        out = js_expr(source, self._params)
        if "len(" in out:
            self._runtime_imports.add("len")
        if "range(" in out:
            self._runtime_imports.add("range")
        return out

    def compile_file(self, path: Path) -> str:
        return self.compile_node(parse_file(path))

    def compile_string(self, source: str) -> str:
        return self.compile_node(parse_string(source))

    def compile_node(self, root: ShanNode) -> str:
        if root.tag != "page":
            raise WebCompileError("root must be <page>")
        self._runtime_imports = set()
        self._fns = {}
        self._fn_args = {}
        self._init_stmts = []
        self._mount = require_mount_selector(root.attrs.get("mount", "#app"))
        markup_nodes: list[ShanNode] = []
        for fan in root.children:
            if fan.tag == "fan":
                for rib in fan.children:
                    if rib.tag == "rib":
                        for c in rib.children:
                            if c.tag in LOGIC_TAGS:
                                self._compile_logic(c)
                            else:
                                markup_nodes.append(c)
        html_str = self._nodes_to_html(markup_nodes)
        assert_safe_markup(html_str)
        return self._emit_module(html_str, root.attrs.get("title", "ShanApp"))

    def _compile_logic(self, node: ShanNode) -> None:
        tag = node.tag
        if tag in ("fan", "rib", "block", "page"):
            for c in node.children:
                self._compile_logic(c)
            return
        if tag == "value":
            name = require_ident(node.attrs["name"])
            expr = node.attrs.get("expr", "null")
            self._init_stmts.append(f"env.{name} = {self._ex(expr)};")
            return
        if tag == "set":
            name = require_ident(node.attrs["name"])
            expr = node.attrs.get("expr", "null")
            self._init_stmts.append(f"env.{name} = {self._ex(expr)};")
            return
        if tag == "fn":
            self._compile_fn(node)
            return
        if tag == "show":
            expr = node.attrs.get("expr", "''")
            self._init_stmts.append(f"console.log({self._ex(expr)});")
            return

    def _compile_fn(self, node: ShanNode) -> None:
        name = require_ident(node.attrs["name"], what="function name")
        args = [a.strip() for a in node.attrs.get("args", "").split(",") if a.strip()]
        self._params = set(args)
        self._fn_args[name] = args
        body: list[str] = []
        self._compile_fn_body(node.children, body)
        self._fns[name] = body
        self._params = set()

    def _compile_fn_body(self, children: list[ShanNode], out: list[str]) -> None:
        i = 0
        while i < len(children):
            n = children[i]
            if n.tag == "when":
                test = self._ex(n.attrs["test"])
                out.append(f"if ({test}) {{")
                inner: list[str] = []
                self._compile_fn_body(n.children, inner)
                out.extend(["  " + line for line in inner])
                out.append("}")
                i += 1
                if i < len(children) and children[i].tag == "otherwise":
                    out.append("else {")
                    inner2: list[str] = []
                    self._compile_fn_body(children[i].children, inner2)
                    out.extend(["  " + line for line in inner2])
                    out.append("}")
                    i += 1
            elif n.tag == "set":
                name = n.attrs["name"]
                expr = self._ex(n.attrs.get("expr", "null"))
                out.append(f"env.{name} = {expr};")
                i += 1
            elif n.tag == "render":
                out.append("api.render();")
                i += 1
            elif n.tag == "show":
                expr = self._ex(n.attrs.get("expr", "''"))
                out.append(f"console.log({expr});")
                i += 1
            elif n.tag == "return":
                expr = self._ex(n.attrs.get("expr", "null"))
                out.append(f"return {expr};")
                i += 1
            elif n.tag == "call":
                name = require_ident(n.attrs["name"], what="call name")
                args_s = n.attrs.get("args", "").strip()
                if args_s:
                    out.append(f"{name}(env, api, {self._ex(args_s)});")
                else:
                    out.append(f"{name}(env, api);")
                i += 1
            else:
                i += 1

    def _nodes_to_html(self, nodes: list[ShanNode]) -> str:
        return "".join(self._node_to_html(n) for n in nodes)

    def _node_to_html(self, node: ShanNode) -> str:
        tag = node.tag
        if tag == "#text":
            return html.escape(node.text)
        if tag == "bind":
            name = require_ident(node.attrs.get("name", ""), what="bind name")
            return f'<span data-bind="{html.escape(name)}"></span>'
        if tag == "input-bind":
            name = require_ident(node.attrs.get("name", ""), what="input-bind name")
            itype = require_safe_input_type(node.attrs.get("type", "text"))
            placeholder = node.attrs.get("placeholder", "")
            ph = f' placeholder="{html.escape(placeholder)}"' if placeholder else ""
            return f'<input type="{html.escape(itype)}" data-input="{html.escape(name)}"{ph} />'
        if tag in LOGIC_TAGS:
            return ""
        check_html_tag(tag)
        attrs = dict(node.attrs)
        on = attrs.pop("on", None)
        attr_parts = []
        if on:
            event, handler = parse_on_attr(on)
            attr_parts.append(f'data-on="{html.escape(f"{event}:{handler}")}"')
        for k, v in attrs.items():
            check_html_attr(k, v)
            attr_parts.append(f'{html.escape(k)}="{html.escape(v)}"')
        attr_s = (" " + " ".join(attr_parts)) if attr_parts else ""
        void = tag in VOID_HTML or (not node.children and not node.text)
        if void:
            return f"<{tag}{attr_s} />"
        inner = html.escape(node.text) if node.text else ""
        inner += "".join(self._node_to_html(c) for c in node.children)
        return f"<{tag}{attr_s}>{inner}</{tag}>"

    def _emit_module(self, html_str: str, title: str) -> str:
        fn_decls = []
        handler_entries = []
        for name, body in self._fns.items():
            lines = body or ["api.render();"]
            extra = [a for a in self._fn_args.get(name, []) if a not in ("env", "api")]
            sig = ", ".join(["env", "api"] + extra)
            fn_decls.append(f"function {name}({sig}) {{")
            fn_decls.extend(f"  {ln}" for ln in lines)
            fn_decls.append("}")
            handler_entries.append(f"  {name},")
        fn_block = "\n".join(fn_decls)
        handlers_obj = "{\n" + "\n".join(handler_entries) + "\n}" if handler_entries else "{}"
        init = "\n".join(f"    {s}" for s in self._init_stmts)
        html_json = json.dumps(html_str)
        mount_json = json.dumps(self._mount)
        title_json = json.dumps(title)
        rt = ["mount"] + sorted(self._runtime_imports)
        imports = ", ".join(rt)
        return (
            f"/**\n * Generated by Shàn — {title}\n * Phase 1 web — no hand-written app JS\n */\n"
            f"import {{ {imports} }} from '/dist/shan-web.js';\n\n"
            f"{fn_block}\n\n"
            f"const handlers = {handlers_obj};\n\n"
            f"export function createApp() {{\n"
            f"  return mount({{\n"
            f"    mount: {mount_json},\n"
            f"    title: {title_json},\n"
            f"    html: {html_json},\n"
            f"    init(env) {{\n"
            f"{init or '      // no init'}\n"
            f"    }},\n"
            f"    handlers,\n"
            f"  }});\n"
            f"}}\n\n"
            f"export default createApp;\n"
        )


def compile_file(path: Path, out: Path | None = None) -> Path:
    code = ShanWebCompiler().compile_file(path)
    default = path.parent / "web" / "dist" / "apps" / f"{path.stem}.js"
    if path.parent.name != "examples" and (Path.cwd() / "examples" / "web").is_dir():
        default = Path.cwd() / "examples" / "web" / "dist" / "apps" / f"{path.stem}.js"
    out_path = out or default
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(code, encoding="utf-8")
    return out_path


def copy_runtime(dest_dir: Path) -> Path:
    src = Path(__file__).parent / "static" / "shan-web.js"
    dest = dest_dir / "shan-web.js"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest

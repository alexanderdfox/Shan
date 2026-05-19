"""Strict static checker for .shan programs."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from shan.locate import annotate_locations
from shan.parser import ShanNode, parse_file, parse_string
from shan.security import (
    ALLOWED_HTML_TAGS,
    FORBIDDEN_HTML_TAGS,
    check_html_attr,
    check_html_tag,
    parse_on_attr,
    require_ident,
)

VALID_ROOMS = frozenset({"keys", "files", "net", "proc", "env", "time", "rand", "sys"})

ROOM_TAGS = {
    "file-read": "files",
    "file-write": "files",
    "fetch": "net",
    "seal": "keys",
    "unseal": "keys",
    "observe": "keys",
}

KNOWN_TAGS = frozenset(
    {
        "page",
        "fan",
        "rib",
        "block",
        "value",
        "set",
        "list",
        "dict",
        "del",
        "half",
        "yes",
        "no",
        "secret",
        "observe",
        "show",
        "text",
        "ask",
        "when",
        "otherwise",
        "each",
        "while",
        "break",
        "continue",
        "return",
        "fn",
        "call",
        "import",
        "class",
        "try",
        "except",
        "finally",
        "open",
        "when-half",
        "case",
        "deny",
        "assert",
        "file-read",
        "file-write",
        "seal",
        "unseal",
    }
)

REQUIRED_ATTRS: dict[str, list[str]] = {
    "value": ["name"],
    "set": ["name"],
    "list": ["name", "expr"],
    "dict": ["name", "expr"],
    "del": ["name"],
    "half": ["name"],
    "yes": ["name"],
    "no": ["name"],
    "secret": ["name"],
    "observe": ["name"],
    "when": ["test"],
    "each": ["var", "in"],
    "while": ["test"],
    "return": [],
    "fn": ["name"],
    "call": ["name"],
    "open": ["room", "why"],
    "when-half": ["name"],
    "case": ["value"],
    "assert": ["test"],
    "file-read": ["path"],
    "file-write": ["path"],
    "seal": ["expr", "key"],
    "ask": ["name"],
}


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    line: int
    col: int
    message: str
    severity: Severity = Severity.ERROR
    rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "severity": self.severity.value,
            "rule": self.rule,
        }


@dataclass
class CheckResult:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    ok: bool = True

    def add(self, d: Diagnostic) -> None:
        self.diagnostics.append(d)
        if d.severity == Severity.ERROR:
            self.ok = False


class ShanChecker:
    def __init__(self) -> None:
        self.result = CheckResult()
        self.open_rooms: list[str] = []
        self.secrets: set[str] = set()
        self.half_vars: set[str] = set()
        self._when_test_stack: list[str] = []

    def check_file(self, path: Path) -> CheckResult:
        source = path.read_text(encoding="utf-8")
        try:
            node = parse_file(path)
        except Exception as e:
            r = CheckResult(ok=False)
            r.add(Diagnostic(1, 1, str(e), rule="parse"))
            return r
        annotate_locations(node, source)
        return self.check_node(node)

    def check_string(self, source: str) -> CheckResult:
        try:
            node = parse_string(source)
        except Exception as e:
            r = CheckResult(ok=False)
            r.add(Diagnostic(1, 1, str(e), rule="parse"))
            return r
        annotate_locations(node, source)
        return self.check_node(node)

    def check_node(self, root: ShanNode) -> CheckResult:
        self.result = CheckResult()
        self.open_rooms = []
        self.secrets = set()
        self.half_vars = set()
        if root.tag != "page":
            self._err(root, "root element must be <page>", "root")
        self._walk(root)
        return self.result

    def _walk(self, node: ShanNode) -> None:
        tag = node.tag
        if tag not in KNOWN_TAGS:
            if tag in ALLOWED_HTML_TAGS or tag in ("bind", "html-bind", "input-bind"):
                self._check_web_markup(node)
            else:
                self._warn(node, f"unknown tag <{tag}>", "unknown-tag")

        for attr in REQUIRED_ATTRS.get(tag, []):
            if attr not in node.attrs:
                self._err(node, f"<{tag}> requires attribute '{attr}'", "missing-attr")

        if tag == "open":
            room = node.attrs.get("room", "")
            if room not in VALID_ROOMS:
                self._err(node, f"invalid room '{room}' — use one of: {', '.join(sorted(VALID_ROOMS))}", "room")
            if not node.attrs.get("why", "").strip():
                self._err(node, "<open> requires non-empty why=\"...\"", "why")
            self.open_rooms.append(room)
            for c in node.children:
                self._walk(c)
            self.open_rooms.pop()
            return

        if tag == "secret":
            if "keys" not in self.open_rooms:
                self._err(node, "<secret> must be inside <open room=\"keys\" why=\"...\">", "room-keys")
            name = node.attrs.get("name", "")
            self.secrets.add(name)
            uses = node.attrs.get("uses")
            if uses is not None:
                try:
                    n = int(uses)
                    if n < 1:
                        self._err(node, "uses must be >= 1", "uses")
                except ValueError:
                    self._err(node, f"uses must be an integer, got '{uses}'", "uses")

        room = ROOM_TAGS.get(tag)
        if room and room not in self.open_rooms:
            self._err(
                node,
                f"<{tag}> needs <open room=\"{room}\" why=\"...\">",
                f"room-{room}",
            )

        if tag == "observe" and not node.attrs.get("why", "").strip():
            self._err(node, "<observe> requires why=\"...\"", "why")

        if tag == "show":
            expr = node.attrs.get("expr", "")
            for s in self.secrets:
                if re.search(rf"\b{re.escape(s)}\b", expr):
                    self._err(
                        node,
                        f"cannot <show> secret '{s}' — use <observe> inside <open room=\"keys\">",
                        "show-secret",
                    )

        if tag == "half":
            self.half_vars.add(node.attrs.get("name", ""))

        if tag == "when":
            test = node.attrs.get("test", "")
            for hv in self.half_vars:
                if re.search(rf"\b{re.escape(hv)}\b", test):
                    self._err(
                        node,
                        f"cannot use half variable '{hv}' in <when test> — use <when-half>",
                        "half-in-when",
                    )

        if tag == "when-half":
            name = node.attrs.get("name", "")
            cases = [c.attrs.get("value") for c in node.children if c.tag == "case"]
            for required in ("half", "yes", "no"):
                if required not in cases:
                    self._warn(node, f"<when-half name=\"{name}\"> missing <case value=\"{required}\">", "case-missing")

        if tag == "case":
            v = node.attrs.get("value", "")
            if v not in ("half", "yes", "no"):
                self._err(node, f"<case value> must be half|yes|no, got '{v}'", "case-value")

        if tag == "fn" and not node.attrs.get("args"):
            self._warn(node, f"<fn name=\"{node.attrs.get('name')}\"> has no args attribute", "fn-args")

        if tag == "import" and "module" not in node.attrs and "shan" not in node.attrs:
            self._err(node, "<import> needs module=\"...\" or shan=\"...\"", "import")

        if tag == "fn":
            try:
                require_ident(node.attrs.get("name", ""), what="function name")
            except ValueError as e:
                self._err(node, str(e), "fn-name")

        if tag == "call":
            try:
                require_ident(node.attrs.get("name", ""), what="call name")
            except ValueError as e:
                self._err(node, str(e), "call-name")

        for c in node.children:
            if tag == "open":
                continue
            self._walk(c)

    def _err(self, node: ShanNode, msg: str, rule: str) -> None:
        self.result.add(Diagnostic(node.line or 1, node.col or 1, msg, Severity.ERROR, rule))

    def _warn(self, node: ShanNode, msg: str, rule: str) -> None:
        self.result.add(Diagnostic(node.line or 1, node.col or 1, msg, Severity.WARNING, rule))

    def _check_web_markup(self, node: ShanNode) -> None:
        tag = node.tag.lower()
        if tag in FORBIDDEN_HTML_TAGS:
            self._err(node, f"forbidden HTML tag <{node.tag}>", "web-forbidden-tag")
            return
        if tag in ("bind", "html-bind", "input-bind"):
            try:
                require_ident(node.attrs.get("name", ""), what=f"{tag} name")
            except ValueError as e:
                self._err(node, str(e), "web-bind-name")
        on = node.attrs.get("on")
        if on:
            try:
                parse_on_attr(on)
            except ValueError as e:
                self._err(node, str(e), "web-on-attr")
        for k, v in node.attrs.items():
            if k == "on":
                continue
            try:
                check_html_attr(k, v)
            except ValueError as e:
                self._err(node, str(e), "web-attr")
        if tag not in ("bind", "input-bind"):
            try:
                check_html_tag(tag)
            except ValueError:
                pass  # unknown-tag warning already emitted


def check_file(path: Path) -> CheckResult:
    return ShanChecker().check_file(path)


def format_diagnostics(result: CheckResult, path: Path | None = None) -> str:
    lines = []
    prefix = f"{path}: " if path else ""
    for d in result.diagnostics:
        sev = d.severity.value.upper()
        lines.append(f"{prefix}line {d.line}, col {d.col}: {sev}: {d.message}")
    if result.ok and not result.diagnostics:
        return "OK"
    return "\n".join(lines) if lines else "OK"


def diagnostics_json(result: CheckResult) -> str:
    return json.dumps({"ok": result.ok, "diagnostics": [d.to_dict() for d in result.diagnostics]}, indent=2)

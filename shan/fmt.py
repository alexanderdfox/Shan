"""Format .shan files (HTML-style indent)."""
from __future__ import annotations

from pathlib import Path

from shan.parser import ShanNode, parse_file, parse_string

INDENT = "  "
VOID_TAGS = frozenset(
    {
        "half",
        "deny",
        "break",
        "continue",
        "yes",
        "no",
        "return",
        "show",
        "set",
        "list",
        "dict",
        "del",
        "call",
        "import",
        "observe",
        "ask",
        "assert",
    }
)


def _fmt_attrs(attrs: dict[str, str]) -> str:
    if not attrs:
        return ""
    parts = [f'{k}="{_escape(v)}"' for k, v in sorted(attrs.items())]
    return " " + " ".join(parts)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def format_node(node: ShanNode, depth: int = 0) -> str:
    pad = INDENT * depth
    attrs = _fmt_attrs(node.attrs)
    text = (node.text or "").strip()

    if node.tag in VOID_TAGS and not node.children and not text:
        return f"{pad}<{node.tag}{attrs} />\n"

    if not node.children and not text:
        return f"{pad}<{node.tag}{attrs}></{node.tag}>\n"

    if not node.children and text:
        if "\n" in text:
            inner = "\n".join(INDENT * (depth + 1) + ln for ln in text.splitlines()) + "\n"
            return f"{pad}<{node.tag}{attrs}>\n{inner}{pad}</{node.tag}>\n"
        return f"{pad}<{node.tag}{attrs}>{_escape(text)}</{node.tag}>\n"

    out = f"{pad}<{node.tag}{attrs}>\n"
    if text:
        for ln in text.splitlines():
            out += f"{pad}{INDENT}{ln}\n"
    for c in node.children:
        out += format_node(c, depth + 1)
    out += f"{pad}</{node.tag}>\n"
    return out


def format_string(source: str) -> str:
    node = parse_string(source)
    return format_node(node).rstrip() + "\n"


def format_file(path: Path) -> str:
    return format_string(path.read_text(encoding="utf-8"))


def format_file_inplace(path: Path) -> None:
    path.write_text(format_file(path), encoding="utf-8")

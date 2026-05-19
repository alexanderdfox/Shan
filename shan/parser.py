"""Parse .shan files (HTML-like) into element trees."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShanNode:
    tag: str
    attrs: dict[str, str]
    text: str = ""
    children: list["ShanNode"] = field(default_factory=list)
    line: int = 0
    col: int = 0


_VOID = {"half", "deny", "break", "continue", "yes", "no", "return", "show", "set", "call", "import", "observe", "ask", "assert", "del", "list", "dict"}


def _strip_comments(source: str) -> str:
    return re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)


def _wrap_fragment(source: str) -> str:
    return f"<root>{source}</root>"


def parse_file(path: Path) -> ShanNode:
    text = path.read_text(encoding="utf-8")
    return parse_string(text)


def parse_string(source: str) -> ShanNode:
    cleaned = _strip_comments(source).strip()
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        wrapped = _wrap_fragment(cleaned)
        root = ET.fromstring(wrapped)
        if root.tag == "root":
            if len(root) != 1:
                raise ValueError("expected single <page> root element")
            root = root[0]
    return _et_to_node(root)


def _et_to_node(el: ET.Element) -> ShanNode:
    tag = el.tag.split("}")[-1]  # handle namespaces
    attrs = dict(el.attrib)
    children: list[ShanNode] = []
    if el.text and el.text.strip():
        children.append(ShanNode(tag="#text", attrs={}, text=el.text.strip()))
    for child in el:
        children.append(_et_to_node(child))
        if child.tail and child.tail.strip():
            children.append(ShanNode(tag="#text", attrs={}, text=child.tail.strip()))
    return ShanNode(tag=tag, attrs=attrs, text="", children=children)

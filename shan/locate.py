"""Attach source line/column to ShanNode tree (preorder match)."""
from __future__ import annotations

import re
from typing import Iterator

from shan.parser import ShanNode

_OPEN = re.compile(r"<(?P<close>/?)(?P<tag>[\w-]+)(?P<rest>[^>]*?)(?P<void>/\s*)?>")


def _iter_nodes(node: ShanNode) -> Iterator[ShanNode]:
    yield node
    for c in node.children:
        yield from _iter_nodes(c)


def _iter_opens(source: str) -> Iterator[tuple[int, int, str, bool]]:
    """Yield (line, col, tag, is_void) for opening tags in document order."""
    for m in _OPEN.finditer(source):
        if m.group("close") == "/":
            continue
        tag = m.group("tag")
        is_void = bool(m.group("void"))
        line = source.count("\n", 0, m.start()) + 1
        col = m.start() - source.rfind("\n", 0, m.start())
        yield line, col, tag, is_void


def annotate_locations(root: ShanNode, source: str) -> None:
    opens = list(_iter_opens(source))
    nodes = list(_iter_nodes(root))
    if len(opens) != len(nodes):
        # fallback: match by tag name scanning
        _annotate_by_tag(root, source)
        return
    for node, (line, col, tag, _void) in zip(nodes, opens):
        if node.tag == tag:
            node.line = line
            node.col = col


def _annotate_by_tag(root: ShanNode, source: str) -> None:
    for node in _iter_nodes(root):
        needle = f"<{node.tag}"
        idx = source.find(needle)
        if idx >= 0:
            node.line = source.count("\n", 0, idx) + 1
            node.col = idx - source.rfind("\n", 0, idx)

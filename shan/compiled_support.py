"""Runtime support for compiled Shàn → Python (span, rooms, audit)."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Iterator


class Truth(Enum):
    HALF = auto()
    YES = auto()
    NO = auto()


Half = Truth.HALF
Yes = Truth.YES
No = Truth.NO


@dataclass
class Span:
    value: Any
    remaining: float = 1.0
    uses_left: int | None = None

    def contract(self, lam: float = 0.9) -> "Span":
        if self.uses_left is not None:
            if self.uses_left <= 0:
                raise RuntimeError("fan closed: secret uses exhausted")
            self.uses_left -= 1
        self.remaining *= lam
        if self.remaining < 1e-6:
            raise RuntimeError("fan closed: span below epsilon")
        return self


_audit: list[dict[str, Any]] = []
_open_rooms: list[str] = []


def audit_log() -> list[dict[str, Any]]:
    return list(_audit)


@contextmanager
def shan_open(room: str, why: str, rib: str = "default") -> Iterator[None]:
    _open_rooms.append(room)
    _audit.append({"room": room, "why": why, "rib": rib, "tag": "open"})
    try:
        yield
    finally:
        _open_rooms.pop()


def _require(room: str) -> None:
    if room not in _open_rooms:
        raise RuntimeError(f'operation requires <open room="{room}" why="...">')


def shan_observe(secret: Span, why: str, rib: str = "default") -> Any:
    _require("keys")
    _audit.append({"room": "keys", "why": why, "rib": rib, "tag": "observe"})
    secret.contract()
    return secret.value


def shan_seal(data: Any, key: Any) -> str:
    _require("keys")
    return hashlib.sha256((str(key) + str(data)).encode()).hexdigest()


def shan_file_read(path: str) -> str:
    _require("files")
    return Path(path).read_text(encoding="utf-8")


def shan_file_write(path: str, content: str) -> None:
    _require("files")
    Path(path).write_text(content, encoding="utf-8")


def truthy(v: Any) -> bool:
    if isinstance(v, Truth):
        return v is Truth.YES
    return bool(v)


def match_half(val: Any) -> str:
    if isinstance(val, Truth):
        return {Truth.YES: "yes", Truth.NO: "no", Truth.HALF: "half"}[val]
    return "yes" if truthy(val) else "no"

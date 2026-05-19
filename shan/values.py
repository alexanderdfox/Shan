"""Fan value model: Half, Yes, No, Span, FanValue."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class Truth(Enum):
    HALF = auto()
    YES = auto()
    NO = auto()

    @staticmethod
    def from_bool(b: bool) -> "Truth":
        return Truth.YES if b else Truth.NO

    def combine_and(self, other: "Truth") -> "Truth":
        if self is Truth.HALF or other is Truth.HALF:
            return Truth.HALF
        if self is Truth.YES and other is Truth.YES:
            return Truth.YES
        return Truth.NO

    def combine_or(self, other: "Truth") -> "Truth":
        if self is Truth.YES or other is Truth.YES:
            return Truth.YES
        if self is Truth.HALF or other is Truth.HALF:
            return Truth.HALF
        return Truth.NO


@dataclass
class Span:
    """Contracting '1' — value with remaining span and use budget."""

    value: Any
    remaining: float = 1.0
    uses_left: int | None = None
    is_secret: bool = True

    def contract(self, lam: float = 0.9) -> "Span":
        if self.uses_left is not None:
            if self.uses_left <= 0:
                raise RuntimeError(f"fan closed: secret span exhausted (uses=0)")
            self.uses_left -= 1
        self.remaining *= lam
        if self.remaining < 1e-6:
            raise RuntimeError("fan closed: span remaining below epsilon")
        return self


@dataclass
class FanValue:
    """Superposition placeholder — rib-indexed slots."""

    ribs: int
    slots: dict[int, Any]

    def __init__(self, ribs: int = 4):
        self.ribs = ribs
        self.slots = {}


def to_truth(v: Any) -> Truth:
    if isinstance(v, Truth):
        return v
    if v is None or v is False:
        return Truth.NO
    if v is True:
        return Truth.YES
    if isinstance(v, str) and v == "half":
        return Truth.HALF
    return Truth.YES  # non-empty values are truthy for when-test


def truthy(v: Any) -> bool:
    if isinstance(v, Truth):
        return v is Truth.YES
    if isinstance(v, Span):
        return True
    return bool(v)

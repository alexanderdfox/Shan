"""Builtins available in Shàn expressions (Python-like)."""
from __future__ import annotations

import json as _json
import math
import hashlib
from pathlib import Path

from shan.values import Span, Truth

from shan.fan_cipher import (
    combine_half,
    collapse_rib_truths,
    fan_audit_summary,
    fan_decrypt,
    fan_encrypt,
)


def build_builtins(runtime) -> dict:
    return {
        "print": print,
        "len": len,
        "range": range,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "reversed": reversed,
        "round": round,
        "type": type,
        "isinstance": isinstance,
        "Truth": Truth,
        "Half": Truth.HALF,
        "Yes": Truth.YES,
        "No": Truth.NO,
        # QFan cipher (half-truth quantum fan)
        "fan_encrypt": fan_encrypt,
        "fan_decrypt": fan_decrypt,
        "fan_audit_summary": fan_audit_summary,
        "collapse_rib_truths": collapse_rib_truths,
        "combine_half": combine_half,
        # math
        "pi": math.pi,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "pow": pow,
        # json
        "json_loads": _json.loads,
        "json_dumps": lambda o: _json.dumps(o),
        # hash (still needs keys room for secrets in strict mode)
        "sha256": lambda s: hashlib.sha256(str(s).encode()).hexdigest(),
        # io helpers — runtime checks room
        "read_text": lambda p: runtime.file_read(p),
        "write_text": lambda p, t: runtime.file_write(p, t),
    }

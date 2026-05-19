"""Tests for web compile target."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compile_greet_imports_len():
    from shan.compile_web import ShanWebCompiler

    js = ShanWebCompiler().compile_string(
        (ROOT / "examples" / "greet-web.shan").read_text()
    )
    assert "import { mount, len }" in js
    assert "String(env.name).trim()" in js


def test_compile_calc_digits():
    from shan.compile_web import ShanWebCompiler

    js = ShanWebCompiler().compile_string(
        (ROOT / "examples" / "calc-web.shan").read_text()
    )
    assert "appendDigit(env, api, '7')" in js
    assert "env.display === '0'" in js


def test_compile_hello_web():
    from shan.compile_web import ShanWebCompiler

    src = (ROOT / "examples" / "hello-web.shan").read_text()
    js = ShanWebCompiler().compile_string(src)
    assert "import { mount }" in js
    assert "function increment" in js
    assert "data-bind" in js
    assert "data-on" in js
    assert "<script" not in js.lower()


def test_js_expr():
    from shan.js_expr import js_expr

    assert js_expr("count + 1") == "(env.count + 1)"
    assert js_expr("[x * 2 for x in xs]") == "(env.xs).map(x => (x * 2))"
    assert js_expr("name.strip()") == "String(env.name).trim()"

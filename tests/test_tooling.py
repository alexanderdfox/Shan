"""Tests for checker, fmt, compile."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_checker_hello_ok():
    from shan.checker import check_file

    r = check_file(EXAMPLES / "hello.shan")
    assert r.ok, r.diagnostics


def test_checker_rejects_show_secret():
    from shan.checker import ShanChecker

    src = """<page>
  <fan><rib id="default">
    <open room="keys" why="t">
      <secret name="k">x</secret>
    </open>
    <show expr="k"/>
  </rib></fan>
</page>"""
    r = ShanChecker().check_string(src)
    assert not r.ok
    assert any(d.rule == "show-secret" for d in r.diagnostics)


def test_checker_requires_open_for_file_read():
    from shan.checker import ShanChecker

    src = """<page><fan><rib id="d">
    <file-read path="'a.txt'" result="t"/>
  </rib></fan></page>"""
    r = ShanChecker().check_string(src)
    assert not r.ok


def test_fmt_roundtrip():
    from shan.fmt import format_string
    from shan.parser import parse_string

    src = (EXAMPLES / "hello.shan").read_text()
    out = format_string(src)
    n1 = parse_string(src)
    n2 = parse_string(out)
    assert n1.tag == n2.tag == "page"


def test_compile_hello_runs():
    from shan.compile import ShanCompiler
    import tempfile
    import os

    src = (EXAMPLES / "hello.shan").read_text()
    code = ShanCompiler().compile_string(src)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "out.py"
        p.write_text(code)
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, env=env, cwd=td)
        assert r.returncode == 0, r.stderr
        assert "Hello" in r.stdout


def test_cli_check_json():
    r = subprocess.run(
        [sys.executable, "-m", "shan", "check", str(EXAMPLES / "hello.shan"), "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert r.returncode == 0
    assert '"ok": true' in r.stdout

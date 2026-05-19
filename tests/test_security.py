"""Security hardening tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shan.checker import check_file
from shan.compile_web import ShanWebCompiler, WebCompileError
from shan.expr import eval_expr
from shan.security import resolve_path_under


class TestExprSecurity(unittest.TestCase):
    def test_blocks_dunder_getattr(self) -> None:
        with self.assertRaises((ValueError, NameError)):
            eval_expr("__import__('os').system('x')", {}, {})

    def test_blocks_indirect_call(self) -> None:
        with self.assertRaises(ValueError):
            eval_expr("(lambda: 1)()", {}, {})

    def test_allows_builtin_call(self) -> None:
        self.assertEqual(eval_expr("len([1,2])", {}, {"len": len}), 2)


class TestPathSecurity(unittest.TestCase):
    def test_blocks_traversal(self) -> None:
        base = Path(tempfile.mkdtemp())
        with self.assertRaises(PermissionError):
            resolve_path_under(base, "../../../etc/passwd")


class TestWebCompileSecurity(unittest.TestCase):
    def test_blocks_script_tag(self) -> None:
        src = """<page mount="#app">
  <fan><rib>
    <script>alert(1)</script>
  </rib></fan>
</page>"""
        with self.assertRaises((WebCompileError, ValueError)):
            ShanWebCompiler().compile_string(src)

    def test_blocks_javascript_href(self) -> None:
        src = """<page mount="#app">
  <fan><rib>
    <a href="javascript:alert(1)">x</a>
  </rib></fan>
</page>"""
        with self.assertRaises((WebCompileError, ValueError)):
            ShanWebCompiler().compile_string(src)


class TestCheckerWeb(unittest.TestCase):
    def test_flags_javascript_href(self) -> None:
        src = """<page>
  <fan><rib>
    <a href="javascript:alert(1)">x</a>
  </rib></fan>
</page>"""
        from shan.checker import ShanChecker

        r = ShanChecker().check_string(src)
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()

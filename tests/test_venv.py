"""Virtual environment helpers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_find_project_root():
    from shan.venv import find_project_root, venv_python

    assert find_project_root(ROOT / "shan" / "__main__.py") == ROOT
    assert venv_python(ROOT) is not None
    assert find_project_root(Path("/tmp")) is None

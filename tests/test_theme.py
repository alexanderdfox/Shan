"""Theme cookie and page shell."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_normalize_and_safe_return():
    from shan.theme import normalize_theme, safe_return, toggle_theme

    assert normalize_theme("light") == "light"
    assert normalize_theme("bogus") == "dark"
    assert toggle_theme("dark") == "light"
    assert safe_return("/app/calc-web") == "/app/calc-web"
    assert safe_return("//evil") == "/gallery.html"


def test_render_includes_theme():
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    html = reg.render("hello-web", {}, theme="light")
    assert 'data-theme="light"' in html
    assert "theme-switch" in html
    assert 'aria-current="true"' in html


def test_gallery_render():
    from shan.theme import render_gallery
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    html = render_gallery("dark", reg.stems())
    assert "password-web" in html
    assert 'data-theme="dark"' in html

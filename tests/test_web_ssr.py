"""Server-rendered web apps (no JavaScript)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ssr_no_script_tags():
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    for stem in reg.stems():
        html = reg.render(stem, {})
        assert "<script" not in html.lower(), stem


def test_base_css_no_external_fonts():
    css = (ROOT / "examples" / "web" / "styles" / "base.css").read_text()
    assert "fonts.googleapis.com" not in css
    assert "@import url(" not in css


def test_greet_action():
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    html = reg.render("greet-web", {"name": "Ada", "_action": "sayHello"})
    assert "Hello, Ada" in html


def test_calc_arithmetic():
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    # 12 + 3 = 15
    h = reg.render(
        "calc-web",
        {
            "display": "3",
            "lhs": "12",
            "op": "+",
            "_action": "equals",
        },
    )
    assert ">15<" in h or "15</span>" in h
    # 8 * 7 = 56
    h2 = reg.render(
        "calc-web",
        {
            "display": "7",
            "lhs": "8",
            "op": "*",
            "_action": "equals",
        },
    )
    assert "56" in h2


def test_password_generate():
    import string

    from shan.web_ssr import WebAppRegistry, gen_password

    pwd = gen_password(24, 1, 1, 1, 1)
    assert len(pwd) == 24
    assert any(c in string.ascii_uppercase for c in pwd)
    assert any(c in string.ascii_lowercase for c in pwd)
    assert any(c in string.digits for c in pwd)

    reg = WebAppRegistry(ROOT / "examples")
    html = reg.render(
        "password-web",
        {
            "length": "20",
            "use_upper": "1",
            "use_lower": "1",
            "use_digits": "1",
            "use_symbols": "1",
            "_action": "generate",
        },
    )
    assert 'type="checkbox"' in html
    assert "New password generated" in html
    # Extract password from span.val inside password-box (non-empty after generate)
    assert "password-box" in html


def test_fan_image_multipart_and_seal():
    from shan.image_fan import sample_image_b64
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    html = reg.render("fan-image-web", {})
    assert "multipart/form-data" in html
    assert 'type="file"' in html
    assert "data:image/png;base64," in html

    html3 = reg.render(
        "fan-image-web",
        {
            "key": "test-key",
            "ribs": "8",
            "plain_b64": sample_image_b64(),
            "mime": "image/png",
            "_action": "qfanRound",
        },
    )
    assert "Instagram" in html3 or "round-trip" in html3
    assert "data:image" in html3
    assert "matches" in html3 or "1080" in html3


def test_parser_inline_tail_text():
    from shan.parser import parse_string

    root = parse_string(
        '<page title="t"><fan ribs="1"><rib id="r">'
        '<p>before <strong>bold</strong> after</p>'
        "</rib></fan></page>"
    )
    p = root.children[0].children[0].children[0]
    assert [c.tag for c in p.children] == ["#text", "strong", "#text"]
    assert p.children[0].text == "before"
    assert p.children[1].text == ""
    assert p.children[1].children[0].text == "bold"
    assert p.children[2].text == "after"

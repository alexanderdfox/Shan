"""Klondike solitaire logic and web SSR."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_roundtrip_and_win_detection():
    from shan.solitaire import deserialize, new_game, serialize, sol_won

    g = new_game()
    raw = serialize(g)
    g2 = deserialize(raw)
    n = len(g2.stock) + len(g2.waste) + sum(len(f) for f in g2.found) + sum(len(t) for t in g2.tabs)
    assert n == 52
    assert sol_won(raw) == 0


def test_tap_draw():
    from shan.solitaire import sol_draw, sol_new, sol_tap

    state = sol_new()
    d = sol_draw(state)
    assert d["state"] != state or d["msg"]
    t = sol_tap(state, "", "waste")
    assert "state" in t and "sel" in t and "msg" in t


def test_solitaire_web_renders():
    from shan.web_ssr import WebAppRegistry

    reg = WebAppRegistry(ROOT / "examples")
    html = reg.render("solitaire-web", {})
    assert "sol-board" in html
    assert "sol-card" in html
    assert "<script" not in html.lower()
    assert "tap_t0" in html

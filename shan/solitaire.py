"""Klondike solitaire — server-side game logic and board HTML for web SSR."""
from __future__ import annotations

import html
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

SUITS = ("S", "H", "D", "C")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")
SUIT_SYM = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RED_SUITS = frozenset({"H", "D"})


@dataclass
class Card:
    id: int
    up: bool = True

    @property
    def suit(self) -> str:
        return SUITS[self.id // 13]

    @property
    def rank(self) -> str:
        return RANKS[self.id % 13]

    @property
    def color(self) -> str:
        return "red" if self.suit in RED_SUITS else "black"

    def rank_val(self) -> int:
        return self.id % 13


@dataclass
class Game:
    stock: list[Card] = field(default_factory=list)
    waste: list[Card] = field(default_factory=list)
    found: list[list[Card]] = field(default_factory=lambda: [[] for _ in range(4)])
    tabs: list[list[Card]] = field(default_factory=lambda: [[] for _ in range(7)])
    draws: int = 1

    def won(self) -> bool:
        return all(len(p) == 13 for p in self.found)


def new_game() -> Game:
    rng = secrets.SystemRandom()
    deck = list(range(52))
    rng.shuffle(deck)
    g = Game()
    i = 0
    for col in range(7):
        for row in range(col + 1):
            g.tabs[col].append(Card(deck[i], up=(row == col)))
            i += 1
    g.stock = [Card(cid, up=False) for cid in deck[i:]]
    return g


def serialize(g: Game) -> str:
    def enc(cards: list[Card]) -> str:
        return ",".join(f"{c.id}{'' if c.up else 'd'}" for c in cards)

    return "|".join(
        [enc(g.stock), enc(g.waste)]
        + [enc(p) for p in g.found]
        + [enc(p) for p in g.tabs]
        + [str(g.draws)]
    )


def deserialize(raw: str) -> Game:
    if not raw or not str(raw).strip():
        return new_game()

    def dec(s: str) -> list[Card]:
        if not s:
            return []
        out: list[Card] = []
        for tok in s.split(","):
            tok = tok.strip()
            if not tok:
                continue
            up = not tok.endswith("d")
            cid = int(tok[:-1] if tok.endswith("d") else tok)
            if 0 <= cid <= 51:
                out.append(Card(cid, up=up))
        return out

    parts = (raw.split("|") + [""] * 14)[:14]
    g = Game()
    g.stock = dec(parts[0])
    g.waste = dec(parts[1])
    g.found = [dec(parts[i]) for i in range(2, 6)]
    g.tabs = [dec(parts[i]) for i in range(6, 13)]
    try:
        g.draws = max(1, min(3, int(parts[13] or "1")))
    except ValueError:
        g.draws = 1
    return g


def _flip_top(cards: list[Card]) -> None:
    if cards and not cards[-1].up:
        cards[-1].up = True


def _can_on_foundation(card: Card, pile: list[Card]) -> bool:
    if not pile:
        return card.rank_val() == 0
    top = pile[-1]
    return card.suit == top.suit and card.rank_val() == top.rank_val() + 1


def _can_on_tableau(card: Card, pile: list[Card]) -> bool:
    if not pile:
        return card.rank_val() == 12
    top = pile[-1]
    if not top.up:
        return False
    return card.color != top.color and card.rank_val() == top.rank_val() - 1


def _valid_tableau_run(cards: list[Card], start: int) -> int:
    if start >= len(cards) or not cards[start].up:
        return 0
    n = 1
    for i in range(start + 1, len(cards)):
        a, b = cards[i - 1], cards[i]
        if not b.up or a.color == b.color or a.rank_val() != b.rank_val() + 1:
            break
        n += 1
    return n


def _move_cards(src: list[Card], dst: list[Card], count: int) -> None:
    dst.extend(src[-count:])
    del src[-count:]
    _flip_top(src)


def _pile_ref(g: Game, pid: str) -> list[Card] | None:
    pid = pid.lower().strip()
    if pid == "stock":
        return g.stock
    if pid == "waste":
        return g.waste
    if len(pid) == 2 and pid[0] == "f" and pid[1].isdigit():
        i = int(pid[1])
        return g.found[i] if 0 <= i < 4 else None
    if len(pid) == 2 and pid[0] == "t" and pid[1].isdigit():
        i = int(pid[1])
        return g.tabs[i] if 0 <= i < 7 else None
    return None


def draw(g: Game) -> str:
    if g.stock:
        for _ in range(min(g.draws, len(g.stock))):
            c = g.stock.pop()
            c.up = True
            g.waste.append(c)
        return "Drew from stock"
    if g.waste:
        while g.waste:
            c = g.waste.pop()
            c.up = False
            g.stock.insert(0, c)
        return "Recycled waste to stock"
    return "Stock empty"


def try_move(g: Game, src: str, dst: str) -> str:
    src, dst = src.lower(), dst.lower()
    if src == dst:
        return "Same pile"
    spile = _pile_ref(g, src)
    dpile = _pile_ref(g, dst)
    if spile is None or dpile is None:
        return "Invalid pile"
    if src == "stock":
        return "Use Draw for stock"

    if src == "waste":
        if not spile:
            return "Waste empty"
        card = spile[-1]
        if dst.startswith("f") and _can_on_foundation(card, dpile):
            _move_cards(spile, dpile, 1)
            return "To foundation"
        if dst.startswith("t") and _can_on_tableau(card, dpile):
            _move_cards(spile, dpile, 1)
            return "To tableau"
        return "Invalid move"

    if src.startswith("f"):
        if not spile:
            return "Foundation empty"
        card = spile[-1]
        if dst.startswith("t") and _can_on_tableau(card, dpile):
            _move_cards(spile, dpile, 1)
            return "From foundation"
        return "Invalid move"

    if src.startswith("t"):
        col = int(src[1])
        pile = g.tabs[col]
        if not pile:
            return "Column empty"
        start = len(pile) - 1
        for i in range(len(pile)):
            if pile[i].up:
                start = i
                break
        run = _valid_tableau_run(pile, start)
        top = pile[-run]
        if dst.startswith("f") and run == 1 and _can_on_foundation(top, dpile):
            _move_cards(pile, dpile, 1)
            return "To foundation"
        if dst.startswith("t") and _can_on_tableau(top, dpile):
            _move_cards(pile, dpile, run)
            return "Moved stack"
        return "Invalid move"

    return "Invalid move"


def tap(g: Game, sel: str, pile: str) -> tuple[Game, str, str]:
    pile = (pile or "").strip().lower()
    if not pile:
        return g, sel or "", ""
    if not sel:
        if pile == "waste" and g.waste:
            return g, "waste", "Selected waste"
        if pile.startswith("f") and _pile_ref(g, pile) and _pile_ref(g, pile):
            return g, pile, "Selected foundation"
        if pile.startswith("t"):
            c = int(pile[1])
            if g.tabs[c] and g.tabs[c][-1].up:
                return g, pile, f"Column {c + 1} selected"
        return g, "", "Select a face-up card"
    msg = try_move(g, sel, pile)
    return g, "", msg


def auto_foundation(g: Game) -> str:
    moved = 0
    for _ in range(52):
        found = False
        for src, pile, idx in _iter_sources(g):
            if not pile:
                continue
            card = pile[-1]
            for fi in range(4):
                if _can_on_foundation(card, g.found[fi]):
                    _move_cards(pile, g.found[fi], 1)
                    moved += 1
                    found = True
                    break
            if found:
                break
        if not found:
            break
    return f"Auto-moved {moved}" if moved else "No auto-moves"


def _iter_sources(g: Game):
    if g.waste:
        yield "waste", g.waste, -1
    for i in range(7):
        if g.tabs[i] and g.tabs[i][-1].up:
            yield f"t{i}", g.tabs[i], i


def board_html(g: Game, sel: str) -> str:
    sel = sel or ""

    def card_face(c: Card, selected: bool = False) -> str:
        if not c.up:
            return '<span class="sol-card back"></span>'
        sym = SUIT_SYM[c.suit]
        extra = " selected" if selected else ""
        return (
            f'<span class="sol-card {c.color}{extra}" title="{html.escape(c.rank + sym)}">'
            f'<span class="rank">{html.escape(c.rank)}</span>'
            f'<span class="suit">{sym}</span></span>'
        )

    def submit(action: str, label: str, inner: str, selected: bool = False) -> str:
        cls = "sol-pile" + (" selected" if selected else "")
        return (
            f'<button type="submit" class="{cls}" name="_action" value="{html.escape(action)}">'
            f'{inner}<span class="sr">{html.escape(label)}</span></button>'
        )

    out: list[str] = ['<div class="sol-board">']

    out.append('<section class="sol-top">')
    out.append('<div class="sol-foundations">')
    for i in range(4):
        pid = f"f{i}"
        pile = g.found[i]
        inner = card_face(pile[-1]) if pile else '<span class="sol-slot">A</span>'
        out.append(submit(f"tap_{pid}", "Foundation", inner, sel == pid))
    out.append("</div>")

    out.append('<div class="sol-stock-row">')
    stock_n = len(g.stock)
    inner = f'<span class="sol-card back"></span><span class="count">{stock_n}</span>' if stock_n else '<span class="sol-slot">∅</span>'
    out.append(submit("drawFromStock", "Stock", inner))
    waste = g.waste
    w_inner = card_face(waste[-1]) if waste else '<span class="sol-slot">—</span>'
    out.append(submit("tap_waste", "Waste", w_inner, sel == "waste"))
    out.append("</div></section>")

    out.append('<section class="sol-tableau">')
    for col in range(7):
        pid = f"t{col}"
        pile = g.tabs[col]
        out.append('<div class="sol-column">')
        out.append(submit(f"tap_{pid}", f"Column {col + 1}", "", sel == pid))
        out.append('<div class="sol-stack">')
        for i, c in enumerate(pile):
            off = i * 1.4
            sel_card = sel == pid and i == len(pile) - 1
            out.append(
                f'<div class="sol-card-wrap" style="--off:{off}rem">'
                + card_face(c, sel_card)
                + "</div>"
            )
        if not pile:
            out.append('<span class="sol-slot col">K</span>')
        out.append("</div></div>")
    out.append("</section></div>")

    return _sanitize_board_html("".join(out))


def _sanitize_board_html(raw: str) -> str:
    raw = re.sub(r"\s*onclick\s*=\s*['\"][^'\"]*['\"]", "", raw, flags=re.I)
    raw = re.sub(r"<script\b[^>]*>.*?</script>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<form\b[^>]*>|</form>", "", raw, flags=re.I)
    return raw


def sol_new() -> str:
    return serialize(new_game())


def sol_board(state: str, sel: str) -> str:
    return board_html(deserialize(state), sel or "")


def sol_tap(state: str, sel: str, pile: str) -> dict[str, Any]:
    g = deserialize(state)
    ng, nsel, msg = tap(g, sel or "", pile or "")
    return {"state": serialize(ng), "sel": nsel, "msg": msg}


def sol_draw(state: str) -> dict[str, Any]:
    g = deserialize(state)
    msg = draw(g)
    return {"state": serialize(g), "sel": "", "msg": msg}


def sol_auto(state: str) -> dict[str, Any]:
    g = deserialize(state)
    msg = auto_foundation(g)
    return {"state": serialize(g), "sel": "", "msg": msg}


def sol_won(state: str) -> int:
    return 1 if deserialize(state).won() else 0

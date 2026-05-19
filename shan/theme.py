"""Site theme (dark / light) via cookie — no JavaScript."""
from __future__ import annotations

import html
from urllib.parse import quote

THEME_COOKIE = "shan_theme"
VALID_THEMES = frozenset({"dark", "light"})
DEFAULT_THEME = "dark"

GALLERY_CARDS: tuple[tuple[str, str, str], ...] = (
    ("hello-web", "Counter", "+1 / −1 / reset"),
    ("greet-web", "Greeting", "Text input + hello"),
    ("lights-web", "Fan lamp", "Toggle on/off"),
    ("score-web", "Scoreboard", "Home vs away"),
    ("todo-web", "Todo", "Three toggle items"),
    ("calc-web", "Calculator", "Digit pad"),
    ("password-web", "Password", "Secure generator"),
    ("solitaire-web", "Solitaire", "Klondike card game"),
    ("fan-image-web", "Encrypted images", "QFan seal & open"),
)


def normalize_theme(value: str | None) -> str:
    if value and value.strip().lower() in VALID_THEMES:
        return value.strip().lower()
    return DEFAULT_THEME


def toggle_theme(current: str) -> str:
    return "light" if normalize_theme(current) == "dark" else "dark"


def safe_return(path: str | None, *, default: str = "/gallery.html") -> str:
    if not path:
        return default
    p = path.strip()
    if not p.startswith("/") or "//" in p or p.startswith("/theme"):
        return default
    return p[:512]


def parse_cookie_header(header: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not header:
        return out
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, val = part.partition("=")
        out[name.strip()] = val.strip()
    return out


def theme_from_cookies(cookies: dict[str, str]) -> str:
    return normalize_theme(cookies.get(THEME_COOKIE))


def cookie_header(theme: str) -> str:
    t = normalize_theme(theme)
    return f"{THEME_COOKIE}={t}; Path=/; Max-Age=31536000; SameSite=Lax"


def theme_switch_html(theme: str, return_path: str) -> str:
    t = normalize_theme(theme)
    ret = quote(safe_return(return_path), safe="/")
    dark = "true" if t == "dark" else "false"
    light = "true" if t == "light" else "false"
    return f"""<nav class="theme-switch" aria-label="Color theme">
  <a class="theme-opt" href="/theme/set?theme=dark&amp;return={ret}" aria-current="{dark}">Dark</a>
  <a class="theme-opt" href="/theme/set?theme=light&amp;return={ret}" aria-current="{light}">Light</a>
</nav>"""


def site_chrome_html(
    theme: str,
    return_path: str,
    *,
    back_href: str = "/gallery.html",
    back_label: str = "← Examples",
    show_back: bool = True,
) -> str:
    back = (
        f'<a class="nav-back" href="{html.escape(back_href)}">{html.escape(back_label)}</a>'
        if show_back
        else '<span class="nav-spacer" aria-hidden="true"></span>'
    )
    return f"""<header class="site-chrome">
  <a class="site-brand" href="/gallery.html">Shàn</a>
  {back}
  {theme_switch_html(theme, return_path)}
</header>"""


def page_shell(
    *,
    title: str,
    theme: str,
    return_path: str,
    body: str,
    stylesheets: tuple[str, ...] = ("/styles/base.css",),
    body_class: str = "",
    chrome_show_back: bool = True,
    chrome_back_href: str = "/gallery.html",
    chrome_back_label: str = "← Examples",
) -> str:
    t = normalize_theme(theme)
    ret = safe_return(return_path)
    chrome = site_chrome_html(
        t,
        ret,
        back_href=chrome_back_href,
        back_label=chrome_back_label,
        show_back=chrome_show_back,
    )
    links = "\n".join(f'  <link rel="stylesheet" href="{html.escape(h)}"/>' for h in stylesheets)
    cls = f' class="{html.escape(body_class)}"' if body_class else ""
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{html.escape(t)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="dark light"/>
  <title>{html.escape(title)}</title>
{links}
</head>
<body{cls}>
{chrome}
{body}
</body>
</html>"""


def render_gallery(theme: str, available_stems: frozenset[str]) -> str:
    t = normalize_theme(theme)
    ret = safe_return("/gallery.html")
    cards: list[str] = []
    delay = 0.05
    for stem, heading, desc in GALLERY_CARDS:
        if stem not in available_stems:
            continue
        cards.append(
            f'    <a class="gallery-card" href="/app/{html.escape(stem)}" '
            f'style="animation-delay:{delay:.2f}s">'
            f"<h2>{html.escape(heading)}</h2>"
            f"<p>{html.escape(desc)}</p></a>"
        )
        delay += 0.05
    grid = "\n".join(cards) if cards else "    <p class=\"gallery-empty\">No examples found.</p>"
    body = f"""<main class="gallery-page">
  <header class="hero">
    <h1>Shàn web examples</h1>
    <p class="lead">Server-rendered HTML and CSS — <strong>no JavaScript</strong> in the browser.</p>
  </header>
  <nav class="gallery-grid">
{grid}
  </nav>
  <p class="gallery-footer">
    CLI: <code>python3 -m shan serve greet-web</code>
  </p>
</main>"""
    return page_shell(
        title="Shàn Web Examples",
        theme=t,
        return_path=ret,
        body=body,
        stylesheets=("/styles/base.css", "/styles/gallery.css"),
        body_class="gallery-page",
        chrome_show_back=False,
    )

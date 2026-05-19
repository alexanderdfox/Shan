"""Shared security rules for Shàn (interpreter, web compile, checker, serve)."""
from __future__ import annotations

import re
from pathlib import Path

# Python/JS identifiers for env keys, handlers, function names
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# CSS selector for mount (Phase 1: id or simple class)
MOUNT_SELECTOR_RE = re.compile(r"^#[A-Za-z][\w-]*$|^\.[A-Za-z][\w-]*$")

FORBIDDEN_HTML_TAGS = frozenset(
    {
        "script", "iframe", "object", "embed", "applet", "base", "link",
        "meta", "form", "frame", "frameset", "template",
    }
)

# Allowlisted void/markup tags for web compile (subset of HTML + shan tags)
ALLOWED_HTML_TAGS = frozenset(
    {
        "html", "head", "body", "title", "style",
        "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "li", "dl", "dt", "dd",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td",
        "section", "article", "header", "footer", "nav", "main", "aside",
        "figure", "figcaption", "blockquote", "pre", "code", "em", "strong",
        "small", "label", "fieldset", "legend", "button", "a", "img", "br", "hr",
        "details", "summary",
        "input", "textarea", "select", "option",
        "bind", "input-bind",
        "area", "col", "param", "source", "track", "wbr",
    }
)

FORBIDDEN_ATTR_PREFIXES = ("on",)  # onclick, onerror, …
FORBIDDEN_ATTR_NAMES = frozenset({"formaction", "xlink:href", "xmlns"})

SAFE_INPUT_TYPES = frozenset(
    {
        "text", "search", "email", "tel", "url", "password", "number", "range",
        "date", "time", "color", "hidden", "checkbox", "file",
    }
)

SAFE_DOM_EVENTS = frozenset(
    {
        "click", "dblclick", "change", "input", "submit", "keydown", "keyup", "keypress",
        "mousedown", "mouseup", "mouseover", "mouseout", "focus", "blur",
    }
)

# Compiled / static markup must not contain these patterns
UNSAFE_MARKUP_RE = re.compile(
    r"<script\b|</script\b|javascript\s*:|data\s*:\s*text/html|"
    r"\bon\w+\s*=|<\s*iframe\b|<\s*object\b|<\s*embed\b",
    re.IGNORECASE,
)

APP_STEM_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-web$")


def require_ident(name: str, *, what: str = "name") -> str:
    if not name or not IDENT_RE.match(name):
        raise ValueError(f"invalid {what}: {name!r} (use letters, digits, underscore)")
    return name


def require_mount_selector(selector: str) -> str:
    s = (selector or "#app").strip()
    if not MOUNT_SELECTOR_RE.match(s):
        raise ValueError(f"invalid mount selector: {s!r} (use #id or .class)")
    return s


def require_app_stem(stem: str) -> str:
    s = stem.strip().lower()
    if not APP_STEM_RE.match(s) or ".." in s or "/" in s or "\\" in s:
        raise ValueError(f"invalid app name: {stem!r}")
    return s


def require_safe_input_type(itype: str) -> str:
    t = (itype or "text").strip().lower()
    if t not in SAFE_INPUT_TYPES:
        raise ValueError(f"unsupported input type: {itype!r}")
    return t


def parse_on_attr(on: str) -> tuple[str, str]:
    """Parse on=\"click:handler\" → (event, handler)."""
    parts = on.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid on= attribute: {on!r} (use event:handler)")
    event, handler = parts[0].strip().lower(), parts[1].strip()
    if event not in SAFE_DOM_EVENTS:
        raise ValueError(f"event not allowed: {event!r}")
    require_ident(handler, what="handler")
    return event, handler


def check_html_tag(tag: str) -> None:
    t = tag.lower()
    if t in FORBIDDEN_HTML_TAGS:
        raise ValueError(f"forbidden HTML tag: <{tag}>")
    if t not in ALLOWED_HTML_TAGS and t not in ("bind", "input-bind", "html-bind", "img-bind"):
        raise ValueError(f"tag not allowed in web markup: <{tag}>")


def check_html_attr(name: str, value: str) -> None:
    n = name.lower()
    if n in FORBIDDEN_ATTR_NAMES:
        raise ValueError(f"forbidden attribute: {name}")
    if any(n.startswith(p) for p in FORBIDDEN_ATTR_PREFIXES):
        raise ValueError(f"inline event handlers are forbidden: {name}")
    if n in ("href", "src", "action", "formaction") and re.search(r"javascript\s*:", value, re.I):
        raise ValueError(f"javascript: URLs are forbidden in {name}")


def assert_safe_markup(html: str) -> None:
    if UNSAFE_MARKUP_RE.search(html):
        raise ValueError("markup contains forbidden patterns (script, javascript:, inline on*=)")


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def resolve_path_under(base: Path, user_path: str | Path) -> Path:
    """Resolve user_path under base; reject traversal outside base."""
    base_r = base.resolve()
    raw = Path(str(user_path))
    target = (base_r / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        target.relative_to(base_r)
    except ValueError:
        raise PermissionError(f"path escapes allowed directory: {user_path}") from None
    return target


def expr_attr_is_safe(attr: str) -> bool:
    """Block dunder attribute access in expression source."""
    return not is_dunder(attr)

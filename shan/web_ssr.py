"""Server-rendered Shàn web apps — HTML + CSS only, no JavaScript."""
from __future__ import annotations

import html
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shan.expr import eval_expr
from shan.parser import ShanNode, parse_file
from shan.security import check_html_attr, check_html_tag, require_ident, require_safe_input_type
from shan.values import truthy

LOGIC_TAGS = frozenset(
    {
        "page", "fan", "rib", "block",
        "value", "set", "list", "dict", "del",
        "half", "yes", "no", "secret", "observe",
        "show", "ask", "when", "otherwise", "each", "while",
        "break", "continue", "return",
        "fn", "call", "import", "class", "try", "except", "finally",
        "open", "when-half", "case", "deny", "assert",
        "file-read", "file-write", "seal", "unseal", "fetch", "render",
    }
)

VOID_HTML = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "bind", "html-bind", "img-bind", "input-bind",
    }
)

# Derived each request; not round-tripped in hidden fields
_DERIVED_ENV_KEYS = frozenset(
    {"orig_url", "stego_url", "ig_stego_url", "noise_url", "opened_url", "match_badge_html"}
)


@dataclass
class WebApp:
    stem: str
    title: str
    markup: list[ShanNode]
    values: list[ShanNode]
    functions: dict[str, ShanNode] = field(default_factory=dict)


def _parse_app(path: Path) -> WebApp:
    root = parse_file(path)
    if root.tag != "page":
        raise ValueError("root must be <page>")
    title = root.attrs.get("title", path.stem)
    markup: list[ShanNode] = []
    values: list[ShanNode] = []
    functions: dict[str, ShanNode] = {}
    for fan in root.children:
        if fan.tag != "fan":
            continue
        for rib in fan.children:
            if rib.tag != "rib":
                continue
            for c in rib.children:
                if c.tag == "value":
                    values.append(c)
                elif c.tag == "fn":
                    functions[require_ident(c.attrs["name"], what="function name")] = c
                elif c.tag not in LOGIC_TAGS:
                    markup.append(c)
    return WebApp(stem=path.stem, title=title, markup=markup, values=values, functions=functions)


def _apply_op(lhs: str, op: str, rhs: str) -> str:
    """Evaluate two operands for the web calculator (SSR)."""
    try:
        a = float(str(lhs or "0"))
        b = float(str(rhs or "0"))
    except (TypeError, ValueError):
        return "Error"
    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    elif op == "/":
        if b == 0:
            return "Error"
        result = a / b
    else:
        return str(rhs)
    if result != result:  # NaN
        return "Error"
    if abs(result - round(result)) < 1e-9:
        return str(int(round(result)))
    text = f"{result:.10f}".rstrip("0").rstrip(".")
    return text or "0"


_PWD_UPPER = string.ascii_uppercase
_PWD_LOWER = string.ascii_lowercase
_PWD_DIGITS = string.digits
_PWD_SYMBOLS = "!@#$%^&*()-_=+[]{}|;:,.<>?"


def _env_flag(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def gen_password(length: Any, upper: Any, lower: Any, digits: Any, symbols: Any) -> str:
    """Cryptographically secure password (secrets module, server-side only)."""
    try:
        n = int(length)
    except (TypeError, ValueError):
        n = 16
    n = max(8, min(128, n))

    pools: list[str] = []
    if _env_flag(upper):
        pools.append(_PWD_UPPER)
    if _env_flag(lower):
        pools.append(_PWD_LOWER)
    if _env_flag(digits):
        pools.append(_PWD_DIGITS)
    if _env_flag(symbols):
        pools.append(_PWD_SYMBOLS)
    if not pools:
        return ""

    rng = secrets.SystemRandom()
    chars = [rng.choice(pool) for pool in pools]
    alphabet = "".join(pools)
    while len(chars) < n:
        chars.append(rng.choice(alphabet))
    rng.shuffle(chars)
    return "".join(chars)


def _builtin_env() -> dict[str, Any]:
    from shan import solitaire as sol
    from shan.fan_cipher import fan_audit_summary
    from shan.image_fan import (
        detect_mime,
        fan_noise_from_sealed,
        fan_open_image,
        fan_qfan_round,
        fan_seal_image,
        fan_stego_hide,
        fan_stego_reveal,
        img_data_uri,
        sample_image_b64,
    )

    return {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "apply_op": _apply_op,
        "gen_password": gen_password,
        "sol_new": sol.sol_new,
        "sol_board": sol.sol_board,
        "sol_tap": sol.sol_tap,
        "sol_draw": sol.sol_draw,
        "sol_auto": sol.sol_auto,
        "sol_won": sol.sol_won,
        "fan_seal_image": fan_seal_image,
        "fan_audit_summary": fan_audit_summary,
        "fan_noise_from_sealed": fan_noise_from_sealed,
        "fan_qfan_round": fan_qfan_round,
        "fan_stego_hide": fan_stego_hide,
        "fan_stego_reveal": fan_stego_reveal,
        "fan_open_image": fan_open_image,
        "img_data_uri": img_data_uri,
        "sample_image_b64": sample_image_b64,
        "detect_mime": detect_mime,
        "True": True,
        "False": False,
        "None": None,
    }


def _initial_env(app: WebApp) -> dict[str, Any]:
    env: dict[str, Any] = {}
    builtins = _builtin_env()
    for node in app.values:
        name = require_ident(node.attrs["name"])
        if node.attrs.get("expr"):
            env[name] = eval_expr(node.attrs["expr"], env, builtins)
        elif node.text:
            env[name] = node.text.strip()
        else:
            env[name] = None
    return env


def _coerce_field(name: str, raw: str, sample: Any) -> Any:
    if sample is None:
        return raw
    if isinstance(sample, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(sample, int) and not isinstance(sample, bool):
        try:
            return int(raw)
        except ValueError:
            return 0
    if isinstance(sample, float):
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return raw


def _apply_form(env: dict[str, Any], fields: dict[str, str], app: WebApp) -> None:
    defaults = _initial_env(app)
    for key, raw in fields.items():
        if key == "_action":
            continue
        if key in defaults or key in env:
            sample = defaults.get(key, env.get(key))
            env[key] = _coerce_field(key, raw, sample)


def _run_function(app: WebApp, env: dict[str, Any], name: str) -> None:
    fn = app.functions.get(name)
    if not fn:
        return
    builtins = _builtin_env()
    arg_names = [a.strip() for a in fn.attrs.get("args", "").split(",") if a.strip()]

    def _eval_expr(source: str | None) -> Any:
        if not source:
            return None
        return eval_expr(source, env, builtins)

    def _run_children(children: list[ShanNode]) -> None:
        i = 0
        while i < len(children):
            n = children[i]
            if n.tag == "when":
                if truthy(_eval_expr(n.attrs.get("test"))):
                    _run_children(n.children)
                    i += 1
                    if i < len(children) and children[i].tag == "otherwise":
                        i += 1
                elif i + 1 < len(children) and children[i + 1].tag == "otherwise":
                    _run_children(children[i + 1].children)
                    i += 2
                else:
                    i += 1
            elif n.tag == "set":
                env[n.attrs["name"]] = _eval_expr(n.attrs.get("expr", "None"))
                i += 1
            elif n.tag == "call":
                callee = n.attrs["name"]
                args_s = n.attrs.get("args", "").strip()
                args = list(_eval_expr(f"[{args_s}]")) if args_s else []
                if callee in app.functions:
                    callee_node = app.functions[callee]
                    for j, an in enumerate(
                        [a.strip() for a in callee_node.attrs.get("args", "").split(",") if a.strip()]
                    ):
                        if j < len(args):
                            env[an] = args[j]
                    _run_children(callee_node.children)
                i += 1
            elif n.tag == "render":
                i += 1
            elif n.tag == "open":
                _run_children(n.children)
                i += 1
            else:
                i += 1

    _run_children(fn.children)
    # keep env mutations from handler


def _render_markup(nodes: list[ShanNode], env: dict[str, Any]) -> str:
    return "".join(_render_node(n, env) for n in nodes)


def _visible_input_names(nodes: list[ShanNode]) -> set[str]:
    out: set[str] = set()

    def walk(ns: list[ShanNode]) -> None:
        for n in ns:
            if n.tag == "input-bind":
                out.add(n.attrs.get("name", ""))
            walk(n.children)

    walk(nodes)
    return out


def _needs_multipart(nodes: list[ShanNode]) -> bool:
    def walk(ns: list[ShanNode]) -> bool:
        for n in ns:
            if n.tag == "input-bind" and n.attrs.get("type") == "file":
                return True
            if walk(n.children):
                return True
        return False

    return walk(nodes)


def _hidden_fields(env: dict[str, Any], markup: list[ShanNode]) -> str:
    visible = _visible_input_names(markup)
    parts: list[str] = []
    for key, val in env.items():
        if key in visible or key in _DERIVED_ENV_KEYS:
            continue
        parts.append(
            f'<input type="hidden" name="{html.escape(key)}" '
            f'value="{html.escape("" if val is None else str(val))}" />'
        )
    return "\n".join(parts)


_MAX_INLINE_IMG_BYTES = 768 * 1024


def _preview_src(stem: str, b64: str, mime: str) -> str:
    """Inline data: URI for small images; cached /app/…/img/ route for large ones."""
    import base64

    from shan.image_fan import img_data_uri
    from shan.img_cache import img_preview_url

    if not b64:
        return ""
    try:
        raw = base64.b64decode(str(b64).strip())
    except (ValueError, TypeError):
        return ""
    if len(raw) <= _MAX_INLINE_IMG_BYTES:
        return img_data_uri(mime, b64)
    return img_preview_url(stem, b64, mime)


def detect_mime_after_stego(env: dict[str, Any]) -> str:
    import base64

    from shan.image_fan import detect_mime

    stego = env.get("stego_b64", "")
    if not stego:
        return str(env.get("mime") or "image/png")
    return detect_mime(base64.b64decode(stego.strip()))


def _apply_fan_crypto(env: dict[str, Any], *, round_trip: bool) -> None:
    """Instagram-sized cover → QFan seal → noise → stego (+ optional reveal)."""
    from shan.image_fan import (
        export_instagram_jpeg,
        fan_seal_image,
        fan_stego_hide,
        fan_stego_reveal,
        prepare_instagram_cover,
    )
    from shan.instagram import layout_label, normalize_layout

    if not env.get("plain_b64"):
        return
    layout = normalize_layout(str(env.get("ig_layout") or "square"))
    try:
        ribs = int(env.get("ribs") or 8)
    except (TypeError, ValueError):
        ribs = 8
    source_b64 = prepare_instagram_cover(env["plain_b64"], layout)
    env["source_b64"] = source_b64
    env["cover_b64"] = source_b64
    env["mime"] = "image/png"
    pack = fan_seal_image(source_b64, str(env.get("key") or ""), ribs=ribs, ig_layout=layout)
    env["sealed"] = pack["sealed"]
    env["noise_b64"] = pack["noise_b64"]
    env["summary"] = pack["summary"]
    stego_b64, noise_b64 = fan_stego_hide(
        source_b64, pack["sealed"], pack["noise_b64"]
    )
    env["stego_b64"] = stego_b64
    env["noise_b64"] = noise_b64
    env["plain_b64"] = stego_b64
    env["ig_stego_b64"] = export_instagram_jpeg(stego_b64, layout)
    env["ig_layout"] = layout
    split = noise_b64 != pack["noise_b64"]
    if round_trip:
        env["opened_b64"] = fan_stego_reveal(
            stego_b64, str(env.get("key") or ""), noise_b64
        )
        env["match_ok"] = 1 if env["opened_b64"] == source_b64 else 0
        if env["match_ok"]:
            if split:
                env["status"] = (
                    f"Instagram {layout_label(layout)} — seal split: marker in cover, "
                    "full message in noise (save panels 1 + 2 PNG)"
                )
            else:
                env["status"] = (
                    f"Instagram {layout_label(layout)} — message hidden in cover pixels; "
                    "save panel 1 PNG to reveal (panel 3 JPEG loses LSB on recompress)"
                )
        else:
            env["status"] = "Decrypted image does not match cover (wrong key?)"
    else:
        env["opened_b64"] = ""
        env["match_ok"] = 0
        env["status"] = (
            f"Encrypted at {layout_label(layout)} — panel 1 is the altered cover "
            "with the message hidden inside"
        )


def _apply_fan_qfan_round(env: dict[str, Any]) -> None:
    _apply_fan_crypto(env, round_trip=True)


def _apply_fan_seal(env: dict[str, Any]) -> None:
    _apply_fan_crypto(env, round_trip=False)


def _apply_fan_reveal(env: dict[str, Any]) -> None:
    from shan.image_fan import fan_stego_reveal

    stego = env.get("stego_b64", "")
    if not stego:
        return
    source = env.get("source_b64") or env.get("cover_b64") or ""
    env["opened_b64"] = fan_stego_reveal(
        stego, str(env.get("key") or ""), env.get("noise_b64", "")
    )
    env["match_ok"] = 1 if env["opened_b64"] == source else 0
    if env["match_ok"]:
        env["status"] = "Stego revealed — matches Instagram cover"
    else:
        env["status"] = "Reveal failed — wrong key or not a QFan stego PNG"


def _refresh_preview_urls(env: dict[str, Any], stem: str) -> None:
    plain = env.get("plain_b64", "")
    source = env.get("source_b64", "")
    mime = env.get("mime", "image/png")
    stego = env.get("stego_b64", "")
    ig_stego = env.get("ig_stego_b64", "")
    noise = env.get("noise_b64", "")
    opened = env.get("opened_b64", "")
    display = stego or plain
    env["orig_url"] = _preview_src(stem, display, detect_mime_after_stego(env) if stego else mime)
    env["source_url"] = _preview_src(stem, source, mime) if source and source != stego else ""
    env["stego_url"] = _preview_src(stem, stego, detect_mime_after_stego(env) if stego else mime)
    env["ig_stego_url"] = _preview_src(stem, ig_stego, "image/jpeg") if ig_stego else ""
    env["noise_url"] = _preview_src(stem, noise, "image/png")
    env["opened_url"] = _preview_src(stem, opened, mime)
    if _env_flag(env.get("match_ok")):
        env["match_badge_html"] = '<span class="match-badge">matches original</span>'
    else:
        env["match_badge_html"] = ""


def _render_node(node: ShanNode, env: dict[str, Any]) -> str:
    tag = node.tag
    if tag == "#text":
        return html.escape(node.text)
    if tag == "bind":
        name = require_ident(node.attrs.get("name", ""), what="bind name")
        val = env.get(name, "")
        return f'<span class="val">{html.escape("" if val is None else str(val))}</span>'
    if tag == "html-bind":
        name = require_ident(node.attrs.get("name", ""), what="html-bind name")
        val = env.get(name, "")
        return "" if val is None else str(val)
    if tag == "img-bind":
        name = require_ident(node.attrs.get("name", ""), what="img-bind name")
        src = env.get(name, "")
        if not src:
            return ""
        alt = html.escape(node.attrs.get("alt", ""))
        cls = node.attrs.get("class", "")
        cls_attr = f' class="{html.escape(cls)}"' if cls else ""
        return f'<img src="{html.escape(str(src))}" alt="{alt}"{cls_attr} />'
    if tag == "input-bind":
        name = require_ident(node.attrs.get("name", ""), what="input-bind name")
        itype = require_safe_input_type(node.attrs.get("type", "text"))
        if itype == "checkbox":
            checked = _env_flag(env.get(name, 0))
            label = html.escape(node.attrs.get("label", name))
            hidden = f'<input type="hidden" name="{html.escape(name)}" value="0"/>'
            chk = " checked" if checked else ""
            return (
                f'<label class="check">'
                f"{hidden}"
                f'<input type="checkbox" name="{html.escape(name)}" value="1"{chk} />'
                f"<span>{label}</span></label>"
            )
        if itype == "file":
            accept = node.attrs.get("accept", "image/*")
            return (
                f'<input type="file" name="{html.escape(name)}" '
                f'accept="{html.escape(accept)}" autocomplete="off" />'
            )
        placeholder = node.attrs.get("placeholder", "")
        ph = f' placeholder="{html.escape(placeholder)}"' if placeholder else ""
        val = env.get(name, "")
        extra = ' autocomplete="off" data-1p-ignore data-lpignore="true"'
        if itype == "number":
            if name == "length":
                extra += ' min="8" max="128" step="1"'
            elif name == "ribs":
                extra += ' min="2" max="16" step="1"'
            else:
                extra += ' step="1"'
        return (
            f'<input type="{html.escape(itype)}" name="{html.escape(name)}" '
            f'value="{html.escape("" if val is None else str(val))}"{ph}{extra} />'
        )
    if tag in LOGIC_TAGS:
        return ""
    check_html_tag(tag)
    attrs = dict(node.attrs)
    on = attrs.pop("on", None)
    attr_parts: list[str] = []
    if tag == "button" and on:
        attrs.pop("type", None)
        _, handler = on.split(":", 1)
        handler = handler.strip()
        require_ident(handler, what="handler")
        attr_parts.append('type="submit"')
        attr_parts.append('name="_action"')
        attr_parts.append(f'value="{html.escape(handler)}"')
    for k, v in attrs.items():
        check_html_attr(k, v)
        attr_parts.append(f'{html.escape(k)}="{html.escape(v)}"')
    attr_s = (" " + " ".join(attr_parts)) if attr_parts else ""
    void = tag in VOID_HTML or (not node.children and not node.text)
    if void:
        return f"<{tag}{attr_s} />"
    inner = html.escape(node.text) if node.text else ""
    inner += "".join(_render_node(c, env) for c in node.children)
    return f"<{tag}{attr_s}>{inner}</{tag}>"


def _apply_uploads(env: dict[str, Any], files: dict[str, bytes]) -> None:
    import base64

    from shan.image_fan import detect_mime

    for name, raw in files.items():
        if not raw:
            continue
        b64 = base64.b64encode(raw).decode("ascii")
        env[f"upload_{name}_b64"] = b64
        if name == "image":
            env["plain_b64"] = b64
            env["mime"] = detect_mime(raw)


def render_app_page(
    app: WebApp,
    fields: dict[str, str],
    *,
    files: dict[str, bytes] | None = None,
    theme: str = "dark",
) -> str:
    from shan.theme import page_shell

    env = _initial_env(app)
    _apply_form(env, fields, app)
    if files:
        _apply_uploads(env, files)
    action = fields.get("_action", "").strip()
    if action.startswith("tap_"):
        env["move"] = action[4:]
        if "applyTap" in app.functions:
            _run_function(app, env, "applyTap")
    elif action and action in app.functions:
        _run_function(app, env, action)
        if app.stem == "fan-image-web":
            if action == "qfanRound":
                _apply_fan_qfan_round(env)
            elif action == "seal":
                _apply_fan_seal(env)
            elif action == "reveal":
                _apply_fan_reveal(env)
    if files and env.get("plain_b64") and not action:
        env["status"] = "Original loaded from upload — press QFan encrypt"
    if "plain_b64" in env:
        _refresh_preview_urls(env, app.stem)
    inner = _hidden_fields(env, app.markup) + "\n" + _render_markup(app.markup, env)
    stem = app.stem
    return_path = f"/app/{stem}"
    enctype = ' enctype="multipart/form-data"' if _needs_multipart(app.markup) else ""
    form = (
        f'<form method="post" action="/app/{html.escape(stem)}" class="shan-app"'
        f' autocomplete="off" data-1p-ignore="true" data-lpignore="true"{enctype}>\n'
        f"{inner}\n"
        f"  </form>"
    )
    return page_shell(
        title=app.title,
        theme=theme,
        return_path=return_path,
        body=form,
        stylesheets=("/styles/base.css", f"/styles/{stem}.css"),
    )


class WebAppRegistry:
    def __init__(self, examples_dir: Path) -> None:
        self._apps: dict[str, WebApp] = {}
        self._paths: dict[str, Path] = {}
        for path in sorted(examples_dir.glob("*-web.shan")):
            app = _parse_app(path)
            self._apps[app.stem] = app
            self._paths[app.stem] = path

    def stems(self) -> frozenset[str]:
        return frozenset(self._apps.keys())

    def render(
        self,
        stem: str,
        fields: dict[str, str],
        *,
        files: dict[str, bytes] | None = None,
        theme: str = "dark",
    ) -> str:
        app = self._apps.get(stem)
        if not app:
            raise KeyError(stem)
        return render_app_page(app, fields, files=files, theme=theme)

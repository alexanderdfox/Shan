"""Dev server for Shàn web apps (HTTPS by default; optional HTTP-only)."""
from __future__ import annotations

import http.server
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from shan.security import require_app_stem

# No JavaScript in the browser — server-rendered HTML only
_CSP_NO_JS = (
    "default-src 'self'; "
    "script-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_DEV_CSP_HTTPS = _CSP_NO_JS + "; upgrade-insecure-requests"
_HSTS = "max-age=86400"
_HOST = "127.0.0.1"

# Browser/proxy often closes idle or duplicate TLS connections — not a server bug.
_CLIENT_DISCONNECT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionResetError,
    BrokenPipeError,
    ConnectionAbortedError,
)


def _is_client_disconnect(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    if isinstance(exc, _CLIENT_DISCONNECT_ERRORS):
        return True
    return isinstance(exc, OSError) and getattr(exc, "errno", None) in (54, 32, 104)


class _ShanServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        if _is_client_disconnect(sys.exc_info()[1]):
            return
        super().handle_error(request, client_address)


def _wait_tls_listening(port: int, timeout: float = 10.0) -> bool:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = socket.create_connection((_HOST, port), timeout=0.25)
            tls = ctx.wrap_socket(raw, server_hostname=_HOST)
            tls.close()
            return True
        except OSError:
            time.sleep(0.06)
    return False


def open_browser_https(url: str) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError(f"refusing to open non-HTTPS URL: {url}")
    if sys.platform == "darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    webbrowser.open(url, new=2)


def project_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "shan" / "__main__.py").is_file():
            return p
    return start.parent


def list_web_apps(root: Path) -> list[Path]:
    ex = root / "examples"
    return sorted(ex.glob("*-web.shan")) if ex.is_dir() else []


def allowed_app_stems(root: Path) -> frozenset[str]:
    return frozenset(p.stem for p in list_web_apps(root))


def compile_web_app(shan_file: Path, root: Path) -> Path:
    from shan.compile_web import compile_file, copy_runtime

    web_root = root / "examples" / "web"
    apps_dir = web_root / "dist" / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    out = apps_dir / f"{shan_file.stem}.js"
    compile_file(shan_file, out)
    copy_runtime(web_root / "dist")
    return out


def compile_all_web_apps(root: Path) -> int:
    apps = list_web_apps(root)
    for path in apps:
        compile_web_app(path, root)
    return len(apps)


def prepare_web_dist(shan_file: Path, project: Path) -> Path:
    return project / "examples" / "web"


def _security_headers(handler: http.server.BaseHTTPRequestHandler, *, csp: str, hsts: bool) -> None:
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    handler.send_header("Content-Security-Policy", csp)
    handler.send_header("Cache-Control", "no-store")
    if hsts:
        handler.send_header("Strict-Transport-Security", _HSTS)


def _parse_form_body(
    handler: http.server.BaseHTTPRequestHandler,
) -> tuple[dict[str, str], dict[str, bytes]]:
    from shan.form_parse import parse_form_body

    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length) if length else b""
    try:
        return parse_form_body(raw, handler.headers.get("Content-Type"))
    except ValueError as e:
        raise ValueError(str(e)) from e


def _make_handler(
    port: int,
    web_root: Path,
    registry,
    *,
    csp: str,
    hsts: bool,
) -> type[http.server.SimpleHTTPRequestHandler]:
    root_resolved = web_root.resolve()
    allowed = registry.stems()

    class Handler(http.server.SimpleHTTPRequestHandler):
        server_port = port
        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".css": "text/css",
            ".html": "text/html; charset=utf-8",
        }

        def end_headers(self) -> None:
            _security_headers(self, csp=csp, hsts=hsts)
            super().end_headers()

        def _cookies(self) -> dict[str, str]:
            from shan.theme import parse_cookie_header

            return parse_cookie_header(self.headers.get("Cookie"))

        def _current_theme(self) -> str:
            from shan.theme import theme_from_cookies

            return theme_from_cookies(self._cookies())

        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except _CLIENT_DISCONNECT_ERRORS:
                pass

        def _send_html(
            self, body: str, code: int = 200, *, set_cookie: str | None = None
        ) -> None:
            data = body.encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                if set_cookie:
                    self.send_header("Set-Cookie", set_cookie)
                self.end_headers()
                self.wfile.write(data)
            except _CLIENT_DISCONNECT_ERRORS:
                pass

        def _handle_theme(self, parsed) -> None:
            from shan.theme import (
                cookie_header,
                normalize_theme,
                safe_return,
                toggle_theme,
                theme_from_cookies,
            )

            qs = parse_qs(parsed.query)
            ret = safe_return(qs.get("return", [""])[0] if qs.get("return") else None)
            if parsed.path == "/theme/toggle":
                theme = toggle_theme(theme_from_cookies(self._cookies()))
            else:
                theme = normalize_theme(qs.get("theme", [""])[0] if qs.get("theme") else None)
            self.send_response(302)
            self.send_header("Location", ret)
            _security_headers(self, csp=csp, hsts=hsts)
            self.send_header("Set-Cookie", cookie_header(theme))
            self.end_headers()

        def _handle_gallery(self) -> None:
            from shan.theme import render_gallery

            theme = self._current_theme()
            page = render_gallery(theme, registry.stems())
            self._send_html(page)

        def _handle_app(
            self,
            stem: str,
            fields: dict[str, str],
            files: dict[str, bytes] | None = None,
        ) -> None:
            try:
                require_app_stem(stem)
            except ValueError:
                self.send_error(400, "invalid app name")
                return
            if stem not in allowed:
                self.send_error(404, "unknown app")
                return
            try:
                page = registry.render(
                    stem, fields, files=files or {}, theme=self._current_theme()
                )
            except Exception as e:
                self.send_error(500, f"render error: {e}")
                return
            self._send_html(page)

        def _app_stem_from_path(self, path: str) -> str | None:
            if not path.startswith("/app/"):
                return None
            parts = path[len("/app/") :].strip("/").split("/")
            if not parts or parts[0] == "img" or parts[0] == "":
                return None
            if len(parts) >= 2 and parts[1] == "img":
                return None
            return parts[0] or None

        def _app_image_route(self, path: str) -> tuple[str, str] | None:
            if not path.startswith("/app/"):
                return None
            parts = path[len("/app/") :].strip("/").split("/")
            if len(parts) == 3 and parts[1] == "img" and parts[2]:
                return parts[0], parts[2]
            return None

        def _handle_app_image(self, stem: str, token: str) -> None:
            from shan.img_cache import preview_cache

            token = unquote(token)
            try:
                require_app_stem(stem)
            except ValueError:
                self.send_error(400, "invalid app name")
                return
            if stem not in allowed:
                self.send_error(404, "unknown app")
                return
            item = preview_cache().get(token)
            if not item:
                self.send_error(404, "image not found or expired")
                return
            data, mime = item
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            try:
                self.end_headers()
                self.wfile.write(data)
            except _CLIENT_DISCONNECT_ERRORS:
                pass

        def translate_path(self, path: str) -> str:
            path = path.split("?", 1)[0]
            path = path.split("#", 1)[0]
            path = unquote(path)
            parts = [p for p in path.split("/") if p and p != "."]
            if ".." in parts:
                return str(root_resolved / ".blocked")
            candidate = (root_resolved.joinpath(*parts) if parts else root_resolved).resolve()
            try:
                candidate.relative_to(root_resolved)
            except ValueError:
                return str(root_resolved / ".blocked")
            return str(candidate)

        def log_message(self, fmt: str, *args) -> None:
            if args and len(args) >= 2 and str(args[1]) in ("200", "304", "302", "404"):
                return
            super().log_message(fmt, *args)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/theme/set", "/theme/toggle"):
                self._handle_theme(parsed)
                return
            if parsed.path in ("/gallery.html", "/gallery"):
                self._handle_gallery()
                return
            if parsed.path in ("", "/"):
                qs = parse_qs(parsed.query)
                if "app" in qs:
                    try:
                        app = require_app_stem(qs["app"][0])
                    except ValueError:
                        self.send_error(400, "invalid app parameter")
                        return
                    self.send_response(302)
                    self.send_header("Location", f"/app/{app}")
                    self.end_headers()
                    return
                self.send_response(302)
                self.send_header("Location", "/gallery.html")
                self.end_headers()
                return
            img_route = self._app_image_route(parsed.path)
            if img_route:
                self._handle_app_image(*img_route)
                return
            stem = self._app_stem_from_path(parsed.path)
            if stem:
                self._handle_app(stem, {})
                return
            return super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            stem = self._app_stem_from_path(parsed.path)
            if stem:
                try:
                    fields, files = _parse_form_body(self)
                except ValueError as e:
                    self.send_error(413, str(e))
                    return
                self._handle_app(stem, fields, files)
                return
            self.send_error(404, "not found")

    return Handler


def _make_redirect_handler(https_port: int, csp: str) -> type[http.server.BaseHTTPRequestHandler]:
    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            pass

        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except _CLIENT_DISCONNECT_ERRORS:
                pass

        def _redirect(self) -> None:
            path = self.path or "/"
            loc = f"https://{_HOST}:{https_port}{path}"
            self.send_response(302, "Found")
            self.send_header("Location", loc)
            _security_headers(self, csp=csp, hsts=False)
            try:
                self.end_headers()
            except _CLIENT_DISCONNECT_ERRORS:
                pass

        def do_GET(self) -> None:
            self._redirect()

        def do_HEAD(self) -> None:
            self._redirect()

    return RedirectHandler


def serve(
    shan_file: Path | None = None,
    port: int = 8765,
    open_browser: bool = True,
    gallery: bool = False,
    *,
    https: bool = True,
    trust_cert: bool = True,
) -> None:
    from shan.web_ssr import WebAppRegistry

    root = project_root(shan_file or Path.cwd())
    web_root = root / "examples" / "web"
    examples = root / "examples"
    registry = WebAppRegistry(examples)
    n = len(registry.stems())

    if gallery or shan_file is None:
        start_path = "/gallery.html"
    else:
        stem = shan_file.stem
        try:
            require_app_stem(stem)
        except ValueError as e:
            raise SystemExit(f"error: {e}") from e
        start_path = f"/app/{stem}"

    os.chdir(web_root)

    listen_port = port
    scheme = "https" if https else "http"
    start_url = f"{scheme}://{_HOST}:{listen_port}{start_path}"
    csp = _DEV_CSP_HTTPS if https else _CSP_NO_JS

    Handler = _make_handler(listen_port, web_root, registry, csp=csp, hsts=https)
    try:
        httpd = _ShanServer((_HOST, listen_port), Handler)
    except OSError as e:
        if e.errno == 48:
            raise SystemExit(
                f"error: port {listen_port} is in use.\n"
                f"  kill it: kill -9 $(lsof -tiTCP:{listen_port})\n"
                f"  or use: python3 -m shan serve -p {port + 1}"
            ) from e
        raise

    http_redirect_port: int | None = None
    if https:
        from shan.tls_dev import cert_dir, ensure_localhost_cert, ssl_context, trust_localhost_cert

        cert_store = cert_dir(web_root)
        try:
            cert_pem, key_pem = ensure_localhost_cert(cert_store)
            if trust_cert:
                ok, msg = trust_localhost_cert(cert_pem)
                if ok:
                    print(f"  TLS cert: {msg}")
                else:
                    print(f"  TLS cert: {cert_pem}")
                    print(f"  trust: {msg}")
                    print("  (approve the keychain prompt on macOS, or accept the browser warning once)")
            ctx = ssl_context(cert_pem, key_pem)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        except Exception as e:
            raise SystemExit(
                f"error: HTTPS setup failed ({e}).\n"
                "  Debug with plain HTTP: python3 -m shan serve --http-only"
            ) from e
        http_redirect_port = port - 1 if port > 1024 else port + 1
        try:
            redirect = _ShanServer(
                (_HOST, http_redirect_port),
                _make_redirect_handler(listen_port, csp),
            )
            threading.Thread(
                target=redirect.serve_forever,
                name="shan-http-redirect",
                daemon=True,
            ).start()
        except OSError:
            http_redirect_port = None

    print(f"Shàn web ({scheme.upper()}, no JavaScript, {_HOST}): {start_url}")
    print(f"  {n} apps (server-rendered from .shan)")
    print("  >>> open: " + start_url)
    if https:
        if http_redirect_port is not None:
            print(f"  HTTP → HTTPS redirect: http://{_HOST}:{http_redirect_port}/")
    if shan_file and not gallery:
        print(f"  source: {shan_file}")
    print(f"  root: {web_root}")
    print("  Ctrl+C to stop")

    if open_browser:
        try:
            if https:
                if not _wait_tls_listening(listen_port, timeout=8.0):
                    raise OSError("HTTPS port did not become ready")
                open_browser_https(start_url)
            else:
                webbrowser.open(start_url, new=2)
        except OSError as e:
            print(f"\n  warning: could not open browser ({e}):\n  {start_url}\n", file=sys.stderr)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def print_app_list(root: Path) -> None:
    apps = list_web_apps(root)
    print("Shàn web examples (shan serve <name>):")
    for p in apps:
        print(f"  {p.stem:16}  examples/{p.name}")

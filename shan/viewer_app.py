"""
Shàn Viewer — display HTML + CSS without JavaScript.

Uses tkinterweb (Tkhtml3) when installed; otherwise a local HTTP server
and your system browser with <script> tags stripped from HTML responses.
"""
from __future__ import annotations

import http.server
import os
import re
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Callable

_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ONEVENT_RE = re.compile(r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)


def sample_dir() -> str:
    return str(_samples_path())


def _samples_path() -> Path:
    return Path(__file__).resolve().parent.parent / "viewer" / "samples"


def launch(start: str | None = None) -> None:
    """Open the viewer on a directory or .html file."""
    path = Path(start).resolve() if start else _samples_path()
    if path.is_file():
        root_dir = path.parent
        initial = path
    else:
        root_dir = path
        initial = _find_index(root_dir)

    if not root_dir.is_dir():
        raise FileNotFoundError(f"not a directory: {root_dir}")

    try:
        _launch_tkinterweb(root_dir, initial)
    except ImportError:
        _launch_browser_shell(root_dir, initial)


def _find_index(directory: Path) -> Path | None:
    for name in ("index.html", "index.htm", "home.html"):
        p = directory / name
        if p.is_file():
            return p
    htmls = sorted(directory.glob("*.html")) + sorted(directory.glob("*.htm"))
    return htmls[0] if htmls else None


def _strip_js(html: str) -> str:
    html = _SCRIPT_RE.sub("", html)
    html = _ONEVENT_RE.sub("", html)
    return html


class _NoScriptHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self.path.endswith((".html", ".htm")):
            data = source.read()
            if isinstance(data, bytes):
                text = data.decode("utf-8", errors="replace")
            else:
                text = data
            text = _strip_js(text)
            outputfile.write(text.encode("utf-8"))
            return
        return super().copyfile(source, outputfile)

    def log_message(self, fmt: str, *args) -> None:
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(root_dir: Path) -> tuple[str, threading.Thread]:
    port = _free_port()
    handler = lambda *a, **k: _NoScriptHandler(*a, directory=str(root_dir), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}/", thread


def _launch_browser_shell(root_dir: Path, initial: Path | None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    base_url, _server = _start_server(root_dir)
    rel = initial.name if initial and initial.parent.samefile(root_dir) else "index.html"
    if not (root_dir / rel).exists():
        rel = initial.name if initial else ""
    current_url = f"{base_url}{rel}" if rel else base_url

    root = tk.Tk()
    root.title("Shàn Viewer — HTML & CSS only (no JavaScript)")
    root.minsize(520, 420)
    root.configure(bg="#1a1a2e")

    status = tk.StringVar(value=current_url)
    tk.Label(
        root,
        text="Rendered in your browser · <script> removed · JS disabled",
        fg="#a0a0b0",
        bg="#1a1a2e",
        font=("Helvetica", 11),
    ).pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(root, textvariable=status, fg="#6eb5ff", bg="#1a1a2e", font=("Menlo", 10)).pack(
        fill="x", padx=12
    )

    def open_url(url: str) -> None:
        status.set(url)
        webbrowser.open(url)

    def refresh() -> None:
        open_url(status.get())

    def pick_file() -> None:
        p = filedialog.askopenfilename(
            initialdir=str(root_dir),
            title="Open HTML",
            filetypes=[("HTML", "*.html *.htm"), ("All", "*.*")],
        )
        if p:
            rel_path = Path(p).relative_to(root_dir)
            open_url(f"{base_url}{rel_path.as_posix()}")

    def pick_folder() -> None:
        p = filedialog.askdirectory(initialdir=str(root_dir))
        if p:
            messagebox.showinfo("Shàn Viewer", "Restart viewer to change root folder.")

    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=12, pady=10)
    ttk.Button(bar, text="Open in browser", command=refresh).pack(side="left", padx=4)
    ttk.Button(bar, text="Open HTML file…", command=pick_file).pack(side="left", padx=4)
    ttk.Button(bar, text="Choose folder…", command=pick_folder).pack(side="left", padx=4)

    listing = tk.Listbox(root, font=("Menlo", 11), bg="#0f0f1a", fg="#e0e0e0", selectbackground="#3d5a80")
    listing.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    for f in sorted(root_dir.iterdir()):
        if f.suffix.lower() in (".html", ".htm", ".css"):
            listing.insert("end", f.name)

    def on_select(_evt=None) -> None:
        sel = listing.curselection()
        if not sel:
            return
        name = listing.get(sel[0])
        if name.endswith((".html", ".htm")):
            open_url(f"{base_url}{name}")

    listing.bind("<Double-Button-1>", on_select)

    hint = tk.Text(root, height=8, wrap="word", bg="#0f0f1a", fg="#c0c0c0", font=("Helvetica", 11))
    hint.pack(fill="x", padx=12, pady=(0, 12))
    hint.insert(
        "1.0",
        "Install tkinterweb for embedded preview:\n  pip install tkinterweb\n\n"
        "This mode opens pages in your default browser. "
        "HTML is served locally with <script> tags removed.",
    )
    hint.configure(state="disabled")

    open_url(current_url)
    root.mainloop()


def _launch_tkinterweb(root_dir: Path, initial: Path | None) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    from tkinterweb import HtmlFrame

    root = tk.Tk()
    root.title("Shàn Viewer — HTML & CSS only")
    root.minsize(640, 480)
    root.configure(bg="#1a1a2e")

    toolbar = ttk.Frame(root)
    toolbar.pack(fill="x", padx=8, pady=6)

    frame = HtmlFrame(root, messages_enabled=False)
    frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    # Tkhtml3 does not execute JavaScript
    if hasattr(frame, "enable_javascript"):
        frame.enable_javascript(False)

    history: list[str] = []
    index = -1

    def load_file(path: Path) -> None:
        nonlocal index
        html = _strip_js(path.read_text(encoding="utf-8"))
        base = path.parent.as_uri() + "/"
        frame.load_html(html, baseurl=base)
        history.append(str(path))
        index = len(history) - 1
        root.title(f"Shàn Viewer — {path.name}")

    def back() -> None:
        nonlocal index
        if index > 0:
            index -= 1
            load_file(Path(history[index]))

    def forward() -> None:
        nonlocal index
        if index < len(history) - 1:
            index += 1
            load_file(Path(history[index]))

    def open_dialog() -> None:
        p = filedialog.askopenfilename(
            initialdir=str(root_dir),
            filetypes=[("HTML", "*.html *.htm")],
        )
        if p:
            load_file(Path(p))

    ttk.Button(toolbar, text="← Back", command=back).pack(side="left", padx=2)
    ttk.Button(toolbar, text="Forward →", command=forward).pack(side="left", padx=2)
    ttk.Button(toolbar, text="Open…", command=open_dialog).pack(side="left", padx=2)
    ttk.Button(toolbar, text="Reload", command=lambda: load_file(Path(history[index]))).pack(
        side="left", padx=2
    )

    start = initial or _find_index(root_dir)
    if start:
        load_file(start)
    else:
        frame.load_html(
            _strip_js(
                "<html><body style='font-family:sans-serif;padding:2em'>"
                "<h1>Shàn Viewer</h1><p>No HTML files in this folder.</p></body></html>"
            ),
            baseurl=root_dir.as_uri() + "/",
        )

    root.mainloop()

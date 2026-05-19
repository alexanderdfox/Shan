"""CLI: python -m shan [run] file.shan | check | fmt | compile | repl | view | run-all"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from shan.runtime import ShanRuntime

_COMMANDS = frozenset({"run", "check", "fmt", "compile", "repl", "view", "run-all"})


def _project_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "shan" / "__main__.py").is_file():
            return d
    return start.parent


def _normalize_argv(argv: list[str]) -> list[str]:
    """Allow: python -m shan examples/foo.shan  →  python -m shan run examples/foo.shan"""
    if not argv:
        return argv
    first = argv[0]
    if first in _COMMANDS:
        return argv
    p = Path(first)
    if p.suffix == ".shan" or (p.exists() and p.suffix == ".shan"):
        return ["run", *argv]
    return argv


def cmd_run(path: Path, loose: bool, compiled: bool) -> int:
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    if compiled:
        out = path.with_suffix(".py")
        from shan.compile import compile_file

        compile_file(path, out)
        env = {**os.environ, "PYTHONPATH": str(_project_root(path))}
        r = subprocess.run([sys.executable, str(out.resolve())], env=env)
        return r.returncode
    rt = ShanRuntime(strict_rooms=not loose)
    rt.run_file(path)
    return 0


def cmd_check(path: Path, json_out: bool) -> int:
    from shan.checker import check_file, diagnostics_json, format_diagnostics

    result = check_file(path)
    if json_out:
        print(diagnostics_json(result))
    else:
        print(format_diagnostics(result, path))
    return 0 if result.ok else 1


def cmd_fmt(path: Path, write: bool) -> int:
    from shan.fmt import format_file, format_file_inplace

    if write:
        format_file_inplace(path)
        print(f"formatted: {path}")
    else:
        print(format_file(path), end="")
    return 0


def cmd_compile(path: Path, out: Path | None, run: bool, target: str) -> int:
    if target == "web":
        from shan.compile_web import compile_file, copy_runtime

        out_path = out or path.parent / "web" / "dist" / "apps" / f"{path.stem}.js"
        compile_file(path, out_path)
        copy_runtime(out_path.parent.parent)  # dist/shan-web.js
        print(f"compiled (web): {out_path}")
        print(f"runtime: {out_path.parent / 'shan-web.js'}")
        if run:
            from shan.serve import prepare_web_dist

            web_root = prepare_web_dist(path.resolve(), _project_root(path))
            print(f"open: {web_root}/index.html via `shan serve {path}`")
        return 0

    from shan.compile import compile_file as compile_py

    out_path = compile_py(path, out)
    print(f"compiled: {out_path}")
    if run:
        env = {**os.environ, "PYTHONPATH": str(_project_root(path))}
        r = subprocess.run([sys.executable, str(out_path.resolve())], env=env)
        return r.returncode
    return 0


def cmd_serve(
    path: Path | None,
    port: int,
    no_browser: bool,
    gallery: bool,
    list_apps: bool,
    http_only: bool,
    no_trust_cert: bool,
) -> int:
    from shan.serve import list_web_apps, print_app_list, project_root, serve

    root = project_root(Path(__file__))
    if list_apps:
        print_app_list(root)
        return 0
    resolved: Path | None = None
    if path and not gallery:
        p = path
        if not p.suffix:
            p = root / "examples" / f"{p.name}.shan"
            if not p.is_file() and not str(path).endswith(".shan"):
                p = root / "examples" / f"{path.name}-web.shan"
        if not p.is_file():
            print(f"error: not found: {path}", file=sys.stderr)
            return 1
        resolved = p.resolve()
    serve(
        resolved,
        port=port,
        open_browser=not no_browser,
        gallery=gallery or resolved is None,
        https=not http_only,
        trust_cert=not no_trust_cert,
    )
    return 0


def cmd_run_all(loose: bool, compiled: bool, compile_only: bool) -> int:
    root = _project_root(Path(__file__))
    examples = sorted(
        p for p in (root / "examples").glob("*.shan")
        if not p.name.endswith("-web.shan")
    )
    if not examples:
        print("no .shan files in examples/", file=sys.stderr)
        return 1
    failed = 0
    for path in examples:
        print(f"\n=== {path.name} ===")
        try:
            if compile_only:
                from shan.compile import compile_file

                out = compile_file(path, path.with_suffix(".py"))
                print(f"compiled: {out}")
            else:
                code = cmd_run(path, loose, compiled)
                if code != 0:
                    failed += 1
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            failed += 1
    print(f"\n{'OK' if failed == 0 else f'{failed} failed'} — {len(examples)} programs")
    return 1 if failed else 0


def cmd_repl() -> int:
    print("Shàn REPL (paste <page>...</page>, blank line to run, Ctrl-D exit)")
    buf: list[str] = []
    while True:
        try:
            line = input("shan> " if not buf else "....> ")
        except EOFError:
            print()
            break
        if line.strip() == "" and buf:
            src = "\n".join(buf)
            buf.clear()
            try:
                from shan.checker import ShanChecker, format_diagnostics

                cr = ShanChecker().check_string(src)
                if not cr.ok:
                    print(format_diagnostics(cr))
                    continue
                ShanRuntime(strict_rooms=False).run_string(src)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
            continue
        buf.append(line)
    return 0


def cmd_view(path: Path | None) -> int:
    viewer_shan = _project_root(Path(__file__)) / "viewer" / "viewer.shan"
    if not viewer_shan.is_file():
        print("viewer/viewer.shan not found", file=sys.stderr)
        return 1
    old_argv = sys.argv[:]
    sys.argv = [str(viewer_shan)] + ([str(path.resolve())] if path else [])
    try:
        ShanRuntime(strict_rooms=True).run_file(viewer_shan)
    finally:
        sys.argv = old_argv
    return 0


def main(argv: list[str] | None = None) -> int:
    from shan.venv import ensure_venv

    ensure_venv()
    argv = _normalize_argv(list(argv if argv is not None else sys.argv[1:]))
    p = argparse.ArgumentParser(
        prog="shan",
        description="Shàn language toolkit",
        epilog="Shortcut: shan program.shan  →  shan run program.shan",
    )
    sub = p.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Execute a .shan file")
    run_p.add_argument("file", type=Path)
    run_p.add_argument("--loose", action="store_true", help="Disable strict room checks")
    run_p.add_argument("--compiled", action="store_true", help="Compile to Python first (faster)")

    chk_p = sub.add_parser("check", help="Static analysis (strict)")
    chk_p.add_argument("file", type=Path)
    chk_p.add_argument("--json", action="store_true", dest="json_out", help="JSON diagnostics")

    fmt_p = sub.add_parser("fmt", help="Format .shan file")
    fmt_p.add_argument("file", type=Path)
    fmt_p.add_argument("-w", "--write", action="store_true", help="Write in place")

    cmp_p = sub.add_parser("compile", help="Compile .shan to Python or JavaScript")
    cmp_p.add_argument("file", type=Path)
    cmp_p.add_argument("-o", "--output", type=Path, default=None)
    cmp_p.add_argument("--run", action="store_true", help="Run compiled output")
    cmp_p.add_argument(
        "--target",
        choices=("python", "web"),
        default="python",
        help="python (default) or web (browser JS)",
    )

    srv_p = sub.add_parser("serve", help="Web dev server (gallery or one app)")
    srv_p.add_argument(
        "file",
        type=Path,
        nargs="?",
        default=None,
        help="App name or path (e.g. hello-web or examples/hello-web.shan)",
    )
    srv_p.add_argument(
        "-p",
        "--port",
        type=int,
        default=8765,
        help="Server port (default 8765)",
    )
    srv_p.add_argument("--no-browser", action="store_true")
    srv_p.add_argument(
        "--gallery",
        action="store_true",
        help="Open example picker (default when file omitted)",
    )
    srv_p.add_argument("--list", action="store_true", help="List serve examples")
    srv_p.add_argument(
        "--http-only",
        action="store_true",
        help="Plain HTTP only (default is HTTPS with a local dev certificate)",
    )
    srv_p.add_argument(
        "--no-trust-cert",
        action="store_true",
        help="Do not try to add the dev certificate to the OS trust store",
    )

    sub.add_parser("repl", help="Interactive REPL")

    view_p = sub.add_parser("view", help="HTML+CSS viewer (no JavaScript)")
    view_p.add_argument("path", type=Path, nargs="?", default=None)

    all_p = sub.add_parser("run-all", help="Run every examples/*.shan program")
    all_p.add_argument("--loose", action="store_true")
    all_p.add_argument("--compiled", action="store_true")
    all_p.add_argument("--compile-only", action="store_true", help="Only compile to .py")

    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 0

    if args.cmd == "run":
        return cmd_run(args.file, args.loose, args.compiled)
    if args.cmd == "check":
        return cmd_check(args.file, args.json_out)
    if args.cmd == "fmt":
        return cmd_fmt(args.file, args.write)
    if args.cmd == "compile":
        return cmd_compile(args.file, args.output, args.run, args.target)
    if args.cmd == "serve":
        return cmd_serve(
            args.file,
            args.port,
            args.no_browser,
            args.gallery,
            args.list,
            args.http_only,
            args.no_trust_cert,
        )
    if args.cmd == "repl":
        return cmd_repl()
    if args.cmd == "view":
        return cmd_view(args.path)
    if args.cmd == "run-all":
        return cmd_run_all(args.loose, args.compiled, args.compile_only)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

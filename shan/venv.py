"""Run Shàn inside the project virtual environment (.venv)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def find_project_root(start: Path) -> Path | None:
    """Peacock source tree (pyproject.toml + shan/), or None if installed-only."""
    for d in [start.resolve(), *start.resolve().parents]:
        if (d / "shan" / "__main__.py").is_file() and (d / "pyproject.toml").is_file():
            return d
    return None


def venv_python(root: Path) -> Path | None:
    if sys.platform == "win32":
        candidate = root / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = root / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def in_virtualenv() -> bool:
    if os.environ.get("VIRTUAL_ENV"):
        return True
    return sys.prefix != sys.base_prefix


def _reexec_argv(venv_py: Path) -> list[str]:
    if len(sys.argv) > 0 and (
        sys.argv[0].endswith("__main__.py") or sys.argv[0] == "-m" or "shan" in Path(sys.argv[0]).name
    ):
        return [str(venv_py), "-m", "shan", *sys.argv[1:]]
    return [str(venv_py), *sys.argv]


def _create_venv(root: Path) -> Path:
    dest = root / ".venv"
    print(f"Creating virtual environment: {dest}", file=sys.stderr)
    subprocess.run([sys.executable, "-m", "venv", str(dest)], check=True)
    vpy = venv_python(root)
    if vpy is None:
        raise RuntimeError("venv was created but python executable is missing")
    subprocess.run([str(vpy), "-m", "pip", "install", "-U", "pip"], check=True)
    subprocess.run(
        [str(vpy), "-m", "pip", "install", "-e", f"{root}[viewer,dev]"],
        check=True,
    )
    return vpy


def ensure_venv(*, auto_create: bool = True) -> None:
    """
    Re-exec into .venv/bin/python when the project venv exists (or create it).
  Set SHAN_SKIP_VENV=1 to use the current interpreter.
    """
    if os.environ.get("SHAN_SKIP_VENV") == "1":
        return

    root = find_project_root(Path(__file__).resolve())
    if root is None:
        return

    vpy = venv_python(root)

    if vpy is None and auto_create and os.environ.get("SHAN_NO_AUTO_VENV") != "1":
        try:
            vpy = _create_venv(root)
            print("Installed shan in .venv (editable).", file=sys.stderr)
        except (subprocess.CalledProcessError, OSError) as e:
            _exit_with_venv_help(root, reason=str(e))
            return

    if vpy is None:
        _exit_with_venv_help(root, reason="no .venv found")
        return

    if in_virtualenv():
        # Prefer the project venv when multiple venvs are nested.
        try:
            if Path(sys.executable).resolve() == vpy.resolve():
                return
        except OSError:
            pass

    os.environ["SHAN_SKIP_VENV"] = "1"
    argv = _reexec_argv(vpy)
    os.execv(argv[0], argv)


def _exit_with_venv_help(root: Path, *, reason: str) -> None:
    script = root / "scripts" / "bootstrap-venv.sh"
    print("error: Shàn must run inside the project virtual environment.", file=sys.stderr)
    print(f"  ({reason})", file=sys.stderr)
    print(file=sys.stderr)
    if script.is_file():
        print(f"  {script}", file=sys.stderr)
    else:
        print(f"  cd {root} && python3 -m venv .venv && .venv/bin/pip install -e .", file=sys.stderr)
    raise SystemExit(1)

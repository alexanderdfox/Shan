# Shàn (扇)

A **general-purpose** programming language that combines:

1. **Quantum-fan security** — half-truth (`½`), contracting secrets (span decay), audited `<open room="...">` gates  
2. **HTML-simple syntax** — tags and attributes anyone can read  
3. **Python-level power** — functions, loops, lists, dicts, comprehensions, classes, `import`, exceptions, REPL  

## Shàn in the browser (Phase 1 — JS replacement)

```bash
python3 -m shan serve              # HTTPS gallery (port 8765; 8764 redirects)
python3 -m shan serve hello-web    # one app
python3 -m shan serve --list       # names
python3 -m shan serve --http-only  # plain HTTP (debugging)

python3 -m shan compile examples/hello-web.shan --target web
```

See [spec/WEB.md](spec/WEB.md).

## HTML+CSS Viewer (no JavaScript)

```bash
python3 -m shan view                    # opens viewer/samples/
python3 -m shan view /path/to/your/site
pip install tkinterweb                  # optional: embedded preview
```

See [viewer/README.md](viewer/README.md).

## Quick start

```bash
cd Peacock

# One-time: create .venv and install Shàn (or auto-created on first shan command)
./scripts/bootstrap-venv.sh

# All commands use .venv automatically (re-exec if you call system python3)
.venv/bin/python -m shan serve
./bin/shan serve                # wrapper script

# Shàn programs (shortcut — no "run" needed)
python3 -m shan examples/data.shan
python3 -m shan run-all --loose

# Or explicitly
python3 -m shan run examples/hello.shan --loose
python3 -m shan compile examples/data.shan --run

# HTML+CSS demos (not .shan files)
python3 -m shan view
```

## Toolkit

| Command | Purpose |
|---------|---------|
| `shan run FILE` | Execute (interpreted) |
| `shan run FILE --compiled` | Compile to `.py` then run (faster) |
| `shan check FILE` | Strict static analysis |
| `shan check FILE --json` | Diagnostics for VS Code |
| `shan fmt FILE` | Print formatted source |
| `shan fmt -w FILE` | Format in place |
| `shan compile FILE` | Emit Python (`FILE.py`) |
| `shan compile FILE --run` | Compile and execute |
| `shan view [PATH]` | HTML+CSS viewer (no JS) |
| `shan program.shan` | Same as `shan run program.shan` |
| `shan run-all` | Run all `examples/*.shan` |
| `shan run-all --compile-only` | Compile all examples to `.py` |
| `shan compile FILE --target web` | Compile to browser JS |
| `shan serve FILE` | Web dev server (compile + open) |

## VS Code extension

```bash
# Install locally (Cursor / VS Code)
code --install-extension ./vscode-shan
# or: cursor --install-extension ./vscode-shan
```

Features:

- Syntax highlighting for `.shan`
- **Format Document** → `shan fmt`
- **Diagnostics on save** → `shan check --json`
- Commands: *Shàn: Run File*, *Check*, *Compile*

Set `shan.projectRoot` to your Peacock folder if auto-detect fails.

## Hello world

```html
<page title="Hello">
  <fan ribs="4">
    <rib id="default">
      <show expr="'Hello, Shàn'"/>
    </rib>
  </fan>
</page>
```

## Python vs Shàn

| Python | Shàn |
|--------|------|
| `print(x)` | `<show expr="x"/>` |
| `x = 1 + 2` | `<set name="x" expr="1 + 2"/>` |
| `def f(n):` | `<fn name="f" args="n">` |
| `for i in range(10):` | `<each var="i" in="range(10)">` |
| `import json` | `<import module="json"/>` |
| `if/else` | `<when test="...">` / `<otherwise>` |

Expressions in `expr="..."` use **Python syntax** (`range`, comprehensions, `**`, etc.).

## Security rooms

Sensitive operations require wrapping in `<open>`:

```html
<open room="files" why="load-config">
  <file-read path="'config.txt'" result="cfg"/>
</open>

<open room="keys" why="sign">
  <secret name="key" uses="3">...</secret>
  <observe name="key" why="sign-request"/>
</open>
```

The checker enforces rooms, `why` on `<open>`/`<observe>`, no `<show>` of secrets, and no half-vars in `<when test>`.

## Compile to Python

`shan compile` emits readable Python using `shan.compiled_support` for span/room/audit semantics. Run from project root so imports resolve:

```bash
PYTHONPATH=. python3 examples/hello.py
```

## Spec

Full language definition: [spec/LANGUAGE.md](spec/LANGUAGE.md)

## Project layout

```
Peacock/
  spec/LANGUAGE.md
  shan/                   # interpreter, checker, fmt, compiler
  examples/*.shan
  vscode-shan/            # VS Code / Cursor extension
  tests/
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

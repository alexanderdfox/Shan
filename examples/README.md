# Shàn example programs

Run any `.shan` file here:

```bash
python3 -m shan hello.shan
python3 -m shan run hello.shan --loose
```

| File | What it does |
|------|----------------|
| `hello.shan` | Hello world + arithmetic |
| `fibonacci.shan` | Recursive functions, loops |
| `data.shan` | Lists, dicts, JSON, math |
| `half_logic.shan` | Half-value (½) and `when-half` |
| `secrets.shan` | Secrets, span, `open room="keys"` |
| `fan_cipher.shan` | **QFan cipher** — ½ ribs, span-contracting encryption |
| `hello-web.shan` | **Browser** — `shan serve hello-web` |
| `greet-web.shan` | Text input greeting |
| `lights-web.shan` | Toggle lamp |
| `score-web.shan` | Scoreboard |
| `todo-web.shan` | Three todos |
| `calc-web.shan` | Calculator pad |

Web gallery: `python3 -m shan serve` → [web/README.md](web/README.md)

Run all:

```bash
python3 -m shan run-all --loose
```

Compile to Python (creates matching `.py` files):

```bash
python3 -m shan run-all --compile-only
PYTHONPATH=. python3 hello.py
```

**HTML viewer** uses `viewer/samples/` — not these `.shan` files:

```bash
python3 -m shan view
```

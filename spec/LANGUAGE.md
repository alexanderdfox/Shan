# Shàn (扇) — Complete Language Specification

Shàn combines three layers:

1. **Fan core** — quantum-inspired values (½, span decay, collapse/audit), rib isolation, eight security rooms.
2. **HTML surface** — tags, attributes, nesting; readable without prior PL experience.
3. **Python parity** — general-purpose scripting: numbers, strings, lists, dicts, functions, modules, loops, exceptions, file I/O, JSON, math, and a REPL.

---

## 1. File format

- Extension: `.shan`
- Encoding: UTF-8
- Root element: exactly one `<page>` per file
- Comments: `<!-- like HTML -->`
- Void elements: `<half />`, `<deny />`, `<break />`, `<continue />`

```html
<page title="MyApp">
  <fan name="main" ribs="4">
    <rib id="default">
      <!-- program here -->
    </rib>
  </fan>
</page>
```

---

## 2. Fan value model (runtime semantics)

### 2.1 Qit (quantum-inspired unit)

Every value carries optional **fan metadata**:

| Concept | Runtime | Author sees |
|---------|---------|-------------|
| Definite true | `Yes` | `<yes>` or expression |
| Definite false | `No` | `<no>` |
| Half (0 = ½) | `Half` | `<half name="x" />` |
| Contracting 1 | `Span(value, remaining)` | `<secret uses="N">` + `<observe>` |
| Superposition | `FanValue(ribs)` | `<fan ribs="N">` (structure) |

**Span decay (“1 gets shorter”):** each `<observe name="k" why="..."/>` on a secret multiplies `remaining` by λ (default 0.9) and decrements `uses`. At `uses=0` or `remaining < ε`, access fails closed.

**Half logic:** `if` on a `Half` is a compile-time error in strict mode; use `<when-half>`.

### 2.2 Three-valued comparisons

| `a \ b` | Half | Yes | No |
|---------|------|-----|-----|
| Half | Half | Half | Half |
| Yes | Half | Yes | No |
| No | Half | No | No |

---

## 3. Security rooms (Bagua → plain names)

| Room attribute | Domain |
|----------------|--------|
| `keys` | Cryptography, secrets |
| `files` | Filesystem |
| `net` | Network |
| `proc` | Processes |
| `env` | Environment variables |
| `time` | Clocks, timers |
| `rand` | Random bytes |
| `sys` | Host introspection (restricted) |

**Rule:** tags that touch a domain must appear inside `<open room="..." why="...">...</open>`.

Audit log (append-only): `{time, room, why, tag, rib, span_before, span_after}`.

---

## 4. HTML-simple tags (authoring)

### 4.1 Structure

| Tag | Purpose |
|-----|---------|
| `<page>` | Program entry |
| `<fan>` | App shell; `ribs` (default 4) |
| `<rib id="...">` | Isolated scope / namespace |
| `<block>` | Group statements |

### 4.2 Data & variables (Python-like)

| Tag | Purpose |
|-----|---------|
| `<value name="x">42</value>` | Bind literal or text |
| `<set name="x" expr="a + b"/>` | Assign from expression |
| `<list name="xs" expr="[1,2,3]"/>` | List literal via expr |
| `<dict name="d" expr="{'a': 1}"/>` | Dict literal |
| `<del name="x"/>` | Delete binding |

Expressions use Python syntax in `expr="..."` (restricted AST: no imports, no attribute stores on dunder).

### 4.3 Control flow

| Tag | Purpose |
|-----|---------|
| `<when test="expr">` | If |
| `<otherwise>` | Else (sibling of when) |
| `<each var="x" in="expr">` | For loop |
| `<while test="expr">` | While loop |
| `<break/>` | Break inner loop |
| `<continue/>` | Continue loop |
| `<return expr="..."/>` | Return from function |

### 4.4 Functions & modules (Python parity)

| Tag | Purpose |
|-----|---------|
| `<fn name="f" args="a,b">` | Define function |
| `<call name="f" args="1,2" result="r"/>` | Call; optional `result` |
| `<import module="json"/>` | Import Python stdlib module into rib |
| `<import shan="utils.shan"/>` | Load another `.shan` rib |
| `<class name="C">` | Define class (see §6) |
| `<try>` / `<except test="ValueError">` / `<finally>` | Exceptions |

### 4.5 I/O & builtins

| Tag | Purpose |
|-----|---------|
| `<show expr="x"/>` or `<text>` | Print (public only) |
| `<ask name="x" prompt="?"/>` | `input()` |
| `<assert test="expr" msg="..."/>` | Assertion |

### 4.6 Security surface

| Tag | Purpose |
|-----|---------|
| `<open room="keys" why="login">` | Capability scope |
| `<secret name="k" uses="3">...</secret>` | Secret with span |
| `<observe name="k" why="reason"/>` | Collapse/read secret |
| `<when-half name="h">` + `<case value="yes|no|half">` | Match three-valued |
| `<deny/>` | Fail closed |
| `<seal expr="data" key="k" result="c"/>` | Encrypt (room keys) |
| `<unseal expr="c" key="k" result="p"/>` | Decrypt |

### 4.7 Void & raw

| Tag | Purpose |
|-----|---------|
| `<half name="x"/>` | Bind Half |
| `<yes name="x"/>` / `<no name="x"/>` | Bind definite |

---

## 5. Python parity matrix

| Python | Shàn |
|--------|------|
| `x = 1` | `<set name="x" expr="1"/>` |
| `print(x)` | `<show expr="x"/>` |
| `if/elif/else` | `<when>` / `<otherwise>` |
| `for x in xs` | `<each var="x" in="xs">` |
| `while` | `<while test="...">` |
| `def f(a,b):` | `<fn name="f" args="a,b">` |
| `return x` | `<return expr="x"/>` |
| `import json` | `<import module="json"/>` |
| `try/except` | `<try>` / `<except>` |
| `class C:` | `<class name="C">` |
| `len`, `range`, `str`… | Builtins in expressions |
| `open(path)` | `<open room="files" why="read"><file-read .../></open>` or `py:open` via import os |
| List comprehensions | `expr="[x*2 for x in xs]"` |
| Dict/list | `expr` attribute |
| REPL | `python -m shan` or `shan run` |

**Interop:** `<import module="numpy"/>` (if installed) — full Python ecosystem available inside ribs with room guards on dangerous ops.

---

## 6. Classes

```html
<class name="Point" bases="">
  <fn name="__init__" args="self,x,y">
    <set name="self.x" expr="x"/>
    <set name="self.y" expr="y"/>
  </fn>
  <fn name="dist" args="self" result="d">
    <set name="d" expr="(self.x**2 + self.y**2)**0.5"/>
    <return expr="d"/>
  </fn>
</class>
<call name="Point" args="0,3" result="p"/>
<call name="p.dist" result="d"/>
```

Desugars to Python-like objects in the reference runtime.

---

## 7. Rib isolation

- Each `<rib>` has its own variable dict and audit prefix.
- `<fan ribs="N">` pre-allocates N rib namespaces; cross-rib calls require `<call rib="other" .../>` (explicit).
- Default: single implicit rib `default` if omitted.

---

## 8. Standard library (built-in modules)

| Module | Tags / functions |
|--------|------------------|
| `shan.math` | `sin, cos, sqrt, pi, ...` in expr |
| `shan.json` | `json_load(s)`, `json_dump(obj)` |
| `shan.io` | `read_file`, `write_file` (files room) |
| `shan.net` | `fetch(url)` (net room) |
| `shan.hash` | `sha256(data)` (keys room) |

---

## 9. CLI

```bash
shan run program.shan          # execute
shan check program.shan        # validate nesting & rooms
shan repl                      # interactive
shan fmt program.shan          # format (indent)
```

---

## 10. Error messages (plain language)

- `Line 12: <file-read> needs <open room="files">`
- `Line 8: cannot <show> secret 'apiKey' — use <observe> inside <open room="keys">`
- `Line 20: secret 'apiKey' fan closed (uses exhausted)`

---

## 11. Formal grammar (surface)

```
document ::= <page attrs?> fan-block </page>
fan-block ::= <fan attrs?> rib* </fan>
rib ::= <rib attrs?> stmt* </rib>
stmt ::= value | set | when | each | fn | call | open | ...
```

Expressions: Python subset embedded in `expr`, `test`, `in`, `args` attributes.

---

## 12. Version

Spec version: **1.0.0** — reference implementation in `shan/` package.

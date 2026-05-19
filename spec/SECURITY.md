# Shàn security model

Peacock implements defense in depth across desktop (`.shan` interpreter), web compile (`--target web`), and dev tooling.

## Fan rooms (desktop)

Eight **rooms** gate sensitive capabilities. In strict mode (default), tags like `<file-read>`, `<seal>`, and `<fetch>` require an enclosing `<open room="…" why="…">`.

- **Secrets** live in `<secret>` inside `room="keys"`; use `<observe why="…">`, not `<show>`, for secret values.
- **Span decay**: `<secret uses="N">` limits observations before the value is cleared.

Run with `--loose` only for local experiments.

## Expression sandbox (Python)

`expr` / `test` attributes are evaluated by a restricted AST walker (`shan/expr.py`):

- No `eval` / `exec` / imports in expressions
- Calls must be direct names (`len(x)`), not `getattr(...)(...)`
- No dunder or leading-underscore attribute access

## Web (Phase 1)

Compiled apps are **static JS modules** plus a small runtime (`shan/static/shan-web.js`):

| Layer | Protection |
|-------|------------|
| Compile | Allowlisted HTML tags; no `<script>`; no `javascript:` URLs; no inline `on*` attrs (use `on="click:handler"` → `data-on`) |
| Runtime | Markup pattern scan; `textContent` for binds; event/handler allowlists; no `eval` |
| Host | `index.html` validates `?app=` stem; CSP meta tag |
| Dev server | **HTTPS by default** on port 8765 (self-signed cert); HTTP on port 8764 redirects to HTTPS; binds **127.0.0.1** only. Use `https://127.0.0.1:8765/` (not port 8766). `--http-only` for debugging. |

**Trust model:** Treat compiled `dist/apps/*.js` as trusted (same as your `.shan` source). Do not inject third-party HTML into compile output.

## Files

`<file-read>` / `read_text()` resolve paths under the **directory of the running `.shan` file** (or cwd for `run_string`). Paths outside that tree raise `PermissionError`.

## Checking

```bash
python3 -m shan check examples/hello.shan
python3 -m shan check examples/greet-web.shan
```

Web markup issues report rules like `web-forbidden-tag`, `web-on-attr`.

## What this is not

- The dev server is **not** production-grade; do not expose it to the internet.
- Web Phase 1 does not enforce fan rooms in the browser (planned Phase 2).
- Compiled Python output inherits OS permissions when you run it.

## Reporting

For security issues in this reference implementation, review `shan/security.py` and open a private issue with reproduction steps.

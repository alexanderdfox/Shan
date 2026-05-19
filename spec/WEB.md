# Shàn Web — Browser Target (Phase 1)

Shàn in the browser replaces **hand-written application JavaScript**. Authors write `.shan`; the toolchain emits ES modules plus a tiny runtime.

## Phase 1 (implemented)

### Authoring

```html
<page title="My App" mount="#app">
  <fan ribs="4">
    <rib id="ui">
      <value name="count" expr="0"/>
      <main>
        <p>Count: <bind name="count"/></p>
        <button type="button" on="click:increment">+1</button>
      </main>
      <fn name="increment">
        <set name="count" expr="count + 1"/>
        <render/>
      </fn>
    </rib>
  </fan>
</page>
```

### Tags (web v1)

| Tag | Role |
|-----|------|
| `page mount="#app"` | Root + mount selector |
| HTML elements (`main`, `button`, `p`, …) | DOM markup |
| `<bind name="x"/>` | Text binding to `env.x` |
| `on="click:handler"` | Event → compiled handler |
| `value`, `set` | State |
| `fn`, `when`, `otherwise` | Logic |
| `render` | Refresh all `[data-bind]` nodes |

### Commands

```bash
python3 -m shan compile examples/hello-web.shan --target web
python3 -m shan serve examples/hello-web.shan
```

Output: `examples/web/dist/app.js` + `shan-web.js`

### Host page

`examples/web/index.html` loads only:

```html
<script type="module">
  import createApp from './dist/app.js';
  createApp();
</script>
```

No app logic in JavaScript — only the loader.

### Runtime (`shan/static/shan-web.js`)

- `mount({ mount, html, init, handlers })`
- `env` state object
- `api.render()` updates bindings
- `data-on="event:handler"` wiring
- No `eval`

## Phase 2+ (planned)

- `open room="net"` + `<fetch>`
- `secret` / `observe` / span in memory
- `when-half` → CSS state classes
- Modules, routes, SSR
- Optional WASM VM

See README for desktop vs web vs HTML viewer.

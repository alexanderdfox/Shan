# Shàn web serve examples

## Gallery (all apps)

```bash
python3 -m shan serve
# or
python3 -m shan serve --gallery
```

Opens https://127.0.0.1:8765/gallery.html — pick an example (HTTP on port 8764 redirects to HTTPS).

Apps are **server-rendered** from `.shan` (HTML forms + CSS). **No JavaScript** runs in the browser.

## One app

```bash
python3 -m shan serve hello-web
python3 -m shan serve greet-web
python3 -m shan serve examples/todo-web.shan
```

## List

```bash
python3 -m shan serve --list
```

Plain HTTP (debugging only): `python3 -m shan serve --http-only`

## Apps

| Name | Command | Features |
|------|---------|----------|
| `hello-web` | Counter | bind, when, buttons |
| `greet-web` | Greeting | input-bind, string concat |
| `lights-web` | Lamp | toggle, emoji bind |
| `score-web` | Scoreboard | two scores |
| `todo-web` | Todo | toggle, call |
| `calc-web` | Calculator | fn args, digit pad |

Styles: `styles/base.css` + `styles/<app>.css`

Compiled JS: `dist/apps/<app>.js`

# Shàn Viewer

Desktop viewer for **HTML and CSS only** — no JavaScript in pages or in the Shàn viewer program.

## Run

```bash
# Gallery + 12 examples (correct folder)
python3 -m shan view

# Or explicitly
python3 -m shan view ./viewer/samples
```

**Not HTML:** `examples/*.shan` are Shàn programs. Use `shan run`, not `shan view`.

```bash
python3 -m shan run examples/fibonacci.shan --loose   # correct
python3 -m shan view ./viewer/samples                 # correct for HTML
```

## HTML+CSS examples

| Page | Shows |
|------|--------|
| [index.html](samples/index.html) | Gallery hub |
| [typography.html](samples/typography.html) | Headings, lists, code |
| [grid-layout.html](samples/grid-layout.html) | CSS Grid |
| [flex-layout.html](samples/flex-layout.html) | Flexbox toolbar & hero |
| [forms.html](samples/forms.html) | Inputs, select, buttons |
| [tables.html](samples/tables.html) | Data table |
| [colors.html](samples/colors.html) | Swatches & gradients |
| [fan-rooms.html](samples/fan-rooms.html) | Eight security rooms |
| [half-value.html](samples/half-value.html) | ½ three-valued logic |
| [span-decay.html](samples/span-decay.html) | Secret span bars |
| [resume.html](samples/resume.html) | Resume layout |
| [article.html](samples/article.html) | Long-form article |
| [print.html](samples/print.html) | `@media print` |

Optional embedded preview: `pip install tkinterweb`

## Files

```
viewer/
  viewer.shan          # Shàn launcher
  samples/             # HTML + CSS examples (open this folder)
    common.css         # Shared nav & variables
    gallery.css        # Gallery grid
    *.html + *.css     # One pair per demo
```

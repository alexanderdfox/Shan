# Shàn VS Code / Cursor Extension

## Install

From the Peacock project root:

```bash
code --install-extension ./vscode-shan
# Cursor:
cursor --install-extension ./vscode-shan
```

## Features

- Syntax highlighting for `.shan`
- Format document (`shan fmt -w`)
- Diagnostics on save (`shan check --json`)
- Commands: **Shàn: Run File**, **Shàn: Check File**, **Shàn: Compile to Python**

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `shan.pythonPath` | `python3` | Python with the `shan` package |
| `shan.projectRoot` | *(auto)* | Folder containing `shan/` |
| `shan.checkOnSave` | `true` | Lint on save |
| `shan.formatOnSave` | `false` | Format on save |

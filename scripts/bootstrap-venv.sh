#!/usr/bin/env bash
# Create .venv and install Shàn (editable) for local development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Creating .venv …"
  python3 -m venv .venv
fi

PY=".venv/bin/python"
"$PY" -m pip install -U pip
"$PY" -m pip install -e ".[viewer,dev]"

echo ""
echo "Virtual environment ready."
echo "  .venv/bin/python -m shan serve"
echo "  ./bin/shan serve      # wrapper (same)"
echo ""
echo "Activate: source .venv/bin/activate"

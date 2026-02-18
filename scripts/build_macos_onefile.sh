#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ICON_PATH="$ROOT_DIR/layout-switcher-icon.icns"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Create virtualenv first: python3 -m venv .venv"
  exit 1
fi
if [[ ! -f "$ICON_PATH" ]]; then
  echo "Icon file not found: $ICON_PATH"
  exit 1
fi

rm -rf build dist/LayoutAutofix dist/LayoutAutofix.app LayoutAutofix.spec

.venv/bin/python -m pip install --upgrade pip pyinstaller
.venv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --specpath build \
  --windowed \
  --osx-bundle-identifier io.vibento.layout-autofix \
  --icon "$ICON_PATH" \
  --add-data "$ICON_PATH:." \
  --name LayoutAutofix \
  layout_autofix/macos_app.py

rm -rf "$ROOT_DIR/dist/LayoutAutofix"

echo
echo "Built macOS app bundle: $ROOT_DIR/dist/LayoutAutofix.app"

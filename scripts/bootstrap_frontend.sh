#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm not found"
  exit 1
fi

npm install

echo "[OK] frontend bootstrap completed"

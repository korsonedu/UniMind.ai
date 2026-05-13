#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "$ROOT_DIR/scripts/check_backend.sh"
bash "$ROOT_DIR/scripts/smoke_qa.sh"
bash "$ROOT_DIR/scripts/check_frontend.sh"

echo "[OK] full stack checks passed"

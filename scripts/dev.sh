#!/usr/bin/env bash
# UniMind 本地开发一键启动（macOS Terminal）
# 用法: bash scripts/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

osascript -e "
tell application \"Terminal\"
    activate
    -- Tab 1: Django
    do script \"cd '$ROOT/backend' && source .venv/bin/activate && echo '[1/3] Django runserver' && python3 manage.py runserver\"
    -- Tab 2: Celery
    do script \"cd '$ROOT/backend' && source .venv/bin/activate && echo '[2/3] Celery worker' && celery -A school_system worker -l info\"
    -- Tab 3: Frontend
    do script \"cd '$ROOT/frontend' && echo '[3/3] Frontend dev' && npm run dev\"
end tell
"

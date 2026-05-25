#!/usr/bin/env bash
# 数据库备份脚本（等保二级：数据备份与恢复）
#
# 用法：
#   bash scripts/backup_db.sh
#
# Crontab 示例（每天凌晨 3 点）：
#   0 3 * * * cd /opt/unimind && bash scripts/backup_db.sh >> /var/log/unimind-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS=30

# 从 .env 读取数据库配置
if [ -f "${PROJECT_DIR}/backend/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_DIR}/backend/.env"
    set +a
fi

DB_NAME="${DB_NAME:-unimind}"
DB_USER="${DB_USER:-unimind}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] 开始备份 ${DB_NAME}..."

PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-privileges \
    | gzip > "${BACKUP_FILE}"

FILE_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "[$(date)] 备份完成: ${BACKUP_FILE} (${FILE_SIZE})"

# 清理过期备份
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
    rm -f "${old_file}"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime +${RETENTION_DAYS} -print0)

if [ "${DELETED_COUNT}" -gt 0 ]; then
    echo "[$(date)] 已清理 ${DELETED_COUNT} 个超过 ${RETENTION_DAYS} 天的备份"
fi

echo "[$(date)] 备份流程结束"

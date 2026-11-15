#!/usr/bin/env bash
# 本机数据库、媒体、日志和账号配置备份（不代替异地副本）
#
# 用法：
#   bash scripts/backup_db.sh
#
# Crontab 示例（每天凌晨 3 点）：
#   0 3 * * * cd /opt/unimind && bash scripts/backup_db.sh >> /var/log/unimind-backup.log 2>&1

set -euo pipefail
umask 077

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
chmod 700 "${BACKUP_DIR}"
BACKUP_PARTIAL="${BACKUP_FILE}.partial"
trap 'rm -f "${BACKUP_PARTIAL}"; echo "[$(date -u +%FT%TZ)] database backup FAILED" >&2' ERR
trap 'rm -f "${BACKUP_PARTIAL}"; exit 1' INT TERM

echo "[$(date)] 开始备份 ${DB_NAME}..."

PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-privileges \
    | gzip > "${BACKUP_PARTIAL}"
gzip -t "${BACKUP_PARTIAL}"
mv "${BACKUP_PARTIAL}" "${BACKUP_FILE}"
# Standard sha256sum format supports checksum verification before restoring.
(cd "${BACKUP_DIR}" && shasum -a 256 "$(basename "${BACKUP_FILE}")" > "$(basename "${BACKUP_FILE}").sha256")


# Snapshot active logs first so tar never archives a file being appended by workers.
FILE_BACKUP="${BACKUP_DIR}/files_${TIMESTAMP}.tar.gz"
SNAPSHOT_DIR="$(mktemp -d "${BACKUP_DIR}/.snapshot.XXXXXX")"
trap 'rm -f "${BACKUP_PARTIAL}" "${FILE_BACKUP}.partial"; rm -rf "${SNAPSHOT_DIR}"; echo "[$(date -u +%FT%TZ)] backup FAILED" >&2' ERR
trap 'rm -f "${BACKUP_PARTIAL}" "${FILE_BACKUP}.partial"; rm -rf "${SNAPSHOT_DIR}"; exit 1' INT TERM
for path in "${PROJECT_DIR}/backend/.env" "${PROJECT_DIR}/backend/media" "${PROJECT_DIR}/backend/logs"; do
    test -e "$path"
done
cp -R "${PROJECT_DIR}/backend/logs" "${SNAPSHOT_DIR}/logs"
paths=("${PROJECT_DIR}/backend/.env" "${PROJECT_DIR}/backend/media" "${SNAPSHOT_DIR}/logs")
for path in "${ACCOUNT_RSA_KEY_PATH:-}" "${UNIMIND_DSH_STATE_DIR:-}"; do
    [ -n "$path" ] || continue
    test -e "$path"
    paths+=("$path")
done
tar -czf "${FILE_BACKUP}.partial" "${paths[@]}"
gzip -t "${FILE_BACKUP}.partial"
mv "${FILE_BACKUP}.partial" "${FILE_BACKUP}"
(cd "${BACKUP_DIR}" && shasum -a 256 "$(basename "${FILE_BACKUP}")" > "$(basename "${FILE_BACKUP}").sha256")
rm -rf "${SNAPSHOT_DIR}"
# Seven full local file archives bound disk use; database dumps retain thirty days.
find "${BACKUP_DIR}" -name 'files_*.tar.gz*' -mtime +7 -delete

FILE_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "[$(date)] 备份完成: ${BACKUP_FILE} (${FILE_SIZE})"

# 清理过期备份
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
    rm -f "${old_file}" "${old_file}.sha256"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime +${RETENTION_DAYS} -print0)

if [ "${DELETED_COUNT}" -gt 0 ]; then
    echo "[$(date)] 已清理 ${DELETED_COUNT} 个超过 ${RETENTION_DAYS} 天的备份"
fi

echo "[$(date)] 备份流程结束"

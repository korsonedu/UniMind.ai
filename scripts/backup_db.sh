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

# .env 提供默认值，调用方指定的数据库与 DSH 状态目录优先。
if [ -f "${PROJECT_DIR}/backend/.env" ]; then
    backup_overrides=()
    for key in DB_NAME DB_HOST DB_PORT DB_USER DB_PASSWORD UNIMIND_DSH_STATE_DIR; do
        if [[ ${!key+x} ]]; then
            backup_overrides+=("${key}=${!key}")
        fi
    done
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_DIR}/backend/.env"
    set +a
    if [ "${#backup_overrides[@]}" -gt 0 ]; then
        export "${backup_overrides[@]}"
    fi
fi

DB_NAME="${DB_NAME:-unimind}"
DB_USER="${DB_USER:-unimind}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
SNAPSHOT_DIR="$(mktemp -d "${BACKUP_DIR}/.snapshot.XXXXXX")"
SNAPSHOT_ID="${TIMESTAMP}_${SNAPSHOT_DIR##*.}"
DUMP_NAME="${DB_NAME}_${SNAPSHOT_ID}.sql.gz"
ARCHIVE_NAME="files_${SNAPSHOT_ID}.tar.gz"
BACKUP_FILE="${BACKUP_DIR}/${DUMP_NAME}"

cleanup() {
    if [ ! -e "${BACKUP_FILE}" ]; then
        rm -f "${BACKUP_FILE}.sha256" "${BACKUP_DIR}/${ARCHIVE_NAME}" "${BACKUP_DIR}/${ARCHIVE_NAME}.sha256"
    fi
    rm -rf "${SNAPSHOT_DIR}"
}
trap cleanup EXIT
trap 'echo "[$(date -u +%FT%TZ)] backup FAILED" >&2' ERR
trap 'exit 1' INT TERM

for path in "${PROJECT_DIR}/backend/.env" "${PROJECT_DIR}/backend/media" "${PROJECT_DIR}/backend/logs"; do
    test -e "$path"
done

echo "[$(date)] 开始备份 ${DB_NAME}..."

PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-privileges \
    | gzip > "${SNAPSHOT_DIR}/${DUMP_NAME}"

# Snapshot active logs first so tar never archives a file being appended by workers.
cp -R "${PROJECT_DIR}/backend/logs" "${SNAPSHOT_DIR}/logs"
paths=("${PROJECT_DIR}/backend/.env" "${PROJECT_DIR}/backend/media" "${SNAPSHOT_DIR}/logs")
for path in "${ACCOUNT_RSA_KEY_PATH:-}" "${UNIMIND_DSH_STATE_DIR:-}"; do
    [ -n "$path" ] || continue
    test -e "$path"
    paths+=("$path")
done
tar -czf "${SNAPSHOT_DIR}/${ARCHIVE_NAME}" "${paths[@]}"
(
    cd "${SNAPSHOT_DIR}"
    for file in "${DUMP_NAME}" "${ARCHIVE_NAME}"; do
        gzip -t -- "$file"
        shasum -a 256 "$file" > "${file}.sha256"
    done
)
# Restore discovers the database file. Publish it only after its paired files are ready.
mv "${SNAPSHOT_DIR}/${ARCHIVE_NAME}" "${SNAPSHOT_DIR}/${ARCHIVE_NAME}.sha256" \
    "${SNAPSHOT_DIR}/${DUMP_NAME}.sha256" "${BACKUP_DIR}/"
mv "${SNAPSHOT_DIR}/${DUMP_NAME}" "${BACKUP_FILE}"

# File archives retain seven days; database dumps retain thirty days.
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

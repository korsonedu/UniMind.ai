#!/usr/bin/env bash
# 数据库恢复脚本
#
# 用法：
#   bash scripts/restore_db.sh <backup_file.sql.gz>
#   bash scripts/restore_db.sh backups/unimind_20260602_030000.sql.gz

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
    echo "用法: $0 <backup_file.sql.gz>"
    echo ""
    echo "可用备份:"
    ls -lh "${PROJECT_DIR}/backups/"*.sql.gz 2>/dev/null || echo "  (无备份文件)"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "错误: 备份文件不存在: ${BACKUP_FILE}"
    exit 1
fi

BACKUP_SHA="$(shasum -a 256 < "${BACKUP_FILE}")"
BACKUP_SHA="${BACKUP_SHA%% *}"
if [ -f "${BACKUP_FILE}.sha256" ]; then
    EXPECTED_SHA="$(awk 'NR == 1 {print $1}' "${BACKUP_FILE}.sha256")"
    if [ "${BACKUP_SHA}" != "${EXPECTED_SHA}" ]; then
        echo "错误: 数据库备份校验和不匹配。" >&2
        exit 1
    fi
fi
gzip -t -- "${BACKUP_FILE}"

# 从 .env 读取数据库配置
if [ -f "${PROJECT_DIR}/backend/.env" ]; then
    set -a
    source "${PROJECT_DIR}/backend/.env"
    set +a
fi

DB_NAME="${DB_NAME:-unimind}"
DB_USER="${DB_USER:-unimind}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "============================================"
echo "  UniMind 数据库恢复"
echo "============================================"
echo "  数据库: ${DB_NAME}"
echo "  主机:   ${DB_HOST}:${DB_PORT}"
echo "  备份:   ${BACKUP_FILE}"
echo "============================================"
echo ""
echo "⚠️  警告: 备份通过校验并导入后，将替换当前数据库！"
read -p "确认恢复? (输入 YES 继续): " CONFIRM

if [ "${CONFIRM}" != "YES" ]; then
    echo "已取消"
    exit 0
fi

echo "[$(date)] 开始恢复..."

psql_restore() {
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
        --no-psqlrc --set=ON_ERROR_STOP=1 "$@"
}

RESTORE_WORK="$(mktemp -d)"
STAGED_DATABASE="ulr_restore_${RESTORE_WORK##*.}"
PREVIOUS_DATABASE="ulr_previous_${RESTORE_WORK##*.}"
RESTORE_STAGED=false

cleanup() {
    if [ "${RESTORE_STAGED}" = true ]; then
        psql_restore -d postgres --quiet --set="staged_database=${STAGED_DATABASE}" --file=- <<'SQL' || true
DROP DATABASE IF EXISTS :"staged_database";
SQL
    fi
    rm -f "${RESTORE_WORK}/stream" "${RESTORE_WORK}/sha256"
    rmdir "${RESTORE_WORK}"
}
trap cleanup EXIT

psql_restore -d postgres --set="staged_database=${STAGED_DATABASE}" --set="restore_owner=${DB_USER}" --file=- <<'SQL'
CREATE DATABASE :"staged_database" OWNER :"restore_owner";
SQL
RESTORE_STAGED=true

# 校验实际导入的流，并让数据和恢复凭据一起提交。
verified_restore_stream() (
    HASH_PID=''
    stop_hash() {
        if [ -n "${HASH_PID}" ]; then
            kill "${HASH_PID}" 2>/dev/null || true
            wait "${HASH_PID}" 2>/dev/null || true
        fi
    }
    trap stop_hash EXIT
    mkfifo "${RESTORE_WORK}/stream"
    shasum -a 256 < "${RESTORE_WORK}/stream" > "${RESTORE_WORK}/sha256" &
    HASH_PID=$!
    if tee "${RESTORE_WORK}/stream" < "${BACKUP_FILE}" | gzip -dc && wait "${HASH_PID}"; then
        HASH_PID=''
        if read -r RESTORED_SHA _ < "${RESTORE_WORK}/sha256" && [ "${RESTORED_SHA}" = "${BACKUP_SHA}" ]; then
            cat <<'SQL'

ALTER DATABASE :"restore_database" SET unimind.restore_sha256 TO :'restore_sha';
SQL
            exit 0
        fi
        echo "错误: 实际导入数据的指纹与确认时的备份不一致。" >&2
    fi
    printf '\nROLLBACK;\n'
    exit 1
)

verified_restore_stream | psql_restore -d "${STAGED_DATABASE}" --quiet --single-transaction --file=- \
    --set="restore_database=${STAGED_DATABASE}" --set="restore_sha=${BACKUP_SHA}"

# 暂存库完整提交后，在同一事务里切换两个库名。
psql_restore -d postgres --single-transaction --file=- \
    --set="target_database=${DB_NAME}" --set="staged_database=${STAGED_DATABASE}" \
    --set="previous_database=${PREVIOUS_DATABASE}" <<'SQL'
SELECT EXISTS (SELECT FROM pg_database WHERE datname = :'target_database') AS target_exists \gset
\if :target_exists
SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity
    WHERE datname = :'target_database' AND pid <> pg_backend_pid();
ALTER DATABASE :"target_database" RENAME TO :"previous_database";
\endif
ALTER DATABASE :"staged_database" RENAME TO :"target_database";
SQL
RESTORE_STAGED=false

psql_restore -d postgres --quiet --set="previous_database=${PREVIOUS_DATABASE}" --file=- <<'SQL'
DROP DATABASE IF EXISTS :"previous_database";
SQL

echo "[$(date)] 恢复完成!"

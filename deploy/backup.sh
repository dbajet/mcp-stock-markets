#!/usr/bin/env bash
# Daily sealed backup: pg_dump encrypted BEFORE touching disk, rotated over 31
# day-of-month slots, uploaded to S3 daily/ (+ monthly/ on the 1st).
# Runs inside the backup sidecar, which alone receives .env.backup.
#
# age, not `openssl enc`: age authenticates what it encrypts, so a tampered or
# truncated backup fails to decrypt instead of restoring garbage. Dumps are
# encrypted to a public key; the private key never lives on this server.
set -euo pipefail
umask 077

DAY="$(date -u +%d)"
STAMP="$(date -u +%Y-%m-%d)"
DIR="/backups/${DAY}"
mkdir -p "${DIR}"

# Sealed before it touches disk; atomic .tmp → mv.
PGPASSWORD="${DB_PASSWORD}" pg_dump -h mcp_stock_markets-db -U "${DB_USER}" -Fc "${DB_NAME}" \
    | age -r "${BACKUP_AGE_RECIPIENT}" \
    > "${DIR}/${DB_NAME}.dump.age.tmp"
mv "${DIR}/${DB_NAME}.dump.age.tmp" "${DIR}/${DB_NAME}.dump.age"

aws s3 cp "${DIR}/${DB_NAME}.dump.age" \
    "s3://${S3_BACKUP_BUCKET}/daily/mcp_stock_markets/${STAMP}/" --sse "${S3_SSE:-AES256}"

if [ "${DAY}" = "01" ]; then
    aws s3 cp "${DIR}/${DB_NAME}.dump.age" \
        "s3://${S3_BACKUP_BUCKET}/monthly/mcp_stock_markets/${STAMP}/" --sse "${S3_SSE:-AES256}"
fi

# Read by the compose healthcheck: the container turns unhealthy when this is overdue.
date -u +%s > /backups/last-success
# A dead-man's switch: the monitor alerts a person when these pings stop — a failed
# backup, a dead sidecar or a dead host alike. Its own failure must not fail the backup.
# Optional while no monitor exists: the run says so in its log.
if [ -n "${BACKUP_HEARTBEAT_URL:-}" ]; then
    curl -fsS --max-time 10 --retry 3 -o /dev/null "${BACKUP_HEARTBEAT_URL}" \
        || echo "warning: heartbeat ping failed" >&2
else
    echo "warning: BACKUP_HEARTBEAT_URL is empty — no monitor is told about this backup" >&2
fi
echo "backup done: ${STAMP} slot ${DAY}"

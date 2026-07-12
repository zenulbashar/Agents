#!/usr/bin/env bash
# Snapshot Foundry memory stores. Run nightly (launchd/cron); copy off-box weekly.
set -euo pipefail
cd "$(dirname "$0")/.."
DATA_DIR="${FOUNDRY_DATA_DIR:-./data}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${DATA_DIR}/backups/${STAMP}"
mkdir -p "$OUT"
CMP="docker compose -f docker/docker-compose.yml"

echo "==> Backing up to $OUT"
$CMP exec -T postgres pg_dump -U "${POSTGRES_USER:-foundry}" "${POSTGRES_DB:-foundry}" > "$OUT/postgres.sql"
# Qdrant: baseline tar of the storage volume (prefer the snapshot API in production).
tar -czf "$OUT/qdrant.tgz" -C "$DATA_DIR" qdrant 2>/dev/null || true
echo "Backup done. TODO: copy $OUT off-box (encrypted) and run a periodic restore test."

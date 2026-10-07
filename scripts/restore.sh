#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -eq 1 && -f "$1" ]] || { echo 'Usage: scripts/restore.sh backups/territory-TIMESTAMP.dump'; exit 1; }
echo 'This replaces the current local database. Make a fresh backup before continuing.'
read -r -p 'Type RESTORE to replace the local database: ' answer
[[ "$answer" == RESTORE ]] || exit 1
docker compose stop api expiry push
docker compose exec -T db pg_restore -U territory -d territory --clean --if-exists --exit-on-error --single-transaction < "$1"
docker compose run --rm migrate
docker compose up -d api expiry
echo 'Database restored. Optional push stays stopped until explicitly re-enabled.'

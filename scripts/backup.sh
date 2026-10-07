#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_path="backups/territory-$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary_path="${backup_path}.partial"
trap 'rm -f "$temporary_path"' EXIT
docker compose exec -T db pg_dump -U territory -d territory -Fc > "$temporary_path"
mv "$temporary_path" "$backup_path"
echo "Backup saved: $backup_path"
echo 'Keep a second copy on an external drive; a backup on the same laptop does not protect against drive failure.'

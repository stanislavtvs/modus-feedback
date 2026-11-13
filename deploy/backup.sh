#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /home/handyapp/modus-feedback
backup_dir=/var/backups/modus
mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
compose=(docker compose -p modus-server -f compose.yaml -f deploy/compose.server.yaml)
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$backup_dir/modus-$stamp.sql.gz.tmp"
mv "$backup_dir/modus-$stamp.sql.gz.tmp" "$backup_dir/modus-$stamp.sql.gz"
"${compose[@]}" exec -T web tar -czf - -C /app/private_uploads . > "$backup_dir/uploads-$stamp.tar.gz.tmp"
mv "$backup_dir/uploads-$stamp.tar.gz.tmp" "$backup_dir/uploads-$stamp.tar.gz"
find "$backup_dir" -maxdepth 1 -type f \( -name 'modus-*.sql.gz' -o -name 'uploads-*.tar.gz' \) -mtime +14 -delete

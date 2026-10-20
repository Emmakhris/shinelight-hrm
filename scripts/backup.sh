#!/bin/sh
# Encrypted PostgreSQL + documents backup for ShineLight HRM.
# Schedule daily via cron on the host, e.g.:  0 1 * * * /opt/shinelight/scripts/backup.sh
# Requires BACKUP_PASSPHRASE in the environment (store it in a password manager, NOT on the server only).
# Copy the resulting files off-site (e.g. rclone to S3/Backblaze) — a backup on the same VPS is not a backup.
set -eu

cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d-%H%M%S)
OUT=./backups
mkdir -p "$OUT"
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE}"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT/db-$STAMP.dump.enc"

docker compose exec -T backend tar -C /app -czf - media \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT/media-$STAMP.tgz.enc"

# keep 30 days locally
find "$OUT" -name '*.enc' -mtime +30 -delete
echo "Backup complete: $OUT/db-$STAMP.dump.enc, $OUT/media-$STAMP.tgz.enc"

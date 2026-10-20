#!/bin/sh
# Restore an encrypted backup produced by backup.sh. Test this quarterly on a staging server.
# Usage: BACKUP_PASSPHRASE=... scripts/restore.sh backups/db-YYYYMMDD-HHMMSS.dump.enc [backups/media-....tgz.enc]
set -eu
cd "$(dirname "$0")/.."
DB_FILE=${1:?db backup file}
MEDIA_FILE=${2:-}
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE}"

echo "This will REPLACE the current database. Type RESTORE to continue:"
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Aborted"; exit 1; }

docker compose stop backend worker beat
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$DB_FILE" \
  | docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'
if [ -n "$MEDIA_FILE" ]; then
  docker compose start backend
  openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$MEDIA_FILE" \
    | docker compose exec -T backend tar -C /app -xzf -
fi
docker compose up -d
docker compose exec backend python manage.py shell -c "from apps.audit.services import verify_chain; from apps.tenancy.models import Organization; print([(o.code, verify_chain(o.id)) for o in Organization.objects.all()])"
echo "Restore complete. Audit chain verification printed above."

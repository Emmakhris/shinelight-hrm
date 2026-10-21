#!/bin/sh
set -e

# Only the web container runs migrations/collectstatic (workers set SKIP_MIGRATIONS=1).
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  python manage.py migrate --noinput
  # Cloud edition on PostgreSQL: (re)apply row-level security after every migration.
  if [ "${DB_ROW_LEVEL_SECURITY:-False}" = "True" ]; then
    python manage.py enable_rls
  fi
  python manage.py collectstatic --noinput >/dev/null
fi

exec "$@"

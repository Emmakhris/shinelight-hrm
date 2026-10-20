#!/bin/sh
set -e

# Only the web container runs migrations/collectstatic (workers set SKIP_MIGRATIONS=1).
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput >/dev/null
fi

exec "$@"

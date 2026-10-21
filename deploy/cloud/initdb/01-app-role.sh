#!/bin/sh
# Runs once, when the PostgreSQL volume is first created (docker-entrypoint-initdb.d).
# The application must connect as a role that is not a superuser and has no BYPASSRLS, otherwise PostgreSQL
# silently skips row-level security. The role owns the database so migrations can create tables (which it then
# owns; FORCE ROW LEVEL SECURITY makes the policies apply to the owner too).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE "${APP_DB_USER}" LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS NOCREATEROLE;
ALTER DATABASE "${POSTGRES_DB}" OWNER TO "${APP_DB_USER}";
GRANT ALL ON SCHEMA public TO "${APP_DB_USER}";
SQL

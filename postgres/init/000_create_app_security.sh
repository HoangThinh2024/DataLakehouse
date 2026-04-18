#!/usr/bin/env bash
set -euo pipefail

APP_CONFIGS=(
  "${MAGE_DB_NAME:-dlh_mage}|${MAGE_DB_USER:-dlh_mage_user}|${MAGE_DB_PASSWORD:-change-me}"
  "${NOCODB_DB_NAME:-dlh_nocodb}|${NOCODB_DB_USER:-dlh_nocodb_user}|${NOCODB_DB_PASSWORD:-change-me}"
  "${SUPERSET_DB_NAME:-dlh_superset}|${SUPERSET_DB_USER:-dlh_superset_user}|${SUPERSET_DB_PASSWORD:-change-me}"
  "${GRAFANA_DB_NAME:-dlh_grafana}|${GRAFANA_DB_USER:-dlh_grafana_user}|${GRAFANA_DB_PASSWORD:-change-me}"
)

check_admin_access() {
  if psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -Atqc 'SELECT 1' >/dev/null 2>&1; then
    return 0
  fi

  cat >&2 <<EOF
postgres-bootstrap: cannot authenticate to PostgreSQL with POSTGRES_USER="${POSTGRES_USER}".
The most likely cause is a stale postgres_data volume that was initialized with a different POSTGRES_PASSWORD.
If you changed the admin password, reset the volume with: docker compose down -v && docker compose up -d
EOF
  exit 2
}

check_admin_access

for cfg in "${APP_CONFIGS[@]}"; do
  IFS='|' read -r app_db app_user app_password <<< "$cfg"
  app_password_sql=${app_password//\'/\'\'}

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO
\$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${app_user}') THEN
    CREATE ROLE "${app_user}" LOGIN PASSWORD '${app_password_sql}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  ELSE
    ALTER ROLE "${app_user}" LOGIN PASSWORD '${app_password_sql}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE "${app_db}" OWNER "${app_user}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${app_db}')
\gexec

REVOKE ALL ON DATABASE "${app_db}" FROM PUBLIC;
GRANT CONNECT, TEMP ON DATABASE "${app_db}" TO "${app_user}";
SQL

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$app_db" <<SQL
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO "${app_user}";
ALTER SCHEMA public OWNER TO "${app_user}";
SQL
done

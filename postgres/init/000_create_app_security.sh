#!/usr/bin/env bash
set -euo pipefail

APP_CONFIGS=(
  "${MAGE_DB_NAME:-dlh_mage}|${MAGE_DB_USER:-dlh_mage_user}|${MAGE_DB_PASSWORD:-change-me}"
  "${NOCODB_DB_NAME:-dlh_nocodb}|${NOCODB_DB_USER:-dlh_nocodb_user}|${NOCODB_DB_PASSWORD:-change-me}"
  "${SUPERSET_DB_NAME:-dlh_superset}|${SUPERSET_DB_USER:-dlh_superset_user}|${SUPERSET_DB_PASSWORD:-change-me}"
  "${GRAFANA_DB_NAME:-dlh_grafana}|${GRAFANA_DB_USER:-dlh_grafana_user}|${GRAFANA_DB_PASSWORD:-change-me}"
  "${AUTHENTIK_DB_NAME:-dlh_authentik}|${AUTHENTIK_DB_USER:-dlh_authentik_user}|${AUTHENTIK_DB_PASSWORD:-change-me}"
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

# ==============================================================
# Custom workspace: CUSTOM_DB_NAME / CUSTOM_DB_USER / CUSTOM_SCHEMA
# Created only when CUSTOM_DB_NAME is non-empty.
# This database/user/schema is completely isolated from the stack
# service databases above and is intended for user-defined ETL and
# reporting workflows.
# ==============================================================
CUSTOM_DB_NAME="${CUSTOM_DB_NAME:-}"
CUSTOM_DB_USER="${CUSTOM_DB_USER:-}"
CUSTOM_DB_PASSWORD="${CUSTOM_DB_PASSWORD:-}"
CUSTOM_SCHEMA="${CUSTOM_SCHEMA:-}"

if [ -n "$CUSTOM_DB_NAME" ] && [ -n "$CUSTOM_DB_USER" ] && [ -n "$CUSTOM_DB_PASSWORD" ]; then
  echo "postgres-bootstrap: provisioning custom workspace db='${CUSTOM_DB_NAME}' user='${CUSTOM_DB_USER}' schema='${CUSTOM_SCHEMA:-public}'"

  custom_password_sql=${CUSTOM_DB_PASSWORD//\'/\'\'}

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO
\$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${CUSTOM_DB_USER}') THEN
    CREATE ROLE "${CUSTOM_DB_USER}" LOGIN PASSWORD '${custom_password_sql}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  ELSE
    ALTER ROLE "${CUSTOM_DB_USER}" LOGIN PASSWORD '${custom_password_sql}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE "${CUSTOM_DB_NAME}" OWNER "${CUSTOM_DB_USER}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${CUSTOM_DB_NAME}')
\gexec

REVOKE ALL ON DATABASE "${CUSTOM_DB_NAME}" FROM PUBLIC;
GRANT CONNECT, TEMP ON DATABASE "${CUSTOM_DB_NAME}" TO "${CUSTOM_DB_USER}";
-- Also allow the admin user full access to the custom DB for ETL and maintenance
GRANT ALL PRIVILEGES ON DATABASE "${CUSTOM_DB_NAME}" TO "${POSTGRES_USER}";
SQL

  # Create the custom schema inside the custom database (skip if schema is "public")
  EFFECTIVE_SCHEMA="${CUSTOM_SCHEMA:-public}"

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$CUSTOM_DB_NAME" <<SQL
-- Ensure the custom schema exists
DO
\$\$
BEGIN
  IF '${EFFECTIVE_SCHEMA}' <> 'public' THEN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${EFFECTIVE_SCHEMA}') THEN
      CREATE SCHEMA "${EFFECTIVE_SCHEMA}" AUTHORIZATION "${CUSTOM_DB_USER}";
    ELSE
      ALTER SCHEMA "${EFFECTIVE_SCHEMA}" OWNER TO "${CUSTOM_DB_USER}";
    END IF;
  END IF;
END
\$\$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO "${CUSTOM_DB_USER}";
GRANT USAGE, CREATE ON SCHEMA "${EFFECTIVE_SCHEMA}" TO "${CUSTOM_DB_USER}";
ALTER ROLE "${CUSTOM_DB_USER}" SET search_path TO "${EFFECTIVE_SCHEMA}", public;
SQL

  echo "postgres-bootstrap: custom workspace ready – db='${CUSTOM_DB_NAME}' schema='${EFFECTIVE_SCHEMA}' user='${CUSTOM_DB_USER}'"
else
  echo "postgres-bootstrap: CUSTOM_DB_NAME/CUSTOM_DB_USER/CUSTOM_DB_PASSWORD not set – skipping custom workspace creation"
fi

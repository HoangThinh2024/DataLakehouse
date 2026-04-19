#!/usr/bin/env bash
# =============================================================
# DataLakehouse – Interactive Deployment Setup
# =============================================================
# Usage:
#   bash scripts/setup.sh
#
# What this script does:
#   1. Walks you through every configuration variable with defaults.
#   2. Writes a .env file in the project root.
#   3. Creates the Docker network (web_network) if it does not exist.
#   4. Runs `docker compose up -d`.
#   5. (Optional) Asks if you want to run ETL and create dashboards.
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

# ── Colour helpers ──────────────────────────────────────────
_bold()  { printf '\033[1m%s\033[0m' "$*"; }
_cyan()  { printf '\033[36m%s\033[0m' "$*"; }
_green() { printf '\033[32m%s\033[0m' "$*"; }
_yellow(){ printf '\033[33m%s\033[0m' "$*"; }
_red()   { printf '\033[31m%s\033[0m' "$*"; }

header() { echo; echo "$(_bold "$(_cyan "=== $* ===")")"; echo; }
info()   { echo "  $(_green "→") $*"; }
warn()   { echo "  $(_yellow "⚠") $*"; }
err()    { echo "  $(_red "✗") $*" >&2; }

# ── Prompt helper ───────────────────────────────────────────
# ask VAR_NAME "Description" "default_value"
# Sets global variable named VAR_NAME.
ask() {
  local var_name="$1"
  local description="$2"
  local default_value="${3:-}"
  local prompt

  if [ -n "$default_value" ]; then
    prompt="  $description [$(_cyan "$default_value")]: "
  else
    prompt="  $description (required): "
  fi

  local value
  while true; do
    read -r -p "$prompt" value
    value="${value:-$default_value}"
    if [ -n "$value" ]; then
      break
    fi
    warn "Value cannot be empty."
  done

  # Export to calling scope via printf + eval trick (bash compatible)
  eval "${var_name}=\"\${value}\""
}

# ── ask_yn helper ────────────────────────────────────────────
ask_yn() {
  local prompt="$1"
  local default="${2:-n}"
  local answer
  read -r -p "  $prompt [$(_cyan "$default")]: " answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy] ]]
}

# ── Load existing .env if present ───────────────────────────
load_existing_env() {
  if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key value; do
      key="${key%%#*}"   # strip inline comments
      key="${key// /}"   # trim spaces
      value="${value%%#*}"
      value="${value## }"; value="${value%% }"
      value="${value#\"}"; value="${value%\"}"
      value="${value#\'}"; value="${value%\'}"
      [ -z "$key" ] && continue
      export "$key"="$value" 2>/dev/null || true
    done < <(grep -v '^\s*#' "$ENV_FILE" | grep '=')
  fi
}

# ── Default values (sourced from existing .env or hardcoded) ─
load_existing_env

# =============================================================
header "DataLakehouse – Guided Setup"
echo "  This wizard configures your .env file and deploys the stack."
echo "  Press Enter to accept the value shown in $(_cyan "[ ]")."
echo "  Existing values from .env are shown as defaults."

# =============================================================
header "1 / 8 – Global Settings"

ask TZ           "Timezone"                             "${TZ:-Asia/Ho_Chi_Minh}"
ask DLH_BIND_IP  "Bind IP (127.0.0.1 = local only)"    "${DLH_BIND_IP:-127.0.0.1}"

# =============================================================
header "2 / 8 – Docker Image Versions"

ask POSTGRES_IMAGE_VERSION   "PostgreSQL image tag"         "${POSTGRES_IMAGE_VERSION:-17-alpine}"
ask RUSTFS_IMAGE_VERSION     "RustFS image tag"             "${RUSTFS_IMAGE_VERSION:-latest}"
ask MINIO_MC_IMAGE_VERSION   "MinIO mc (rustfs-init) tag"   "${MINIO_MC_IMAGE_VERSION:-latest}"
ask CLICKHOUSE_IMAGE_VERSION "ClickHouse image tag"         "${CLICKHOUSE_IMAGE_VERSION:-latest}"
ask MAGE_IMAGE_VERSION       "Mage image tag"               "${MAGE_IMAGE_VERSION:-latest}"
ask NOCODB_IMAGE_VERSION     "NocoDB image tag"             "${NOCODB_IMAGE_VERSION:-latest}"
ask SUPERSET_IMAGE_VERSION   "Superset image tag"           "${SUPERSET_IMAGE_VERSION:-latest}"
ask GRAFANA_IMAGE_VERSION    "Grafana image tag"            "${GRAFANA_IMAGE_VERSION:-latest}"

# =============================================================
header "3 / 8 – Core PostgreSQL (Admin)"

ask POSTGRES_DB       "Admin database name"     "${POSTGRES_DB:-datalakehouse}"
ask POSTGRES_USER     "Admin username"           "${POSTGRES_USER:-dlh_admin}"
ask POSTGRES_PASSWORD "Admin password"           "${POSTGRES_PASSWORD:-change-this-admin-password}"
ask DLH_POSTGRES_PORT "Host port for PostgreSQL" "${DLH_POSTGRES_PORT:-25432}"

# =============================================================
header "4 / 8 – Custom Workspace (optional)"
echo "  Create an isolated PostgreSQL database / schema / user for your"
echo "  own ETL and reporting. Leave CUSTOM_DB_NAME empty to skip."

ask CUSTOM_DB_NAME     "Custom database name (blank = skip)" "${CUSTOM_DB_NAME:-dlh_custom}"
if [ -n "$CUSTOM_DB_NAME" ]; then
  ask CUSTOM_DB_USER     "Custom username"     "${CUSTOM_DB_USER:-dlh_custom_user}"
  ask CUSTOM_DB_PASSWORD "Custom password"     "${CUSTOM_DB_PASSWORD:-change-this-custom-password}"
  ask CUSTOM_SCHEMA      "Custom schema name"  "${CUSTOM_SCHEMA:-custom_schema}"
else
  CUSTOM_DB_USER=""
  CUSTOM_DB_PASSWORD=""
  CUSTOM_SCHEMA=""
fi

# =============================================================
header "5 / 8 – RustFS (Object Storage)"

ask RUSTFS_ACCESS_KEY           "RustFS access key"            "${RUSTFS_ACCESS_KEY:-rustfsadmin}"
ask RUSTFS_SECRET_KEY           "RustFS secret key"            "${RUSTFS_SECRET_KEY:-rustfsadmin}"
ask DLH_RUSTFS_API_PORT         "Host port for RustFS API"     "${DLH_RUSTFS_API_PORT:-29100}"
ask DLH_RUSTFS_CONSOLE_PORT     "Host port for RustFS console" "${DLH_RUSTFS_CONSOLE_PORT:-29101}"

# =============================================================
header "6 / 8 – ClickHouse"

ask CLICKHOUSE_DB             "ClickHouse database"        "${CLICKHOUSE_DB:-analytics}"
ask CLICKHOUSE_USER           "ClickHouse user"            "${CLICKHOUSE_USER:-default}"
ask CLICKHOUSE_PASSWORD       "ClickHouse password (blank ok)" "${CLICKHOUSE_PASSWORD:-}"
ask DLH_CLICKHOUSE_HTTP_PORT  "Host port – ClickHouse HTTP" "${DLH_CLICKHOUSE_HTTP_PORT:-28123}"
ask DLH_CLICKHOUSE_TCP_PORT   "Host port – ClickHouse TCP"  "${DLH_CLICKHOUSE_TCP_PORT:-29000}"

# =============================================================
header "7 / 8 – App Service Passwords"
echo "  (Mage, NocoDB, Superset, Grafana metadata DB passwords)"

ask MAGE_DB_PASSWORD     "Mage DB password"     "${MAGE_DB_PASSWORD:-change-this-mage-password}"
ask NOCODB_DB_PASSWORD   "NocoDB DB password"   "${NOCODB_DB_PASSWORD:-change-this-nocodb-password}"
ask SUPERSET_SECRET_KEY  "Superset secret key"  "${SUPERSET_SECRET_KEY:-replace-this-secret}"
ask SUPERSET_DB_PASSWORD "Superset DB password" "${SUPERSET_DB_PASSWORD:-change-this-superset-db-password}"
ask SUPERSET_ADMIN_USER  "Superset admin user"  "${SUPERSET_ADMIN_USER:-admin}"
ask SUPERSET_ADMIN_PASSWORD "Superset admin password" "${SUPERSET_ADMIN_PASSWORD:-admin}"
ask GRAFANA_DB_PASSWORD  "Grafana DB password"  "${GRAFANA_DB_PASSWORD:-change-this-grafana-db-password}"
ask GRAFANA_ADMIN_USER   "Grafana admin user"   "${GRAFANA_ADMIN_USER:-admin}"
ask GRAFANA_ADMIN_PASSWORD "Grafana admin password" "${GRAFANA_ADMIN_PASSWORD:-admin}"

# =============================================================
header "8 / 8 – Port Assignments"

ask DLH_MAGE_PORT    "Host port – Mage"    "${DLH_MAGE_PORT:-26789}"
ask DLH_NOCODB_PORT  "Host port – NocoDB"  "${DLH_NOCODB_PORT:-28082}"
ask DLH_SUPERSET_PORT "Host port – Superset" "${DLH_SUPERSET_PORT:-28088}"
ask DLH_GRAFANA_PORT  "Host port – Grafana"  "${DLH_GRAFANA_PORT:-23001}"

# =============================================================
# Write .env
# =============================================================
header "Writing .env"

cat > "$ENV_FILE" <<EOF
# ============================================================
# DataLakehouse – generated by scripts/setup.sh
# $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# ============================================================

TZ=${TZ}
DLH_BIND_IP=${DLH_BIND_IP}

# Docker Image Versions
POSTGRES_IMAGE_VERSION=${POSTGRES_IMAGE_VERSION}
RUSTFS_IMAGE_VERSION=${RUSTFS_IMAGE_VERSION}
MINIO_MC_IMAGE_VERSION=${MINIO_MC_IMAGE_VERSION}
CLICKHOUSE_IMAGE_VERSION=${CLICKHOUSE_IMAGE_VERSION}
MAGE_IMAGE_VERSION=${MAGE_IMAGE_VERSION}
NOCODB_IMAGE_VERSION=${NOCODB_IMAGE_VERSION}
SUPERSET_IMAGE_VERSION=${SUPERSET_IMAGE_VERSION}
GRAFANA_IMAGE_VERSION=${GRAFANA_IMAGE_VERSION}

# Core PostgreSQL
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DLH_POSTGRES_PORT=${DLH_POSTGRES_PORT}

# Custom Workspace
CUSTOM_DB_NAME=${CUSTOM_DB_NAME}
CUSTOM_DB_USER=${CUSTOM_DB_USER}
CUSTOM_DB_PASSWORD=${CUSTOM_DB_PASSWORD}
CUSTOM_SCHEMA=${CUSTOM_SCHEMA}

# RustFS
RUSTFS_ACCESS_KEY=${RUSTFS_ACCESS_KEY}
RUSTFS_SECRET_KEY=${RUSTFS_SECRET_KEY}
DLH_RUSTFS_API_PORT=${DLH_RUSTFS_API_PORT}
DLH_RUSTFS_CONSOLE_PORT=${DLH_RUSTFS_CONSOLE_PORT}
RUSTFS_CORS_ALLOWED_ORIGINS=http://${DLH_BIND_IP}:${DLH_RUSTFS_API_PORT}
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=http://${DLH_BIND_IP}:${DLH_RUSTFS_CONSOLE_PORT}
RUSTFS_BUCKET=nocodb
RUSTFS_BRONZE_BUCKET=bronze
RUSTFS_SILVER_BUCKET=silver
RUSTFS_GOLD_BUCKET=gold

# ClickHouse
CLICKHOUSE_DB=${CLICKHOUSE_DB}
CLICKHOUSE_USER=${CLICKHOUSE_USER}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
DLH_CLICKHOUSE_HTTP_PORT=${DLH_CLICKHOUSE_HTTP_PORT}
DLH_CLICKHOUSE_TCP_PORT=${DLH_CLICKHOUSE_TCP_PORT}

# Mage
DLH_MAGE_PORT=${DLH_MAGE_PORT}
MAGE_DB_NAME=dlh_mage
MAGE_DB_USER=dlh_mage_user
MAGE_DB_PASSWORD=${MAGE_DB_PASSWORD}
SOURCE_DB_NAME=${POSTGRES_DB}
SOURCE_DB_USER=${POSTGRES_USER}
SOURCE_DB_PASSWORD=${POSTGRES_PASSWORD}
SOURCE_SCHEMA=${CUSTOM_SCHEMA:-public}
SOURCE_TABLE=
SOURCE_TABLE_CANDIDATES=Demo,test_projects
CSV_UPLOAD_BUCKET=bronze
CSV_UPLOAD_PREFIX=csv_upload/
CSV_UPLOAD_ALLOW_ANYWHERE=true
CSV_UPLOAD_SEPARATOR=,
CSV_UPLOAD_ENCODING=utf-8
CSV_UPLOAD_SCAN_LIMIT=200

# NocoDB
DLH_NOCODB_PORT=${DLH_NOCODB_PORT}
NOCODB_DB_NAME=dlh_nocodb
NOCODB_DB_USER=dlh_nocodb_user
NOCODB_DB_PASSWORD=${NOCODB_DB_PASSWORD}

# Superset
DLH_SUPERSET_PORT=${DLH_SUPERSET_PORT}
SUPERSET_SECRET_KEY=${SUPERSET_SECRET_KEY}
SUPERSET_DB_NAME=dlh_superset
SUPERSET_DB_USER=dlh_superset_user
SUPERSET_DB_PASSWORD=${SUPERSET_DB_PASSWORD}
SUPERSET_ADMIN_USER=${SUPERSET_ADMIN_USER}
SUPERSET_ADMIN_PASSWORD=${SUPERSET_ADMIN_PASSWORD}
SUPERSET_ADMIN_EMAIL=admin@superset.local

# Grafana
DLH_GRAFANA_PORT=${DLH_GRAFANA_PORT}
GRAFANA_DB_NAME=dlh_grafana
GRAFANA_DB_USER=dlh_grafana_user
GRAFANA_DB_PASSWORD=${GRAFANA_DB_PASSWORD}
GRAFANA_ADMIN_USER=${GRAFANA_ADMIN_USER}
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}

# Nginx Proxy Manager (optional)
DLH_NPM_HTTP_PORT=28080
DLH_NPM_HTTPS_PORT=28443
DLH_NPM_ADMIN_PORT=28081
EOF

info ".env written to $ENV_FILE"

# =============================================================
# Docker network
# =============================================================
header "Docker Network"

if docker network inspect web_network >/dev/null 2>&1; then
  info "Docker network 'web_network' already exists."
else
  info "Creating Docker network 'web_network' …"
  docker network create web_network
  info "Network created."
fi

# =============================================================
# Deploy
# =============================================================
header "Deploying Stack"

cd "$REPO_ROOT"
info "Running: docker compose up -d"
docker compose up -d

info "Stack is starting. Use 'docker compose logs -f <service>' to follow logs."
echo
echo "  Service URLs:"
echo "    PostgreSQL : postgresql://localhost:${DLH_POSTGRES_PORT}"
echo "    RustFS     : http://localhost:${DLH_RUSTFS_CONSOLE_PORT}"
echo "    ClickHouse : http://localhost:${DLH_CLICKHOUSE_HTTP_PORT}"
echo "    Mage       : http://localhost:${DLH_MAGE_PORT}"
echo "    NocoDB     : http://localhost:${DLH_NOCODB_PORT}"
echo "    Superset   : http://localhost:${DLH_SUPERSET_PORT}"
echo "    Grafana    : http://localhost:${DLH_GRAFANA_PORT}"

# =============================================================
# Optional: ETL + Dashboard
# =============================================================
echo
if ask_yn "Run ETL and create Superset dashboards now? (requires services to be healthy)" "n"; then
  echo
  info "Launching ETL and dashboard setup …"
  python3 "$REPO_ROOT/scripts/run_etl_and_dashboard.py"
else
  echo
  info "Skipped ETL/dashboard setup."
  echo "  Run it later with:"
  echo "    python3 scripts/run_etl_and_dashboard.py"
fi

echo
echo "$(_bold "$(_green "Setup complete!")")"

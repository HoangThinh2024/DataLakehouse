#!/usr/bin/env bash
# ============================================================================
# DataLakehouse – Interactive Deployment Setup & Bootstrap
# ============================================================================
# Purpose:
#   Complete guided setup for DataLakehouse deployment:
#   - Guided .env configuration
#   - Docker network creation
#   - Stack deployment via stackctl.sh
#   - Optional: UFW firewall setup, Python sync, ETL/dashboards
#
# Usage:
#   bash scripts/setup.sh
#
# The script is organized into logical phases:
#   Phase 1: Environment and settings validation
#   Phase 2: Interactive configuration questionnaire
#   Phase 3: .env file generation
#   Phase 4: Docker network setup
#   Phase 5: Stack deployment
#   Phase 6: Optional post-deployment tasks (firewall, Python, ETL)
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

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

# ── Python environment helpers (uv) ───────────────────────
ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "Found uv: $(uv --version)"
    return 0
  fi

  warn "uv (Astral) is not installed."
  if ! ask_yn "Install uv now via official installer?" "y"; then
    return 1
  fi

  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    err "Neither curl nor wget is available to install uv automatically."
    return 1
  fi

  # uv installer typically places binaries in ~/.local/bin
  export PATH="$HOME/.local/bin:$PATH"

  if command -v uv >/dev/null 2>&1; then
    info "Installed uv: $(uv --version)"
    return 0
  fi

  err "uv installation finished but command is not in PATH yet."
  echo "  Open a new shell or run: export PATH=\"$HOME/.local/bin:\$PATH\""
  return 1
}

sync_python_env() {
  if ! ensure_uv; then
    warn "Skipping Python dependency setup (uv not available)."
    return 1
  fi

  info "Syncing Python dependencies with uv (all groups) …"
  (cd "$REPO_ROOT" && uv sync --all-groups)
  info "Python environment ready at $REPO_ROOT/.venv"
  return 0
}

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
    local line key value
    while IFS= read -r line; do
      [[ "$line" =~ ^[[:space:]]*$ ]] && continue
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ "$line" != *"="* ]] && continue

      key="${line%%=*}"
      value="${line#*=}"

      key="${key#"${key%%[![:space:]]*}"}"
      key="${key%"${key##*[![:space:]]}"}"
      value="${value#"${value%%[![:space:]]*}"}"
      value="${value%"${value##*[![:space:]]}"}"

      value="${value#\"}"; value="${value%\"}"
      value="${value#\'}"; value="${value%\'}"
      [ -z "$key" ] && continue
      export "$key"="$value" 2>/dev/null || true
    done < "$ENV_FILE"
  fi
}

# ── Default values (sourced from existing .env or hardcoded) ─
load_existing_env

DLH_LAN_CIDR="${DLH_LAN_CIDR:-192.168.1.0/24}"
UFW_ALLOW_DATA_PORTS="${UFW_ALLOW_DATA_PORTS:-false}"

# =============================================================
header "DataLakehouse – Guided Setup"
echo "  This wizard configures your .env file and deploys the stack."
echo "  Press Enter to accept the value shown in $(_cyan "[ ]")."
echo "  Existing values from .env are shown as defaults."

# =============================================================
header "1 / 8 – Global Settings"

ask TZ           "Timezone"                             "${TZ:-Asia/Ho_Chi_Minh}"
ask DLH_BIND_IP  "Bind IP (127.0.0.1 = local only)"    "${DLH_BIND_IP:-127.0.0.1}"
ask DLH_APP_BIND_IP  "App/UI bind IP (use 127.0.0.1 when using reverse proxy)" "${DLH_APP_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}"
ask DLH_DATA_BIND_IP "Data/DB bind IP (use 0.0.0.0 for LAN clients)"            "${DLH_DATA_BIND_IP:-0.0.0.0}"
ask DLH_LAN_CIDR "LAN CIDR for firewall rules"          "${DLH_LAN_CIDR:-192.168.1.0/24}"
ask UFW_ALLOW_DATA_PORTS "Allow data ports to LAN (true/false)" "${UFW_ALLOW_DATA_PORTS:-false}"

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
  SOURCE_DB_NAME_VAL="$CUSTOM_DB_NAME"
  SOURCE_DB_USER_VAL="$CUSTOM_DB_USER"
  SOURCE_DB_PASSWORD_VAL="$CUSTOM_DB_PASSWORD"
  SOURCE_SCHEMA_VAL="$CUSTOM_SCHEMA"
else
  CUSTOM_DB_USER=""
  CUSTOM_DB_PASSWORD=""
  CUSTOM_SCHEMA=""
  SOURCE_DB_NAME_VAL="$POSTGRES_DB"
  SOURCE_DB_USER_VAL="$POSTGRES_USER"
  SOURCE_DB_PASSWORD_VAL="$POSTGRES_PASSWORD"
  SOURCE_SCHEMA_VAL="public"
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
ask MAGE_DEFAULT_OWNER_EMAIL "Mage default owner email" "${MAGE_DEFAULT_OWNER_EMAIL:-admin@admin.com}"
ask MAGE_DEFAULT_OWNER_USERNAME "Mage default owner username" "${MAGE_DEFAULT_OWNER_USERNAME:-admin}"
ask MAGE_DEFAULT_OWNER_PASSWORD "Mage default owner password" "${MAGE_DEFAULT_OWNER_PASSWORD:-admin}"
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
# DataLakehouse Environment Configuration
# ============================================================
# This file was auto-generated by scripts/setup.sh
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
#
# IMPORTANT NOTES:
#  • Keep credentials secure (do NOT commit to Git)
#  • Port values (DLH_*_PORT) must be unique
#  • Changes take effect after: docker compose restart <service>
#  • Use stackctl.sh for common operations:
#    - bash scripts/stackctl.sh up
#    - bash scripts/stackctl.sh down
#    - bash scripts/stackctl.sh redeploy
#    - bash scripts/stackctl.sh check-env
#    - bash scripts/stackctl.sh check-system
# ============================================================

# ─ Global Settings ─────────────────────────────────────────
TZ=${TZ}
DLH_BIND_IP=${DLH_BIND_IP}
DLH_APP_BIND_IP=${DLH_APP_BIND_IP}
DLH_DATA_BIND_IP=${DLH_DATA_BIND_IP}
DLH_LAN_CIDR=${DLH_LAN_CIDR}
UFW_ALLOW_DATA_PORTS=${UFW_ALLOW_DATA_PORTS}

# ─ Docker Image Versions ───────────────────────────────────
# Pin versions for reproducibility. Use 'latest' for auto-updates.
POSTGRES_IMAGE_VERSION=${POSTGRES_IMAGE_VERSION}
RUSTFS_IMAGE_VERSION=${RUSTFS_IMAGE_VERSION}
MINIO_MC_IMAGE_VERSION=${MINIO_MC_IMAGE_VERSION}
CLICKHOUSE_IMAGE_VERSION=${CLICKHOUSE_IMAGE_VERSION}
MAGE_IMAGE_VERSION=${MAGE_IMAGE_VERSION}
NOCODB_IMAGE_VERSION=${NOCODB_IMAGE_VERSION}
SUPERSET_IMAGE_VERSION=${SUPERSET_IMAGE_VERSION}
GRAFANA_IMAGE_VERSION=${GRAFANA_IMAGE_VERSION}

# ─ Core PostgreSQL (System Admin) ──────────────────────────
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DLH_POSTGRES_PORT=${DLH_POSTGRES_PORT}
POSTGRES_HOST=dlh-postgres

# ─ Custom Workspace (for isolated ETL/reporting) ───────────
CUSTOM_DB_NAME=${CUSTOM_DB_NAME}
CUSTOM_DB_USER=${CUSTOM_DB_USER}
CUSTOM_DB_PASSWORD=${CUSTOM_DB_PASSWORD}
CUSTOM_SCHEMA=${CUSTOM_SCHEMA}

# ─ RustFS (Object Storage via S3-like API) ────────────────
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

# ─ ClickHouse (Analytics Data Warehouse) ───────────────────
CLICKHOUSE_DB=${CLICKHOUSE_DB}
CLICKHOUSE_USER=${CLICKHOUSE_USER}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
DLH_CLICKHOUSE_HTTP_PORT=${DLH_CLICKHOUSE_HTTP_PORT}
DLH_CLICKHOUSE_TCP_PORT=${DLH_CLICKHOUSE_TCP_PORT}

# ─ Mage (ETL Orchestration) ────────────────────────────────
DLH_MAGE_PORT=${DLH_MAGE_PORT}
MAGE_DB_NAME=dlh_mage
MAGE_DB_USER=dlh_mage_user
MAGE_DB_PASSWORD=${MAGE_DB_PASSWORD}
MAGE_DEFAULT_OWNER_EMAIL=${MAGE_DEFAULT_OWNER_EMAIL}
MAGE_DEFAULT_OWNER_USERNAME=${MAGE_DEFAULT_OWNER_USERNAME}
MAGE_DEFAULT_OWNER_PASSWORD=${MAGE_DEFAULT_OWNER_PASSWORD}
SOURCE_DB_NAME=${SOURCE_DB_NAME_VAL}
SOURCE_DB_USER=${SOURCE_DB_USER_VAL}
SOURCE_DB_PASSWORD=${SOURCE_DB_PASSWORD_VAL}
SOURCE_SCHEMA=${SOURCE_SCHEMA_VAL}
SOURCE_SCHEMA_FALLBACKS=public
SOURCE_TABLE=
SOURCE_TABLE_CANDIDATES=Demo,test_projects,sales_orders
CSV_UPLOAD_BUCKET=bronze
CSV_UPLOAD_PREFIX=csv_upload/
CSV_UPLOAD_ALLOW_ANYWHERE=true
CSV_UPLOAD_SEPARATOR=,
CSV_UPLOAD_ENCODING=utf-8
CSV_UPLOAD_SCAN_LIMIT=200

# ─ NocoDB (Database UI) ────────────────────────────────────
DLH_NOCODB_PORT=${DLH_NOCODB_PORT}
NOCODB_DB_NAME=dlh_nocodb
NOCODB_DB_USER=dlh_nocodb_user
NOCODB_DB_PASSWORD=${NOCODB_DB_PASSWORD}

# ─ Superset (BI and Analytics) ─────────────────────────────
DLH_SUPERSET_PORT=${DLH_SUPERSET_PORT}
SUPERSET_SECRET_KEY=${SUPERSET_SECRET_KEY}
SUPERSET_DB_NAME=dlh_superset
SUPERSET_DB_USER=dlh_superset_user
SUPERSET_DB_PASSWORD=${SUPERSET_DB_PASSWORD}
SUPERSET_ADMIN_USER=${SUPERSET_ADMIN_USER}
SUPERSET_ADMIN_PASSWORD=${SUPERSET_ADMIN_PASSWORD}
SUPERSET_ADMIN_EMAIL=admin@superset.local
SUPERSET_PREFERRED_URL_SCHEME=http

# ─ Grafana (Monitoring & Dashboards) ───────────────────────
DLH_GRAFANA_PORT=${DLH_GRAFANA_PORT}
GRAFANA_DB_NAME=dlh_grafana
GRAFANA_DB_USER=dlh_grafana_user
GRAFANA_DB_PASSWORD=${GRAFANA_DB_PASSWORD}
GRAFANA_ADMIN_USER=${GRAFANA_ADMIN_USER}
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}

# ─ Nginx Proxy Manager (optional, for reverse proxy) ───────
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
info "Running: bash scripts/stackctl.sh up"
bash "$REPO_ROOT/scripts/stackctl.sh" up

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
# Optional: UFW + ufw-docker for LAN deployments
# =============================================================
if [ "$DLH_BIND_IP" != "127.0.0.1" ]; then
  echo
  if ask_yn "Configure UFW + ufw-docker for LAN access now?" "y"; then
    info "Configuring host firewall for LAN CIDR ${DLH_LAN_CIDR} …"
    bash "$REPO_ROOT/scripts/setup_ufw_docker.sh" "$DLH_LAN_CIDR" || \
      warn "Firewall setup script failed. Review output and rerun manually."
  else
    info "Skipped firewall setup."
    echo "  You can run it later with:"
    echo "    bash scripts/setup_ufw_docker.sh ${DLH_LAN_CIDR}"
  fi
fi

# =============================================================
# Python deps for host scripts
# =============================================================
echo
if ask_yn "Prepare host Python environment with uv sync now?" "y"; then
  sync_python_env || true
else
  info "Skipped Python environment setup."
  echo "  You can run it later with:"
  echo "    uv sync --all-groups"
fi

# =============================================================
# Optional: ETL + Dashboard
# =============================================================
echo
if ask_yn "Run ETL and create Superset dashboards now? (requires services to be healthy)" "n"; then
  echo
  info "Launching ETL and dashboard setup …"
  if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && uv run python scripts/run_etl_and_dashboard.py --auto)
  else
    warn "uv not found, falling back to python3."
    python3 "$REPO_ROOT/scripts/run_etl_and_dashboard.py" --auto
  fi
else
  echo
  info "Skipped ETL/dashboard setup."
  echo "  Run it later with:"
  echo "    uv run python scripts/run_etl_and_dashboard.py"
fi

echo
echo "$(_bold "$(_green "Setup complete!")")"

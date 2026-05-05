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

# Source environment library
if [[ -f "$REPO_ROOT/scripts/lib_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/scripts/lib_env.sh"
else
  echo "Error: scripts/lib_env.sh not found" >&2
  exit 1
fi

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

# ── Default values (sourced from existing .env or hardcoded) ─
load_env_file

# =============================================================
header "DataLakehouse – Guided Setup"
echo "  This wizard configures your .env file and deploys the stack."
echo "  Press Enter to accept the value shown in [ ]."
echo "  Existing values from .env are shown as defaults."

# ── Phase 0: Pre-flight Checks ───────────────────────────────
header "0 / 8 – Pre-flight Checks"

check_failed=0

if command -v docker >/dev/null 2>&1; then
  info "Docker: $(docker --version)"
else
  err "Docker not found. Please install Docker Engine first."
  check_failed=1
fi

if docker compose version >/dev/null 2>&1; then
  info "Docker Compose: $(docker compose version | head -1)"
else
  err "Docker Compose not found. Please install the Docker Compose plugin."
  check_failed=1
fi

if ensure_uv; then
  info "uv: $(uv --version)"
else
  warn "uv not found. Some host-side scripts may require manual python execution."
fi

if [[ $check_failed -eq 1 ]]; then
  err "Pre-flight checks failed. Please resolve the issues above and try again."
  exit 1
fi

info "All critical prerequisites met."

# =============================================================
header "1 / 8 – Global Settings"

TZ=$(ask_input "Timezone" "${TZ:-Asia/Ho_Chi_Minh}")
DLH_BIND_IP=$(ask_input "Bind IP (127.0.0.1 = local only)" "${DLH_BIND_IP:-127.0.0.1}")
DLH_APP_BIND_IP=$(ask_input "App/UI bind IP" "${DLH_APP_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}")
DLH_DATA_BIND_IP=$(ask_input "Data/DB bind IP" "${DLH_DATA_BIND_IP:-0.0.0.0}")
DLH_LAN_CIDR=$(ask_input "LAN CIDR for firewall rules" "${DLH_LAN_CIDR:-192.168.1.0/24}")
UFW_ALLOW_DATA_PORTS=$(ask_input "Allow data ports to LAN (true/false)" "${UFW_ALLOW_DATA_PORTS:-false}")

# =============================================================
header "2 / 8 – Docker Image Versions"

POSTGRES_IMAGE_VERSION=$(ask_input "PostgreSQL image tag" "${POSTGRES_IMAGE_VERSION:-17-alpine}")
RUSTFS_IMAGE_VERSION=$(ask_input "RustFS image tag" "${RUSTFS_IMAGE_VERSION:-latest}")
MINIO_MC_IMAGE_VERSION=$(ask_input "MinIO mc (rustfs-init) tag" "${MINIO_MC_IMAGE_VERSION:-latest}")
CLICKHOUSE_IMAGE_VERSION=$(ask_input "ClickHouse image tag" "${CLICKHOUSE_IMAGE_VERSION:-latest}")
MAGE_IMAGE_VERSION=$(ask_input "Mage image tag" "${MAGE_IMAGE_VERSION:-latest}")
SUPERSET_IMAGE_VERSION=$(ask_input "Superset image tag" "${SUPERSET_IMAGE_VERSION:-latest}")
GRAFANA_IMAGE_VERSION=$(ask_input "Grafana image tag" "${GRAFANA_IMAGE_VERSION:-latest}")

# =============================================================
header "3 / 8 – Core PostgreSQL (Admin)"

POSTGRES_DB=$(ask_input "Admin database name" "${POSTGRES_DB:-datalakehouse}")
POSTGRES_USER=$(ask_input "Admin username" "${POSTGRES_USER:-dlh_admin}")
POSTGRES_PASSWORD=$(ask_input "Admin password" "${POSTGRES_PASSWORD:-change-this-admin-password}")
SUGGESTED_PG_PORT=$(suggest_port "${DLH_POSTGRES_PORT:-25432}")
DLH_POSTGRES_PORT=$(ask_input "Host port for PostgreSQL" "$SUGGESTED_PG_PORT")

# =============================================================
header "4 / 8 – Custom Workspace (optional)"
echo "  Create an isolated PostgreSQL database / schema / user for your"
echo "  own ETL and reporting. Leave CUSTOM_DB_NAME empty to skip."

CUSTOM_DB_NAME=$(ask_input "Custom database name (blank = skip)" "${CUSTOM_DB_NAME:-dlh_custom}")
if [ -n "$CUSTOM_DB_NAME" ]; then
  CUSTOM_DB_USER=$(ask_input "Custom username" "${CUSTOM_DB_USER:-dlh_custom_user}")
  CUSTOM_DB_PASSWORD=$(ask_input "Custom password" "${CUSTOM_DB_PASSWORD:-change-this-custom-password}")
  CUSTOM_SCHEMA=$(ask_input "Custom schema name" "${CUSTOM_SCHEMA:-custom_schema}")
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

RUSTFS_ACCESS_KEY=$(ask_input "RustFS access key" "${RUSTFS_ACCESS_KEY:-rustfsadmin}")
RUSTFS_SECRET_KEY=$(ask_input "RustFS secret key" "${RUSTFS_SECRET_KEY:-rustfsadmin}")
SUGGESTED_RUSTFS_API_PORT=$(suggest_port "${DLH_RUSTFS_API_PORT:-29100}")
DLH_RUSTFS_API_PORT=$(ask_input "Host port for RustFS API" "$SUGGESTED_RUSTFS_API_PORT")
SUGGESTED_RUSTFS_CONSOLE_PORT=$(suggest_port "${DLH_RUSTFS_CONSOLE_PORT:-29101}")
DLH_RUSTFS_CONSOLE_PORT=$(ask_input "Host port for RustFS console" "$SUGGESTED_RUSTFS_CONSOLE_PORT")

# =============================================================
header "6 / 8 – ClickHouse"

CLICKHOUSE_DB=$(ask_input "ClickHouse database" "${CLICKHOUSE_DB:-analytics}")
CLICKHOUSE_USER=$(ask_input "ClickHouse user" "${CLICKHOUSE_USER:-default}")
CLICKHOUSE_PASSWORD=$(ask_input "ClickHouse password (blank ok)" "${CLICKHOUSE_PASSWORD:-}")
SUGGESTED_CH_HTTP_PORT=$(suggest_port "${DLH_CLICKHOUSE_HTTP_PORT:-28123}")
DLH_CLICKHOUSE_HTTP_PORT=$(ask_input "Host port – ClickHouse HTTP" "$SUGGESTED_CH_HTTP_PORT")
SUGGESTED_CH_TCP_PORT=$(suggest_port "${DLH_CLICKHOUSE_TCP_PORT:-29000}")
DLH_CLICKHOUSE_TCP_PORT=$(ask_input "Host port – ClickHouse TCP" "$SUGGESTED_CH_TCP_PORT")

# =============================================================
header "7 / 8 – App Service Passwords"
echo "  (Mage, Superset, Grafana metadata DB passwords)"

MAGE_DB_PASSWORD=$(ask_input "Mage DB password" "${MAGE_DB_PASSWORD:-change-this-mage-password}")
MAGE_DEFAULT_OWNER_EMAIL=$(ask_input "Mage default owner email" "${MAGE_DEFAULT_OWNER_EMAIL:-admin@admin.com}")
MAGE_DEFAULT_OWNER_USERNAME=$(ask_input "Mage default owner username" "${MAGE_DEFAULT_OWNER_USERNAME:-admin}")
MAGE_DEFAULT_OWNER_PASSWORD=$(ask_input "Mage default owner password" "${MAGE_DEFAULT_OWNER_PASSWORD:-admin}")
SUPERSET_SECRET_KEY=$(ask_input "Superset secret key" "${SUPERSET_SECRET_KEY:-replace-this-secret}")
SUPERSET_DB_PASSWORD=$(ask_input "Superset DB password" "${SUPERSET_DB_PASSWORD:-change-this-superset-db-password}")
SUPERSET_ADMIN_USER=$(ask_input "Superset admin user" "${SUPERSET_ADMIN_USER:-admin}")
SUPERSET_ADMIN_PASSWORD=$(ask_input "Superset admin password" "${SUPERSET_ADMIN_PASSWORD:-admin}")
GRAFANA_DB_PASSWORD=$(ask_input "Grafana DB password" "${GRAFANA_DB_PASSWORD:-change-this-grafana-db-password}")
GRAFANA_ADMIN_USER=$(ask_input "Grafana admin user" "${GRAFANA_ADMIN_USER:-admin}")
GRAFANA_ADMIN_PASSWORD=$(ask_input "Grafana admin password" "${GRAFANA_ADMIN_PASSWORD:-admin}")

# =============================================================
header "8 / 8 – Port Assignments"

SUGGESTED_MAGE_PORT=$(suggest_port "${DLH_MAGE_PORT:-26789}")
DLH_MAGE_PORT=$(ask_input "Host port – Mage" "$SUGGESTED_MAGE_PORT")
SUGGESTED_SUPERSET_PORT=$(suggest_port "${DLH_SUPERSET_PORT:-28088}")
DLH_SUPERSET_PORT=$(ask_input "Host port – Superset" "$SUGGESTED_SUPERSET_PORT")
SUGGESTED_GRAFANA_PORT=$(suggest_port "${DLH_GRAFANA_PORT:-23001}")
DLH_GRAFANA_PORT=$(ask_input "Host port – Grafana" "$SUGGESTED_GRAFANA_PORT")


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
SUPERSET_IMAGE_VERSION=${SUPERSET_IMAGE_VERSION}
GRAFANA_IMAGE_VERSION=${GRAFANA_IMAGE_VERSION}
REDIS_STACK_IMAGE_VERSION=${REDIS_STACK_IMAGE_VERSION:-latest}
AUTHENTIK_IMAGE_VERSION=${AUTHENTIK_IMAGE_VERSION:-2026.2.1}

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
RUSTFS_BUCKET=general
RUSTFS_BRONZE_BUCKET=bronze
RUSTFS_SILVER_BUCKET=silver
RUSTFS_GOLD_BUCKET=gold

# ─ ClickHouse (Analytics Data Warehouse) ───────────────────
CLICKHOUSE_DB=${CLICKHOUSE_DB}
CLICKHOUSE_USER=${CLICKHOUSE_USER}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
DLH_CLICKHOUSE_HTTP_PORT=${DLH_CLICKHOUSE_HTTP_PORT}
DLH_CLICKHOUSE_TCP_PORT=${DLH_CLICKHOUSE_TCP_PORT}

# ─ Redis (Shared Cache / Queue Backend) ───────────────────
REDIS_HOST=dlh-redis
REDIS_BIND_IP=${REDIS_BIND_IP:-127.0.0.1}
DLH_REDIS_PORT=${DLH_REDIS_PORT:-26379}
REDIS_PASSWORD=${REDIS_PASSWORD:-change-this-redis-password}
REDIS_PROTECTED_MODE=${REDIS_PROTECTED_MODE:-yes}
REDIS_APPENDONLY=${REDIS_APPENDONLY:-yes}
REDIS_MAXMEMORY=${REDIS_MAXMEMORY:-512mb}
REDIS_MAXMEMORY_POLICY=${REDIS_MAXMEMORY_POLICY:-allkeys-lru}
REDIS_VM_OVERCOMMIT_MEMORY=${REDIS_VM_OVERCOMMIT_MEMORY:-1}
REDIS_STACK_IMAGE_VERSION=${REDIS_STACK_IMAGE_VERSION:-latest}
DLH_REDIS_GUI_PORT=${DLH_REDIS_GUI_PORT:-25540}
REDIS_AUTHENTIK_DB=${REDIS_AUTHENTIK_DB:-1}
SUPERSET_REDIS_CACHE_DB=${SUPERSET_REDIS_CACHE_DB:-2}
SUPERSET_REDIS_RESULTS_DB=${SUPERSET_REDIS_RESULTS_DB:-3}

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
SUPERSET_PIP_REQUIREMENTS=${SUPERSET_PIP_REQUIREMENTS:-psycopg2-binary==2.9.9 clickhouse-connect==0.8.3}

# ─ Authentik (Identity Provider) ───────────────────────────
DLH_AUTHENTIK_PORT=${DLH_AUTHENTIK_PORT:-29090}
AUTHENTIK_SECRET_KEY=${AUTHENTIK_SECRET_KEY:-replace-this-with-a-long-random-secret}
AUTHENTIK_DB_NAME=${AUTHENTIK_DB_NAME:-dlh_authentik}
AUTHENTIK_DB_USER=${AUTHENTIK_DB_USER:-dlh_authentik_user}
AUTHENTIK_DB_PASSWORD=${AUTHENTIK_DB_PASSWORD:-change-this-authentik-db-password}
AUTHENTIK_BOOTSTRAP_EMAIL=${AUTHENTIK_BOOTSTRAP_EMAIL:-admin@authentik.local}
AUTHENTIK_BOOTSTRAP_PASSWORD=${AUTHENTIK_BOOTSTRAP_PASSWORD:-admin}
AUTHENTIK_BOOTSTRAP_TOKEN=${AUTHENTIK_BOOTSTRAP_TOKEN:-}

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
echo "    Superset   : http://localhost:${DLH_SUPERSET_PORT}"
echo "    Authentik  : http://localhost:${DLH_AUTHENTIK_PORT:-29090}"
echo "    Grafana    : http://localhost:${DLH_GRAFANA_PORT}"
echo "    Redis      : localhost:${DLH_REDIS_PORT:-26379}"
echo "    Redis GUI  : http://localhost:${DLH_REDIS_GUI_PORT:-25540}"

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

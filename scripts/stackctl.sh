#!/usr/bin/env bash
set -euo pipefail
set -E

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="$REPO_ROOT/.env"

# Source environment library
if [[ -f "$REPO_ROOT/scripts/lib_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/scripts/lib_env.sh"
else
  echo "Error: scripts/lib_env.sh not found" >&2
  exit 1
fi

error_handler() {
  local exit_code=$?
  local line_number=$1
  err "Error on line $line_number executing '$BASH_COMMAND' (exit: $exit_code)"
  exit "$exit_code"
}

trap 'error_handler $LINENO' ERR

usage() {
  cat <<'EOF'
Usage:
  bash scripts/stackctl.sh up                           Start all services
  bash scripts/stackctl.sh down                         Stop all services
  bash scripts/stackctl.sh redeploy [--with-etl] [--safe] Redeploy (stop + start)
  bash scripts/stackctl.sh status                       Show service status

  bash scripts/stackctl.sh health                       Detailed health checks
  bash scripts/stackctl.sh diagnose                     Run advanced troubleshooting
  bash scripts/stackctl.sh logs [SERVICE]               Show service logs (use 'all' for all)

  bash scripts/stackctl.sh reset [--hard]               Clean state (containers) --hard: with volumes
  bash scripts/stackctl.sh check-env                    Validate environment variables
  bash scripts/stackctl.sh check-system                 Quick system health overview
  bash scripts/stackctl.sh sync-env                     Update environment interactively
  bash scripts/stackctl.sh validate-env                 Strict validation with suggestions
  bash scripts/stackctl.sh inspect [SERVICE]            Detailed service information

Options:
  --with-etl  Run ETL/dashboard orchestration after redeploy.
  --safe      Run ClickHouse backup before redeploy.
  -h, --help  Show this help.


Examples:
  bash scripts/stackctl.sh logs dlh-mage                # View Mage ETL logs
  bash scripts/stackctl.sh logs all                     # View all service logs
  bash scripts/stackctl.sh health                       # Full system health check
  bash scripts/stackctl.sh reset --hard                 # Complete clean slate
  bash scripts/stackctl.sh redeploy --with-etl          # Redeploy and run ETL
EOF
}

# ── Command Handlers ────────────────────────────────────────

compose_up() {
  info "Ensuring Docker network web_network exists..."
  if ! docker network inspect web_network >/dev/null 2>&1; then
    docker network create web_network >/dev/null
  fi

  info "Starting stack with docker compose up -d..."
  (cd "$REPO_ROOT" && docker compose up -d)
}

compose_down() {
  info "Stopping stack..."
  (cd "$REPO_ROOT" && docker compose down)

  info "Attempting to clean firewall rules (non-blocking)..."
  bash "$REPO_ROOT/scripts/setup_ufw_docker.sh" --remove || warn "Firewall cleanup skipped or failed."
}

redeploy() {
  local with_etl="$1"
  local safe_mode="$2"

  if [[ "$safe_mode" == "true" ]]; then
    header "Safe Redeploy: Triggering Pre-deployment Backup"
    if command -v uv >/dev/null 2>&1; then
      info "Running maintenance_tasks.py backup..."
      (cd "$REPO_ROOT" && uv run python scripts/maintenance_tasks.py) || warn "Backup failed, continuing with redeploy..."
    else
      warn "uv not found, skipping pre-deployment backup."
    fi
  fi

  compose_down || true
  compose_up


  if [[ "$with_etl" == "true" ]]; then
    if command -v uv >/dev/null 2>&1; then
      info "Running ETL and dashboard orchestration..."
      (cd "$REPO_ROOT" && uv run python scripts/run_etl_and_dashboard.py --auto)
    else
      warn "uv is not installed; skipping ETL/dashboard orchestration."
    fi
  fi

  check_system
}

status() {
  (cd "$REPO_ROOT" && docker compose ps)
}

print_env_value() {
  local key="$1"
  local value="${!key:-<unset>}"
  printf '%-28s %s\n' "$key:" "$value"
}

check_env() {
  load_env_file
  echo "Environment snapshot:"
  for key in \
    TZ DLH_BIND_IP DLH_APP_BIND_IP DLH_DATA_BIND_IP DLH_LAN_CIDR UFW_ALLOW_DATA_PORTS \
    POSTGRES_DB POSTGRES_USER POSTGRES_HOST \
    CUSTOM_DB_NAME CUSTOM_DB_USER CUSTOM_SCHEMA \
    SOURCE_DB_NAME SOURCE_DB_USER SOURCE_SCHEMA SOURCE_TABLE SOURCE_TABLE_CANDIDATES \
    MAGE_DEFAULT_OWNER_EMAIL MAGE_DEFAULT_OWNER_USERNAME \
    CLICKHOUSE_DB CLICKHOUSE_USER DLH_CLICKHOUSE_HTTP_PORT DLH_CLICKHOUSE_TCP_PORT \
    DLH_RUSTFS_API_PORT DLH_RUSTFS_CONSOLE_PORT DLH_MAGE_PORT DLH_SUPERSET_PORT DLH_GRAFANA_PORT \
    SUPERSET_ADMIN_USER SUPERSET_PREFERRED_URL_SCHEME
  do
    print_env_value "$key"
  done

  local problems=0
  if [[ -n "${DLH_LAN_CIDR:-}" ]] && ! is_valid_cidr "${DLH_LAN_CIDR:-}"; then
    err "Invalid DLH_LAN_CIDR: ${DLH_LAN_CIDR:-}"
    problems=$((problems + 1))
  fi

  for key in DLH_POSTGRES_PORT DLH_RUSTFS_API_PORT DLH_RUSTFS_CONSOLE_PORT DLH_CLICKHOUSE_HTTP_PORT DLH_CLICKHOUSE_TCP_PORT DLH_MAGE_PORT DLH_SUPERSET_PORT DLH_GRAFANA_PORT; do
    value="${!key:-}"
    if [[ -n "$value" ]] && ! is_valid_port "$value"; then
      err "Invalid $key: $value"
      problems=$((problems + 1))
    fi
  done

  if [[ "$problems" -eq 0 ]]; then
    info "Environment variables look valid."
  else
    exit 1
  fi
}

sync_env() {
  load_env_file
  echo "Update mutable environment values. Leave blank to keep the current value."

  local bind_ip app_bind_ip data_bind_ip lan_cidr allow_data_ports postgres_port rustfs_api_port rustfs_console_port clickhouse_http_port clickhouse_tcp_port mage_port superset_port grafana_port superset_scheme mage_owner_email mage_owner_username mage_owner_password
  bind_ip="$(ask_input "Bind IP" "${DLH_BIND_IP:-127.0.0.1}")"
  app_bind_ip="$(ask_input "App/UI bind IP" "${DLH_APP_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}")"
  data_bind_ip="$(ask_input "Data/DB bind IP" "${DLH_DATA_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}")"
  lan_cidr="$(ask_input "LAN CIDR" "${DLH_LAN_CIDR:-192.168.1.0/24}")"
  allow_data_ports="$(ask_input "Open data ports to LAN?" "${UFW_ALLOW_DATA_PORTS:-false}")"
  postgres_port="$(ask_input "PostgreSQL port" "${DLH_POSTGRES_PORT:-25432}")"
  rustfs_api_port="$(ask_input "RustFS API port" "${DLH_RUSTFS_API_PORT:-29100}")"
  rustfs_console_port="$(ask_input "RustFS console port" "${DLH_RUSTFS_CONSOLE_PORT:-29101}")"
  clickhouse_http_port="$(ask_input "ClickHouse HTTP port" "${DLH_CLICKHOUSE_HTTP_PORT:-28123}")"
  clickhouse_tcp_port="$(ask_input "ClickHouse TCP port" "${DLH_CLICKHOUSE_TCP_PORT:-29000}")"
  mage_port="$(ask_input "Mage port" "${DLH_MAGE_PORT:-26789}")"
  mage_owner_email="$(ask_input "Mage default owner email" "${MAGE_DEFAULT_OWNER_EMAIL:-admin@admin.com}")"
  mage_owner_username="$(ask_input "Mage default owner username" "${MAGE_DEFAULT_OWNER_USERNAME:-admin}")"
  mage_owner_password="$(ask_input "Mage default owner password" "${MAGE_DEFAULT_OWNER_PASSWORD:-admin}")"
  superset_port="$(ask_input "Superset port" "${DLH_SUPERSET_PORT:-28088}")"
  grafana_port="$(ask_input "Grafana port" "${DLH_GRAFANA_PORT:-23001}")"
  superset_scheme="$(ask_input "Superset URL scheme" "${SUPERSET_PREFERRED_URL_SCHEME:-http}")"

  upsert_env_var "DLH_BIND_IP" "$bind_ip"
  upsert_env_var "DLH_APP_BIND_IP" "$app_bind_ip"
  upsert_env_var "DLH_DATA_BIND_IP" "$data_bind_ip"
  upsert_env_var "DLH_LAN_CIDR" "$lan_cidr"
  upsert_env_var "UFW_ALLOW_DATA_PORTS" "$allow_data_ports"
  upsert_env_var "DLH_POSTGRES_PORT" "$postgres_port"
  upsert_env_var "DLH_RUSTFS_API_PORT" "$rustfs_api_port"
  upsert_env_var "DLH_RUSTFS_CONSOLE_PORT" "$rustfs_console_port"
  upsert_env_var "DLH_CLICKHOUSE_HTTP_PORT" "$clickhouse_http_port"
  upsert_env_var "DLH_CLICKHOUSE_TCP_PORT" "$clickhouse_tcp_port"
  upsert_env_var "DLH_MAGE_PORT" "$mage_port"
  upsert_env_var "MAGE_DEFAULT_OWNER_EMAIL" "$mage_owner_email"
  upsert_env_var "MAGE_DEFAULT_OWNER_USERNAME" "$mage_owner_username"
  upsert_env_var "MAGE_DEFAULT_OWNER_PASSWORD" "$mage_owner_password"
  upsert_env_var "DLH_SUPERSET_PORT" "$superset_port"
  upsert_env_var "DLH_GRAFANA_PORT" "$grafana_port"
  upsert_env_var "SUPERSET_PREFERRED_URL_SCHEME" "$superset_scheme"

  info ".env updated."
}

check_system() {
  (cd "$REPO_ROOT" && docker compose ps)
  echo
  echo "Health checks:"

  local services=(
    "dlh-postgres:${DLH_POSTGRES_PORT:-25432}"
    "dlh-rustfs:${DLH_RUSTFS_API_PORT:-29100}"
    "dlh-clickhouse:${DLH_CLICKHOUSE_HTTP_PORT:-28123}"
    "dlh-mage:${DLH_MAGE_PORT:-26789}"
    "dlh-superset:${DLH_SUPERSET_PORT:-28088}"
    "dlh-grafana:${DLH_GRAFANA_PORT:-23001}"
  )

  local service host port
  for service in "${services[@]}"; do
    host="${service%%:*}"
    port="${service##*:}"
    printf '  %s -> http://127.0.0.1:%s\n' "$host" "$port"
  done

  if command -v uv >/dev/null 2>&1; then
    echo
    info "Running architecture verification script..."
    (cd "$REPO_ROOT" && uv run python scripts/verify_lakehouse_architecture.py)
  else
    warn "uv is not installed; skipping verify_lakehouse_architecture.py."
  fi
}

# Enhanced health check with detailed diagnostics
health() {
  load_env_file
  header "System Health Check"
  
  echo "=== Docker Compose Status ==="
  (cd "$REPO_ROOT" && docker compose ps)
  echo

  echo "=== Service Health Endpoints ==="
  local services=(
    "dlh-postgres:5432:PostgreSQL"
    "dlh-rustfs:${DLH_RUSTFS_API_PORT:-29100}:RustFS API"
    "dlh-clickhouse:${DLH_CLICKHOUSE_HTTP_PORT:-28123}:ClickHouse"
    "dlh-mage:${DLH_MAGE_PORT:-26789}:Mage"
    "dlh-superset:${DLH_SUPERSET_PORT:-28088}:Superset"
    "dlh-grafana:${DLH_GRAFANA_PORT:-23001}:Grafana"
  )

  for service_info in "${services[@]}"; do
    local name="${service_info%%:*}"
    local port="${service_info#*:}"
    port="${port%%:*}"
    local label="${service_info##*:}"
    
    if docker exec "$name" true 2>/dev/null; then
      printf "  ✓ %-20s (http://localhost:%-5s) [RUNNING]\n" "$label" "$port"
    else
      printf "  ✗ %-20s (http://localhost:%-5s) [STOPPED/ERROR]\n" "$label" "$port"
    fi
  done
  echo

  echo "=== Disk Usage ==="
  docker system df
  echo

  if command -v uv >/dev/null 2>&1; then
    info "Running full architecture verification..."
    (cd "$REPO_ROOT" && uv run python scripts/verify_lakehouse_architecture.py) || true
  fi
}

# Advanced diagnostics for troubleshooting
diagnose() {
  load_env_file
  header "DataLakehouse Diagnostic Report"

  info "1. Checking host-side port conflicts..."
  local ports=(
    "DLH_POSTGRES_PORT:${DLH_POSTGRES_PORT:-25432}"
    "DLH_RUSTFS_API_PORT:${DLH_RUSTFS_API_PORT:-29100}"
    "DLH_RUSTFS_CONSOLE_PORT:${DLH_RUSTFS_CONSOLE_PORT:-29101}"
    "DLH_CLICKHOUSE_HTTP_PORT:${DLH_CLICKHOUSE_HTTP_PORT:-28123}"
    "DLH_CLICKHOUSE_TCP_PORT:${DLH_CLICKHOUSE_TCP_PORT:-29000}"
    "DLH_MAGE_PORT:${DLH_MAGE_PORT:-26789}"
    "DLH_SUPERSET_PORT:${DLH_SUPERSET_PORT:-28088}"
    "DLH_GRAFANA_PORT:${DLH_GRAFANA_PORT:-23001}"
  )

  for p in "${ports[@]}"; do
    local var="${p%%:*}"
    local val="${p##*:}"
    if is_port_in_use "$val"; then
      # We check if it's OUR container using it
      local container
      container=$(docker ps --format '{{.Names}}' --filter "publish=${val}")
      if [[ -n "$container" ]]; then
        info "  [OK] Port $val ($var) is used by $container"
      else
        err "  [CONFLICT] Port $val ($var) is used by an external process!"
      fi
    else
      warn "  [OFFLINE] Port $val ($var) is not listening"
    fi
  done

  echo
  info "2. Scanning logs for critical errors (last 100 lines)..."
  local errors
  errors=$(docker compose logs --tail=100 | grep -iE "error|exception|fail|refused|denied" | grep -v "DEBUG" | tail -10)
  if [[ -n "$errors" ]]; then
    err "  Found recent suspicious log entries:"
    echo "$errors" | sed 's/^/    /'
  else
    info "  No obvious critical errors found in recent logs."
  fi

  echo
  info "3. Checking Docker resources..."
  local disk_usage
  disk_usage=$(docker system df --format "{{.Type}}: {{.Size}} ({{.Reclaimable}} reclaimable)")
  echo "$disk_usage" | sed 's/^/    /'

  echo
  info "4. Validating network..."
  if docker network inspect web_network >/dev/null 2>&1; then
    info "  [OK] web_network exists"
  else
    err "  [MISSING] web_network is missing!"
  fi
}


logs_cmd() {
  local service="${1:-all}"
  
  if [[ "$service" == "all" ]]; then
    info "Showing last 50 lines from all services (use Ctrl+C to stop)..."
    (cd "$REPO_ROOT" && docker compose logs --tail=50 -f)
  else
    info "Showing logs for service: $service"
    (cd "$REPO_ROOT" && docker compose logs --tail=100 -f "$service")
  fi
}

inspect() {
  local service="${1:-}"
  
  if [[ -z "$service" ]]; then
    echo "Available services for inspection:"
    (cd "$REPO_ROOT" && docker compose config --services)
    echo
    echo "Usage: bash scripts/stackctl.sh inspect <service>"
    return 1
  fi

  echo "=== Service: $service ==="
  echo
  echo "Container Info:"
  docker inspect "$service" 2>/dev/null | head -50 || warn "Service $service not found or not running"
  echo
  echo "Recent Logs (last 30 lines):"
  (cd "$REPO_ROOT" && docker compose logs --tail=30 "$service") || true
}

reset() {
  local hard="${1:-}"
  
  echo "=== Stack Reset ==="
  
  if [[ "$hard" == "--hard" ]]; then
    warn "HARD RESET: This will remove containers AND volumes. Press Ctrl+C to cancel."
    read -r -p "Type 'yes' to confirm hard reset: " confirm
    if [[ "$confirm" != "yes" ]]; then
      info "Reset cancelled."
      return 0
    fi
    
    info "Stopping and removing all containers..."
    (cd "$REPO_ROOT" && docker compose down -v) || true
    
    info "Removing network web_network..."
    docker network rm web_network 2>/dev/null || true
    
    info "Hard reset complete. All volumes and containers removed."
  else
    info "Soft reset: Stopping and removing containers (keeping volumes)..."
    (cd "$REPO_ROOT" && docker compose down) || true
    
    info "Removing network web_network..."
    docker network rm web_network 2>/dev/null || true
    
    info "Soft reset complete. To restore, run: bash scripts/stackctl.sh up"
  fi
}

validate_env() {
  load_env_file
  local issues=0

  echo "=== Strict Environment Validation ==="
  echo

  local critical_vars=(
    "DLH_BIND_IP"
    "DLH_APP_BIND_IP"
    "DLH_DATA_BIND_IP"
    "DLH_LAN_CIDR"
    "POSTGRES_DB"
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "CLICKHOUSE_DB"
    "CLICKHOUSE_USER"
    "CLICKHOUSE_PASSWORD"
  )

  for var in "${critical_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      err "Missing critical variable: $var"
      issues=$((issues + 1))
    fi
  done

  echo
  info "Checking port uniqueness..."
  local ports=(
    "DLH_POSTGRES_PORT"
    "DLH_RUSTFS_API_PORT"
    "DLH_RUSTFS_CONSOLE_PORT"
    "DLH_CLICKHOUSE_HTTP_PORT"
    "DLH_CLICKHOUSE_TCP_PORT"
    "DLH_MAGE_PORT"
    "DLH_SUPERSET_PORT"
    "DLH_GRAFANA_PORT"
  )

  local port_values=()
  for port_var in "${ports[@]}"; do
    local port="${!port_var:-}"
    if [[ -n "$port" ]]; then
      for existing_port in "${port_values[@]}"; do
        if [[ "$port" == "$existing_port" ]]; then
          err "Duplicate port: $port_var=$port"
          issues=$((issues + 1))
        fi
      done
      port_values+=("$port")
    fi
  done

  if ! is_valid_cidr "${DLH_LAN_CIDR:-}"; then
    err "Invalid CIDR format: DLH_LAN_CIDR=${DLH_LAN_CIDR:-}"
    issues=$((issues + 1))
  else
    info "CIDR format valid: ${DLH_LAN_CIDR}"
  fi

  if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed or not in PATH"
    issues=$((issues + 1))
  else
    info "Docker found: $(docker --version)"
  fi

  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose is not available"
    issues=$((issues + 1))
  else
    info "Docker Compose found: $(docker compose version | head -1)"
  fi

  if ! command -v uv >/dev/null 2>&1; then
    warn "uv is not installed (optional but recommended for Python script execution)"
  else
    info "uv found: $(uv --version)"
  fi

  echo
  if [[ $issues -eq 0 ]]; then
    info "✓ All validation checks passed!"
  else
    err "✗ Found $issues validation issue(s)."
    return 1
  fi
}

# ── Main ────────────────────────────────────────────────────

main() {
  local command="${1:-}"
  local with_etl="false"
  local safe_mode="false"

  case "$command" in
    up)
      compose_up
      ;;
    down)
      compose_down
      ;;
    redeploy)
      shift || true
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --with-etl)
            with_etl="true"
            shift
            ;;
          --safe)
            safe_mode="true"
            shift
            ;;
          -h|--help)
            usage
            exit 0
            ;;
          *)
            err "Unknown argument for redeploy: $1"
            usage
            exit 1
            ;;
        esac
      done
      redeploy "$with_etl" "$safe_mode"
      ;;
    status)
      status
      ;;
    health)
      health
      ;;
    diagnose)
      diagnose
      ;;
    logs)

      shift || true
      logs_cmd "$@"
      ;;
    inspect)
      shift || true
      inspect "$@"
      ;;
    reset)
      shift || true
      reset "$@"
      ;;
    check-env)
      check_env
      ;;
    check-system)
      check_system
      ;;
    validate-env)
      validate_env
      ;;
    sync-env)
      sync_env
      ;;
    -h|--help|"")
      usage
      ;;
    *)
      err "Unknown command: $command"
      usage
      exit 1
      ;;
  esac
}

main "$@"

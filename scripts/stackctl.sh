#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/stackctl.sh up                           Start all services
  bash scripts/stackctl.sh down                         Stop all services
  bash scripts/stackctl.sh redeploy [--with-etl]        Redeploy (stop + start)
  bash scripts/stackctl.sh status                       Show service status
  bash scripts/stackctl.sh health                       Detailed health checks
  bash scripts/stackctl.sh logs [SERVICE]               Show service logs (use 'all' for all)
  bash scripts/stackctl.sh reset [--hard]               Clean state (containers) --hard: with volumes
  bash scripts/stackctl.sh check-env                    Validate environment variables
  bash scripts/stackctl.sh sync-env                     Update environment interactively
  bash scripts/stackctl.sh validate-env                 Strict validation with suggestions
  bash scripts/stackctl.sh inspect [SERVICE]            Detailed service information

Options:
  --with-etl  Run ETL/dashboard orchestration after redeploy.
  -h, --help  Show this help.

Examples:
  bash scripts/stackctl.sh logs dlh-mage                # View Mage ETL logs
  bash scripts/stackctl.sh logs all                     # View all service logs
  bash scripts/stackctl.sh health                       # Full system health check
  bash scripts/stackctl.sh reset --hard                 # Complete clean slate
  bash scripts/stackctl.sh redeploy --with-etl          # Redeploy and run ETL
EOF
}

info() { echo "  → $*"; }
warn() { echo "  ⚠ $*"; }
err() { echo "  ✗ $*" >&2; }

load_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a
    . "$ENV_FILE"
    set +a
  fi
}

upsert_env_var() {
  local key="$1"
  local value="$2"

  if [[ ! -f "$ENV_FILE" ]]; then
    touch "$ENV_FILE"
  fi

  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s#^${key}=.*#${key}=${value}#" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

ask_input() {
  local prompt="$1"
  local default_value="$2"
  local value
  read -r -p "$prompt [$default_value]: " value
  value="${value:-$default_value}"
  printf '%s' "$value"
}

trim_value() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

is_valid_cidr() {
  local cidr="$1"
  [[ "$cidr" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]
}

is_valid_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 ))
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
    TZ DLH_BIND_IP DLH_LAN_CIDR UFW_ALLOW_DATA_PORTS \
    POSTGRES_DB POSTGRES_USER POSTGRES_HOST \
    CUSTOM_DB_NAME CUSTOM_DB_USER CUSTOM_SCHEMA \
    SOURCE_DB_NAME SOURCE_DB_USER SOURCE_SCHEMA SOURCE_TABLE SOURCE_TABLE_CANDIDATES \
    CLICKHOUSE_DB CLICKHOUSE_USER DLH_CLICKHOUSE_HTTP_PORT DLH_CLICKHOUSE_TCP_PORT \
    DLH_RUSTFS_API_PORT DLH_RUSTFS_CONSOLE_PORT DLH_MAGE_PORT DLH_NOCODB_PORT DLH_SUPERSET_PORT DLH_GRAFANA_PORT \
    SUPERSET_ADMIN_USER SUPERSET_PREFERRED_URL_SCHEME
  do
    print_env_value "$key"
  done

  local problems=0
  if [[ -n "${DLH_LAN_CIDR:-}" ]] && ! is_valid_cidr "${DLH_LAN_CIDR:-}"; then
    err "Invalid DLH_LAN_CIDR: ${DLH_LAN_CIDR:-}"
    problems=$((problems + 1))
  fi

  for key in DLH_POSTGRES_PORT DLH_RUSTFS_API_PORT DLH_RUSTFS_CONSOLE_PORT DLH_CLICKHOUSE_HTTP_PORT DLH_CLICKHOUSE_TCP_PORT DLH_MAGE_PORT DLH_NOCODB_PORT DLH_SUPERSET_PORT DLH_GRAFANA_PORT; do
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

  local bind_ip lan_cidr allow_data_ports postgres_port rustfs_api_port rustfs_console_port clickhouse_http_port clickhouse_tcp_port mage_port nocodb_port superset_port grafana_port superset_scheme
  bind_ip="$(ask_input "Bind IP" "${DLH_BIND_IP:-127.0.0.1}")"
  lan_cidr="$(ask_input "LAN CIDR" "${DLH_LAN_CIDR:-192.168.1.0/24}")"
  allow_data_ports="$(ask_input "Open data ports to LAN?" "${UFW_ALLOW_DATA_PORTS:-false}")"
  postgres_port="$(ask_input "PostgreSQL port" "${DLH_POSTGRES_PORT:-25432}")"
  rustfs_api_port="$(ask_input "RustFS API port" "${DLH_RUSTFS_API_PORT:-29100}")"
  rustfs_console_port="$(ask_input "RustFS console port" "${DLH_RUSTFS_CONSOLE_PORT:-29101}")"
  clickhouse_http_port="$(ask_input "ClickHouse HTTP port" "${DLH_CLICKHOUSE_HTTP_PORT:-28123}")"
  clickhouse_tcp_port="$(ask_input "ClickHouse TCP port" "${DLH_CLICKHOUSE_TCP_PORT:-29000}")"
  mage_port="$(ask_input "Mage port" "${DLH_MAGE_PORT:-26789}")"
  nocodb_port="$(ask_input "NocoDB port" "${DLH_NOCODB_PORT:-28082}")"
  superset_port="$(ask_input "Superset port" "${DLH_SUPERSET_PORT:-28088}")"
  grafana_port="$(ask_input "Grafana port" "${DLH_GRAFANA_PORT:-23001}")"
  superset_scheme="$(ask_input "Superset URL scheme" "${SUPERSET_PREFERRED_URL_SCHEME:-http}")"

  upsert_env_var "DLH_BIND_IP" "$bind_ip"
  upsert_env_var "DLH_LAN_CIDR" "$lan_cidr"
  upsert_env_var "UFW_ALLOW_DATA_PORTS" "$allow_data_ports"
  upsert_env_var "DLH_POSTGRES_PORT" "$postgres_port"
  upsert_env_var "DLH_RUSTFS_API_PORT" "$rustfs_api_port"
  upsert_env_var "DLH_RUSTFS_CONSOLE_PORT" "$rustfs_console_port"
  upsert_env_var "DLH_CLICKHOUSE_HTTP_PORT" "$clickhouse_http_port"
  upsert_env_var "DLH_CLICKHOUSE_TCP_PORT" "$clickhouse_tcp_port"
  upsert_env_var "DLH_MAGE_PORT" "$mage_port"
  upsert_env_var "DLH_NOCODB_PORT" "$nocodb_port"
  upsert_env_var "DLH_SUPERSET_PORT" "$superset_port"
  upsert_env_var "DLH_GRAFANA_PORT" "$grafana_port"
  upsert_env_var "SUPERSET_PREFERRED_URL_SCHEME" "$superset_scheme"

  info ".env updated."
}

compose_up() {
  info "Ensuring Docker network web_network exists..."
  if ! docker network inspect web_network >/dev/null 2>&1; then
    docker network create web_network >/dev/null
  fi

  info "Starting stack with docker compose up -d..."
  (cd "$REPO_ROOT" && docker compose up -d)
}

compose_down() {
  info "Stopping stack and cleaning firewall rules..."
  bash "$REPO_ROOT/scripts/setup_ufw_docker.sh" --down
}

redeploy() {
  local with_etl="$1"
  compose_down || true
  compose_up

  if [[ "$with_etl" == "true" ]]; then
    if command -v uv >/dev/null 2>&1; then
      info "Running ETL and dashboard orchestration..."
      (cd "$REPO_ROOT" && uv run python scripts/run_etl_and_dashboard.py)
    else
      warn "uv is not installed; skipping ETL/dashboard orchestration."
    fi
  fi

  check_system
}

status() {
  (cd "$REPO_ROOT" && docker compose ps)
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
    "dlh-nocodb:${DLH_NOCODB_PORT:-28082}"
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
  echo "=== Docker Compose Status ==="
  (cd "$REPO_ROOT" && docker compose ps)
  echo

  echo "=== Service Health Endpoints ==="
  local services=(
    "dlh-postgres:5432:PostgreSQL"
    "dlh-rustfs:${DLH_RUSTFS_API_PORT:-29100}:RustFS API"
    "dlh-clickhouse:${DLH_CLICKHOUSE_HTTP_PORT:-28123}:ClickHouse"
    "dlh-mage:${DLH_MAGE_PORT:-26789}:Mage"
    "dlh-nocodb:${DLH_NOCODB_PORT:-28082}:NocoDB"
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

# View logs from services
logs_cmd() {
  local service="${1:-all}"
  
  if [[ "$service" == "all" ]]; then
    info "Showing last 50 lines from all services (use Ctrl+C to stop)..."
    (cd "$REPO_ROOT" && docker compose logs --tail=50 -f)
  elif [[ -z "$service" ]]; then
    info "Showing docker compose logs help..."
    (cd "$REPO_ROOT" && docker compose logs --help | head -20)
  else
    info "Showing logs for service: $service"
    (cd "$REPO_ROOT" && docker compose logs --tail=100 -f "$service")
  fi
}

# Inspect detailed service information
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

# Reset stack state (containers, optionally volumes)
reset() {
  local hard="$1"
  
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

# Strict environment validation with suggestions
validate_env() {
  load_env_file
  local issues=0

  echo "=== Strict Environment Validation ==="
  echo

  # Check critical variables
  local critical_vars=(
    "DLH_BIND_IP"
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

  # Check port uniqueness
  echo
  info "Checking port uniqueness..."
  local ports=(
    "DLH_POSTGRES_PORT"
    "DLH_RUSTFS_API_PORT"
    "DLH_RUSTFS_CONSOLE_PORT"
    "DLH_CLICKHOUSE_HTTP_PORT"
    "DLH_CLICKHOUSE_TCP_PORT"
    "DLH_MAGE_PORT"
    "DLH_NOCODB_PORT"
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

  # Check CIDR format
  if ! is_valid_cidr "${DLH_LAN_CIDR:-}"; then
    err "Invalid CIDR format: DLH_LAN_CIDR=${DLH_LAN_CIDR:-}"
    issues=$((issues + 1))
  else
    info "CIDR format valid: ${DLH_LAN_CIDR}"
  fi

  # Check if docker is installed
  if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed or not in PATH"
    issues=$((issues + 1))
  else
    info "Docker found: $(docker --version)"
  fi

  # Check if docker compose is available
  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose is not available"
    issues=$((issues + 1))
  else
    info "Docker Compose found: $(docker compose version | head -1)"
  fi

  # Check if uv is installed
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


main() {
  local command="${1:-}"
  local with_etl="false"

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
      redeploy "$with_etl"
      ;;
    status)
      status
      ;;
    health)
      health
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

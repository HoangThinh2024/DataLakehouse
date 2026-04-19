#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/setup_ufw_docker.sh [LAN_CIDR] [--interactive|--non-interactive]
  bash scripts/setup_ufw_docker.sh --remove
  bash scripts/setup_ufw_docker.sh --down

Description:
  Configure ufw-docker rules for LAN access to DataLakehouse services.
  All rules managed by this script are tagged with "datalakehouse-" prefix.

Options:
  --interactive       Prompt for values directly in script.
  --non-interactive   Use .env/CLI defaults without prompting.
  --remove            Remove all rules managed by this script.
  --down              Run `docker compose down` and then remove rules.
  --lan-cidr VALUE    Override the LAN CIDR without using a positional arg.
  --custom-ports CSV  Override custom extra ports (comma-separated).
  -h, --help          Show this help.
EOF
}

info() { echo "  → $*"; }
warn() { echo "  ⚠ $*"; }
err() { echo "  ✗ $*" >&2; }

ask_input() {
  local prompt="$1"
  local default_value="$2"
  local value
  read -r -p "$prompt [$default_value]: " value
  value="${value:-$default_value}"
  printf '%s' "$value"
}

ask_yn() {
  local prompt="$1"
  local default="${2:-n}"
  local answer
  read -r -p "$prompt [$default]: " answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy]$ ]]
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

load_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a
    . "$ENV_FILE"
    set +a
  fi
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

split_custom_ports() {
  local raw="$1"
  CUSTOM_PORTS=()
  raw="$(trim_value "$raw")"
  [[ -z "$raw" ]] && return 0

  local port
  IFS=',' read -r -a CUSTOM_PORTS <<< "$raw"
  for port in "${CUSTOM_PORTS[@]}"; do
    port="$(trim_value "$port")"
    [[ -z "$port" ]] && continue
    if ! is_valid_port "$port"; then
      err "Invalid custom port: $port"
      exit 1
    fi
  done
}

ensure_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    err "Please run this script as a normal user with sudo, not as root."
    exit 1
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    err "sudo is required."
    exit 1
  fi
}

ensure_ufw_docker() {
  if command -v ufw-docker >/dev/null 2>&1; then
    return 0
  fi

  warn "ufw-docker not found, installing helper script..."
  local tmp_file
  tmp_file="$(mktemp)"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://raw.githubusercontent.com/chaifeng/ufw-docker/master/ufw-docker -o "$tmp_file"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$tmp_file" https://raw.githubusercontent.com/chaifeng/ufw-docker/master/ufw-docker
  else
    err "Need curl or wget to install ufw-docker."
    rm -f "$tmp_file"
    exit 1
  fi

  sudo install -m 0755 "$tmp_file" /usr/local/bin/ufw-docker
  rm -f "$tmp_file"
}

run_compose_down() {
  if ! command -v docker >/dev/null 2>&1; then
    warn "docker is not installed, skipping docker compose down."
    return 0
  fi

  if ! docker compose version >/dev/null 2>&1; then
    warn "docker compose is not available, skipping stack shutdown."
    return 0
  fi

  info "Running docker compose down..."
  (cd "$REPO_ROOT" && docker compose down)
}

prepare_ports() {
  UI_PORTS=(
    "${DLH_GRAFANA_PORT:-23001}"        # Grafana UI
    "${DLH_MAGE_PORT:-26789}"           # Mage orchestration UI
    "${DLH_NOCODB_PORT:-28082}"         # NocoDB UI
    "${DLH_SUPERSET_PORT:-28088}"       # Superset analytics UI
    "${DLH_RUSTFS_CONSOLE_PORT:-29101}" # RustFS console
  )

  DATA_PORTS=(
    "${DLH_POSTGRES_PORT:-25432}"        # PostgreSQL metadata/data DB
    "${DLH_CLICKHOUSE_HTTP_PORT:-28123}" # ClickHouse HTTP endpoint
    "${DLH_CLICKHOUSE_TCP_PORT:-29000}"  # ClickHouse native TCP endpoint
    "${DLH_RUSTFS_API_PORT:-29100}"      # RustFS S3 API
  )
}

validate_config() {
  if ! is_valid_cidr "$LAN_CIDR"; then
    err "Invalid LAN CIDR: $LAN_CIDR"
    exit 1
  fi

  local port
  for port in "${UI_PORTS[@]}"; do
    if ! is_valid_port "$port"; then
      err "Invalid UI port: $port"
      exit 1
    fi
  done

  for port in "${DATA_PORTS[@]}"; do
    if ! is_valid_port "$port"; then
      err "Invalid data port: $port"
      exit 1
    fi
  done
}

ufw_rule_present() {
  local comment_tag="$1"
  sudo ufw status numbered | grep -F "${comment_tag}" >/dev/null 2>&1
}

add_lan_port_rule() {
  local port="$1"
  local comment_tag="$2"

  if ufw_rule_present "$comment_tag"; then
    info "  Rule exists: ${comment_tag} (port ${port})"
    return 0
  fi

  # Use UFW route rules restricted by LAN CIDR and tagged comments for cleanup.
  sudo ufw route allow proto tcp from "$LAN_CIDR" to any port "$port" comment "$comment_tag"
}

apply_rules() {
  info "Initializing ufw-docker..."
  sudo ufw-docker install

  echo
  echo "Managed port groups:"
  echo "  UI ports   : Grafana, Mage, NocoDB, Superset, RustFS console"
  echo "  Data ports : PostgreSQL, ClickHouse HTTP/TCP, RustFS API (optional)"
  echo

  info "Allowing UI ports from LAN CIDR $LAN_CIDR..."
  local port service_name
  for port in "${UI_PORTS[@]}"; do
    case "$port" in
      23001) service_name="grafana" ;;
      26789) service_name="mage" ;;
      28082) service_name="nocodb" ;;
      28088) service_name="superset" ;;
      29101) service_name="rustfs-console" ;;
      *) service_name="unknown" ;;
    esac
    info "  Adding rule: $service_name (port $port)"
    add_lan_port_rule "$port" "datalakehouse-ui-$service_name"
  done

  if [[ "$ALLOW_DATA_PORTS" == "true" ]]; then
    info "Allowing data service ports from LAN CIDR $LAN_CIDR..."
    for port in "${DATA_PORTS[@]}"; do
      case "$port" in
        25432) service_name="postgres" ;;
        28123) service_name="clickhouse-http" ;;
        29000) service_name="clickhouse-tcp" ;;
        29100) service_name="rustfs-api" ;;
        *) service_name="unknown" ;;
      esac
      info "  Adding rule: $service_name (port $port)"
      add_lan_port_rule "$port" "datalakehouse-data-$service_name"
    done
  else
    info "Skipping PostgreSQL/ClickHouse/RustFS API LAN exposure."
    echo "  Set UFW_ALLOW_DATA_PORTS=true in .env if you need those ports from LAN."
  fi

  if [[ ${#CUSTOM_PORTS[@]} -gt 0 ]]; then
    info "Allowing custom TCP ports from LAN CIDR $LAN_CIDR..."
    local idx=0
    for port in "${CUSTOM_PORTS[@]}"; do
      info "  Adding rule: custom-port-$idx (port $port)"
      add_lan_port_rule "$port" "datalakehouse-custom-$idx"
      idx=$((idx + 1))
    done
  fi
}

remove_rules() {
  info "Scanning for DataLakehouse-managed rules..."
  
  # Get all rules and filter by DataLakehouse prefix
  local rule_count=0
  while IFS= read -r line; do
    if [[ "$line" =~ datalakehouse- ]]; then
      echo "  $line"
      rule_count=$((rule_count + 1))
    fi
  done < <(sudo ufw status numbered)

  if [[ $rule_count -eq 0 ]]; then
    info "No DataLakehouse-managed rules found."
    return 0
  fi

  info "Found $rule_count rule(s) to remove."
  
  # Remove rules in reverse order to avoid index shifting
  local -a indices_to_remove
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*\[([0-9]+)\] ]] && [[ "$line" =~ datalakehouse- ]]; then
      indices_to_remove+=("${BASH_REMATCH[1]}")
    fi
  done < <(sudo ufw status numbered)

  # Sort indices in descending order and delete
  for idx in $(printf '%s\n' "${indices_to_remove[@]}" | sort -rn); do
    info "Removing rule #$idx..."
    echo "y" | sudo ufw delete "$idx" >/dev/null 2>&1 || warn "Failed to delete rule #$idx"
  done
}

persist_env() {
  local custom_ports_csv=""
  local port
  for port in "${CUSTOM_PORTS[@]}"; do
    port="$(trim_value "$port")"
    [[ -z "$port" ]] && continue
    if [[ -z "$custom_ports_csv" ]]; then
      custom_ports_csv="$port"
    else
      custom_ports_csv="${custom_ports_csv},${port}"
    fi
  done

  echo "Saving firewall configuration into $ENV_FILE ..."
  upsert_env_var "DLH_LAN_CIDR" "$LAN_CIDR"
  upsert_env_var "UFW_ALLOW_DATA_PORTS" "$ALLOW_DATA_PORTS"
  upsert_env_var "UFW_CUSTOM_PORTS" "$custom_ports_csv"
}

ACTION="apply"
INTERACTIVE="auto"
LAN_CIDR="${DLH_LAN_CIDR:-192.168.1.0/24}"
ALLOW_DATA_PORTS="${UFW_ALLOW_DATA_PORTS:-false}"
CUSTOM_PORTS_RAW="${UFW_CUSTOM_PORTS:-}"
CUSTOM_PORTS=()

load_env_file

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interactive)
      INTERACTIVE="true"
      shift
      ;;
    --non-interactive)
      INTERACTIVE="false"
      shift
      ;;
    --remove)
      ACTION="remove"
      INTERACTIVE="false"
      shift
      ;;
    --down)
      ACTION="down"
      INTERACTIVE="false"
      shift
      ;;
    --lan-cidr)
      shift
      [[ $# -gt 0 ]] || { err "--lan-cidr requires a value."; exit 1; }
      LAN_CIDR="$1"
      shift
      ;;
    --custom-ports)
      shift
      [[ $# -gt 0 ]] || { err "--custom-ports requires a comma-separated value."; exit 1; }
      CUSTOM_PORTS_RAW="$1"
      shift
      ;;
    --allow-data-ports)
      shift
      [[ $# -gt 0 ]] || { err "--allow-data-ports requires true or false."; exit 1; }
      ALLOW_DATA_PORTS="$1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ "$1" == */* ]] && [[ "$LAN_CIDR" == "${DLH_LAN_CIDR:-192.168.1.0/24}" ]]; then
        LAN_CIDR="$1"
        shift
      else
        err "Unknown argument: $1"
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ "$INTERACTIVE" == "auto" ]]; then
  if [[ -t 0 ]]; then
    INTERACTIVE="true"
  else
    INTERACTIVE="false"
  fi
fi

prepare_ports

if [[ -n "$CUSTOM_PORTS_RAW" ]]; then
  split_custom_ports "$CUSTOM_PORTS_RAW"
fi

if [[ "$ACTION" == "apply" && "$INTERACTIVE" == "true" ]]; then
  echo "============================================================"
  echo "  DataLakehouse - ufw-docker Configuration"
  echo "============================================================"
  LAN_CIDR="$(ask_input "LAN CIDR allowed to connect" "$LAN_CIDR")"

  if ask_yn "Open data ports (PostgreSQL/ClickHouse/RustFS API) to LAN?" "n"; then
    ALLOW_DATA_PORTS="true"
  else
    ALLOW_DATA_PORTS="false"
  fi

  if ask_yn "Add custom TCP ports (comma-separated)" "n"; then
    CUSTOM_PORTS_RAW="$(ask_input "Custom ports" "")"
    split_custom_ports "$CUSTOM_PORTS_RAW"
  else
    CUSTOM_PORTS=()
  fi

  echo
  echo "Apply firewall changes with these values?"
  echo "  LAN CIDR         : $LAN_CIDR"
  echo "  Allow data ports : $ALLOW_DATA_PORTS"
  if [[ ${#CUSTOM_PORTS[@]} -gt 0 ]]; then
    echo "  Custom ports     : ${CUSTOM_PORTS[*]}"
  fi
  if ! ask_yn "Continue" "y"; then
    echo "Cancelled by user."
    exit 0
  fi
fi

validate_config

if [[ "$ACTION" == "remove" ]]; then
  ensure_sudo
  ensure_ufw_docker
  remove_rules
  echo
  echo "UFW status summary (DataLakehouse rules):"
  sudo ufw status numbered | grep -i "datalakehouse-" || echo "  (no DataLakehouse rules found)"
  echo
  echo "Done. Managed DataLakehouse firewall rules were removed."
  exit 0
fi

if [[ "$ACTION" == "down" ]]; then
  ensure_sudo
  ensure_ufw_docker
  run_compose_down || warn "docker compose down returned a non-zero exit code; continuing with firewall cleanup."
  remove_rules
  echo
  echo "UFW status summary (DataLakehouse rules):"
  sudo ufw status numbered | grep -i "datalakehouse-" || echo "  (no DataLakehouse rules found)"
  echo
  echo "Done. Docker stack was stopped and managed firewall rules were removed."
  exit 0
fi

persist_env

echo "============================================================"
echo "  DataLakehouse - ufw-docker Setup"
echo "============================================================"
echo "LAN CIDR         : $LAN_CIDR"
echo "Allow data ports : $ALLOW_DATA_PORTS"
echo

ensure_sudo
ensure_ufw_docker
apply_rules

echo
echo "UFW status summary (DataLakehouse rules):"
sudo ufw status numbered | grep -i "datalakehouse-" || echo "  (no DataLakehouse rules found yet)"
echo
echo "Done. LAN clients in $LAN_CIDR can now access the managed DataLakehouse ports."

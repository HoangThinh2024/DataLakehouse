#!/usr/bin/env bash
# ============================================================================
# DataLakehouse – Centralized Environment & Utility Library
# ============================================================================

# Colors
if [[ -t 1 ]]; then
  readonly C_BOLD='\033[1m'
  readonly C_CYAN='\033[36m'
  readonly C_GREEN='\033[32m'
  readonly C_YELLOW='\033[33m'
  readonly C_RED='\033[31m'
  readonly C_RESET='\033[0m'
else
  readonly C_BOLD=''
  readonly C_CYAN=''
  readonly C_GREEN=''
  readonly C_YELLOW=''
  readonly C_RED=''
  readonly C_RESET=''
fi

# Logging helpers
header() { echo -e "\n${C_BOLD}${C_CYAN}=== $* ===${C_RESET}\n"; }
info()   { echo -e "  ${C_GREEN}→${C_RESET} $*"; }
warn()   { echo -e "  ${C_YELLOW}⚠${C_RESET} $*"; }
err()    { echo -e "  ${C_RED}✗${C_RESET} $*" >&2; }

# Robust .env loader
# Handles BOM, CRLF, quotes, and comments
load_env_file() {
  local env_file="${1:-$ENV_FILE}"
  if [[ -f "$env_file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      # 1. Remove BOM (Byte Order Mark) from the first line if present
      # 2. Remove CR (Carriage Return) for CRLF compatibility
      # 3. Trim leading/trailing whitespace
      line=$(echo "$line" | sed '1s/^\xEF\xBB\xBF//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      
      # Skip empty lines and comments
      [[ -z "$line" || "$line" == "#"* ]] && continue
      
      # Parse KEY=VALUE
      if [[ "$line" =~ ^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$ ]]; then
        local key="${BASH_REMATCH[1]}"
        local val="${BASH_REMATCH[2]}"
        
        # Remove surrounding quotes if they exist (both " and ')
        val="${val#\"}"
        val="${val%\"}"
        val="${val#\'}"
        val="${val%\'}"
        
        export "$key"="$val"
      fi
    done < "$env_file"
  fi
}

# Centralized function to update or add variables in .env
upsert_env_var() {
  local key="$1"
  local value="$2"
  local env_file="${3:-$ENV_FILE}"

  if [[ ! -f "$env_file" ]]; then
    touch "$env_file"
  fi

  # Use a temporary file for safer replacement
  local tmp_file
  tmp_file=$(mktemp)
  
  if grep -q "^${key}=" "$env_file"; then
    # Replace existing key. We use a different delimiter | to avoid issues with / in values
    sed "s|^${key}=.*|${key}=${value}|" "$env_file" > "$tmp_file"
  else
    # Append new key
    cat "$env_file" > "$tmp_file"
    # Ensure there's a newline before appending if the file doesn't end with one
    [[ -s "$tmp_file" && ! $(tail -c1 "$tmp_file" | wc -l) -gt 0 ]] && echo "" >> "$tmp_file"
    echo "${key}=${value}" >> "$tmp_file"
  fi
  
  mv "$tmp_file" "$env_file"
}

# Helper for interactive prompts with defaults
ask_input() {
  local prompt="$1"
  local default_value="$2"
  local value
  
  if [[ -n "$default_value" ]]; then
    read -r -p "  $prompt [${C_CYAN}${default_value}${C_RESET}]: " value
  else
    read -r -p "  $prompt (required): " value
  fi
  
  value="${value:-$default_value}"
  printf '%s' "$value"
}

# Helper for Yes/No questions
ask_yn() {
  local prompt="$1"
  local default="${2:-n}"
  local answer
  read -r -p "  $prompt [${C_CYAN}${default}${C_RESET}]: " answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy] ]]
}

# Validation: TCP Port
is_valid_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 ))
}

# Validation: IPv4 CIDR
is_valid_cidr() {
  local cidr="$1"
  [[ "$cidr" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]
}

# Check if a TCP port is in use on the host

is_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tulpn | grep -q ":${port} "
  elif command -v netstat >/dev/null 2>&1; then
    netstat -tuln | grep -q ":${port} "
  else
    # Fallback to /dev/tcp if available (bash only)
    (echo > "/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1
  fi
}

# Suggest the next available port if the requested one is taken
suggest_port() {
  local port="$1"
  while is_port_in_use "$port"; do
    port=$((port + 1))
  done
  printf '%s' "$port"
}


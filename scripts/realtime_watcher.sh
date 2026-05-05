#!/usr/bin/env bash
# Real-time Data Watcher for DataLakehouse (Docker Volume Edition)
# Monitors bronze folder inside the container and triggers Mage AI.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/dlh_watcher.lock"
PIPELINE_UUID="etl_excel_to_lakehouse"

# Source environment library for logging and .env loading
if [[ -f "$REPO_ROOT/scripts/lib_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/scripts/lib_env.sh"
else
  echo "Error: scripts/lib_env.sh not found" >&2
  exit 1
fi

# Lock file handling to prevent multiple instances
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  err "Another instance of the watcher is already running."
  exit 1
fi

header "DataLakehouse Real-time Watcher"
info "Starting Docker-aware monitor on rustfs/bronze..."
info "Pipeline: $PIPELINE_UUID"
info "Polling interval: 10s"

last_state=""

# Cleanup on exit
cleanup() {
  info "Watcher stopping..."
  rm -f "$LOCK_FILE"
  exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
  # Check if container is running first
  if ! docker ps -q --filter "name=dlh-rustfs" | grep -q . ; then
    warn "Container dlh-rustfs is not running. Waiting..."
    sleep 10
    continue
  fi

  # Check files inside the docker container
  # We use md5sum of the file list and sizes to detect changes quickly
  current_state=$(docker exec dlh-rustfs ls -lR /data/bronze 2>/dev/null | grep ".xlsx" || echo "")
  
  if [[ -n "$current_state" && "$current_state" != "$last_state" ]]; then
    if [[ -z "$last_state" ]]; then
      info "Initial state captured. Monitoring for changes..."
    else
      header "Change Detected in RustFS Bronze"
      info "Triggering Mage Pipeline: $PIPELINE_UUID ..."
      
      if docker exec dlh-mage mage run /home/src "$PIPELINE_UUID" ; then
        info "✓ Pipeline run successful."
      else
        err "✗ Pipeline run failed!"
      fi
      info "Waiting for next change..."
    fi
    last_state="$current_state"
  fi
  
  sleep 10
done

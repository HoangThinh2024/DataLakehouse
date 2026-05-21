#!/usr/bin/env bash
# Real-time Data Watcher & Ingester for DataLakehouse
# Monitors S3 bronze bucket recursively and triggers Mage AI pipelines.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/dlh_watcher.lock"
PIPELINE_EXCEL="etl_excel_to_lakehouse"
PIPELINE_CSV="etl_csv_upload_to_reporting"

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

header "DataLakehouse Real-time S3 Event Watcher"
info "Monitoring S3:    dlh-rustfs (bronze bucket, recursive)"
info "Polling interval: 10s"

last_s3_state=""
last_excel_state=""
last_csv_state=""

# Cleanup on exit
cleanup() {
  info "Watcher stopping..."
  rm -f "$LOCK_FILE"
  exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
  # --- S3 MONITORING & PIPELINE TRIGGER ---
  if ! docker ps -q --filter "name=dlh-rustfs" | grep -q . ; then
    warn "Container dlh-rustfs is not running. Skipping S3 check..."
    sleep 10
    continue
  fi

  # Detect changes in S3 Bronze recursively for Excel files (monitoring xl.meta within .xlsx folders)
  current_excel_state=$(docker exec dlh-rustfs find /data/bronze -path "*.xlsx/xl.meta" 2>/dev/null | sort | xargs -I {} docker exec dlh-rustfs stat -c "%n %s %Y" {} 2>/dev/null || echo "")
  # Detect changes in S3 Bronze recursively for CSV files (monitoring xl.meta within .csv folders)
  current_csv_state=$(docker exec dlh-rustfs find /data/bronze -path "*.csv/xl.meta" 2>/dev/null | sort | xargs -I {} docker exec dlh-rustfs stat -c "%n %s %Y" {} 2>/dev/null || echo "")
  
  current_s3_state="${current_excel_state}${current_csv_state}"

  if [[ -n "$current_s3_state" && "$current_s3_state" != "$last_s3_state" ]]; then
    if [[ -z "$last_s3_state" ]]; then
      info "Initial S3 state captured. Monitoring for changes..."
    else
      header "Change Detected in RustFS Bronze"
      
      # Trigger Excel pipeline if Excel files changed
      if [[ "$current_excel_state" != "$last_excel_state" ]]; then
        info "Triggering Mage Pipeline: $PIPELINE_EXCEL ..."
        docker exec dlh-mage mage run /home/src "$PIPELINE_EXCEL" || err "✗ $PIPELINE_EXCEL failed!"
      fi

      # Trigger CSV pipeline if CSV files changed
      if [[ "$current_csv_state" != "$last_csv_state" ]]; then
        info "Triggering Mage Pipeline: $PIPELINE_CSV ..."
        docker exec dlh-mage mage run /home/src "$PIPELINE_CSV" || err "✗ $PIPELINE_CSV failed!"
      fi
    fi
    last_s3_state="$current_s3_state"
    last_excel_state="$current_excel_state"
    last_csv_state="$current_csv_state"
  fi
  
  sleep 10
done

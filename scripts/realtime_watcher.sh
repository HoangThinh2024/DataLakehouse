#!/usr/bin/env bash
# Real-time Data Watcher & Ingester for DataLakehouse
# 1. Monitors mage/bronze_local for new files and ingests them to S3.
# 2. Monitors S3 bronze bucket and triggers Mage AI pipelines.

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

header "DataLakehouse Real-time Watcher & Ingester"
info "Monitoring local: mage/bronze_local/"
info "Monitoring S3:    dlh-rustfs (bronze bucket)"
info "Polling interval: 10s"

last_s3_state=""

# Cleanup on exit
cleanup() {
  info "Watcher stopping..."
  rm -f "$LOCK_FILE"
  exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
  # --- PHASE 1: LOCAL INGESTION ---
  # Check if there are any .xlsx or .csv files in mage/bronze_local
  if ls "$REPO_ROOT/mage/bronze_local/"*.xlsx "$REPO_ROOT/mage/bronze_local/"*.csv 1>/dev/null 2>&1; then
    info "New local files detected. Starting ingestion to S3 Bronze..."
    if uv run --with boto3 --with python-dotenv python "$REPO_ROOT/scripts/ingest_to_bronze.py"; then
      info "✓ Local ingestion complete."
    else
      err "✗ Local ingestion failed!"
    fi
  fi

  # --- PHASE 2: S3 MONITORING & PIPELINE TRIGGER ---
  if ! docker ps -q --filter "name=dlh-rustfs" | grep -q . ; then
    warn "Container dlh-rustfs is not running. Skipping S3 check..."
    sleep 10
    continue
  fi

  # Detect changes in S3 Bronze (Excel)
  current_excel_state=$(docker exec dlh-rustfs ls -lR /data/bronze/excel_upload 2>/dev/null | grep ".xlsx" || echo "")
  # Detect changes in S3 Bronze (CSV)
  current_csv_state=$(docker exec dlh-rustfs ls -lR /data/bronze/csv_upload 2>/dev/null | grep ".csv" || echo "")
  
  current_s3_state="${current_excel_state}${current_csv_state}"

  if [[ -n "$current_s3_state" && "$current_s3_state" != "$last_s3_state" ]]; then
    if [[ -z "$last_s3_state" ]]; then
      info "Initial S3 state captured. Monitoring for changes..."
    else
      header "Change Detected in RustFS Bronze"
      
      # Trigger Excel pipeline if Excel files changed
      if [[ "$current_excel_state" != *"${last_s3_state}"* ]]; then
        info "Triggering Mage Pipeline: $PIPELINE_EXCEL ..."
        docker exec dlh-mage mage run /home/src "$PIPELINE_EXCEL" || err "✗ $PIPELINE_EXCEL failed!"
      fi

      # Trigger CSV pipeline if CSV files changed
      if [[ "$current_csv_state" != *"${last_s3_state}"* ]]; then
        info "Triggering Mage Pipeline: $PIPELINE_CSV ..."
        docker exec dlh-mage mage run /home/src "$PIPELINE_CSV" || err "✗ $PIPELINE_CSV failed!"
      fi
    fi
    last_s3_state="$current_s3_state"
  fi
  
  sleep 10
done

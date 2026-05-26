#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:-}"
TARGET_PARENT="${2:-$HOME}"
TARGET_DIR="${TARGET_PARENT}/DataLakehouse"

if [[ -z "${ARCHIVE_PATH}" ]]; then
  echo "Usage: $0 /path/to/DataLakehouse_backup_YYYYMMDD_HHMM.tar.gz [target_parent_dir]"
  exit 1
fi

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  echo "Archive not found: ${ARCHIVE_PATH}"
  exit 1
fi

mkdir -p "${TARGET_PARENT}"
tar -xzf "${ARCHIVE_PATH}" -C "${TARGET_PARENT}"

# Fix permissions for common services (adjust if your images/users differ)
if [[ -d "${TARGET_DIR}/data" ]]; then
  sudo chown -R 999:999 "${TARGET_DIR}/data/postgres" 2>/dev/null || true
  sudo chown -R 101:101 "${TARGET_DIR}/data/redpanda" 2>/dev/null || true
  sudo chown -R 65534:65534 "${TARGET_DIR}/data/prometheus" 2>/dev/null || true
  sudo chown -R 472:0 "${TARGET_DIR}/data/grafana" 2>/dev/null || true
  sudo chown -R 1000:1000 "${TARGET_DIR}/data/superset" 2>/dev/null || true
  sudo chown -R 0:0 "${TARGET_DIR}/data/dockhand" "${TARGET_DIR}/data/cloudbeaver" 2>/dev/null || true
fi

echo "Restore complete at: ${TARGET_DIR}"
echo "Next:"
echo "  cd ${TARGET_DIR}"
echo "  docker compose up -d"

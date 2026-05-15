#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M)"
ARCHIVE_NAME="DataLakehouse_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${OUT_DIR}/${ARCHIVE_NAME}"

mkdir -p "${OUT_DIR}"

# Stop stack to keep data consistent
( cd "${ROOT_DIR}" && docker compose down )

# Create archive
( cd "$(dirname "${ROOT_DIR}")" && \
  tar -czf "${ARCHIVE_PATH}" \
    --exclude="DataLakehouse/.venv" \
    --exclude="DataLakehouse/.git" \
    DataLakehouse )

echo "Backup created: ${ARCHIVE_PATH}"

# Implementation Plan: DataLakehouse Script Optimization

This plan details the surgical changes to optimize all operational scripts for robustness, performance, and portability.

## Phase 1: Shared Environment Core
- [x] **Task 1.1**: Create `scripts/lib_env.sh`.
    - Centralize `.env` loading with support for:
        - Windows/WSL encoding normalization.
        - Whitespace/quote stripping.
        - Strict validation functions (`is_valid_port`, `is_valid_cidr`).
- [x] **Task 1.2**: Update `scripts/stackctl.sh` and `scripts/setup.sh` to source `lib_env.sh`.
    - Remove duplicated parsing logic.

## Phase 2: Refactoring setup.sh
- [x] **Task 2.1**: Implement "Pre-flight Checks".
    - Check Docker, Docker Compose, and `uv` versions.
    - Validate `web_network` early.
- [x] **Task 2.2**: Implement "Intelligent Port Suggestions".
    - Function to check if a port is in use and suggest the next available (e.g., if 28123 taken, suggest 28124).
- [x] **Task 2.3**: Improve UX.
    - Clearer section headers and color-coded success/warning messages.

## Phase 3: Enhancing stackctl.sh
- [x] **Task 3.1**: Modularize command handlers.
    - Convert `case` blocks into clean function calls.
- [x] **Task 3.2**: Add `diagnose` command.
    - Check port conflicts.
    - Check container logs for "Connection Refused" or "Access Denied".
    - Check disk space/volume status.
- [x] **Task 3.3**: Optimize `redeploy`.
    - Add `--safe` flag to trigger `maintenance_tasks.py` (backup) before destructive operations.

## Phase 4: Python Script Portability & Performance
- [x] **Task 4.1**: Update `scripts/verify_lakehouse_architecture.py`.
    - Replace sequential probes with concurrent checks using `concurrent.futures`.
    - Improve "effective host" discovery logic (Docker bridge IP vs. 127.0.0.1).
    - Add `--json` output flag.
- [x] **Task 4.2**: Update `scripts/maintenance_tasks.py`.
    - Improve error handling for S3 connection timeouts.
    - Add progress logging for large cleanup tasks.

## Phase 5: Watcher & Firewall
- [x] **Task 5.1**: Optimize `scripts/realtime_watcher.sh`.
    - Replace `sleep 10` with improved polling and md5 detection.
    - Add lock file to prevent multiple watcher instances.
- [x] **Task 5.2**: Update `scripts/setup_ufw_docker.sh`.
    - Use the unified environment library.
    - Improve rule cleanup logic (reverse deletion).

## Phase 6: Validation
- [x] **Task 6.1**: Run `bash scripts/stackctl.sh validate-env`.
- [x] **Task 6.2**: Run `bash scripts/stackctl.sh health`.
- [x] **Task 6.3**: Verify end-to-end bootstrap with `bash scripts/setup.sh`.

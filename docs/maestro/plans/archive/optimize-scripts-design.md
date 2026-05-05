# Design Document: DataLakehouse Script Optimization

**Goal**: Transform current operational scripts into a robust, high-performance, and portable management suite.

## 1. Current Issues Identified

### Bash Scripts (`setup.sh`, `stackctl.sh`)
- **Environment Inconsistency**: `.env` parsing is duplicated and varies in robustness (e.g., handling of quotes, spaces, and multi-line values).
- **Error Diagnostics**: `stackctl.sh` has a good trap, but error messages could be more actionable (e.g., providing specific commands to fix port conflicts).
- **Redundancy**: `setup.sh` and `stackctl.sh` share some logic for network checks and status reporting.

### Python Scripts (`verify_lakehouse_architecture.py`, `run_etl_and_dashboard.py`)
- **Host Discovery**: Probing for internal vs. external ports is manual and sometimes fragile on WSL2.
- **Dependency Management**: While `uv` is recommended, some scripts lack clear "fail-fast" messages when specific optional libraries are missing.
- **Performance**: Architecture verification probes every endpoint sequentially; this can be parallelized or cached more effectively.

## 2. Optimization Strategy

### A. Unified Environment Management
- Create a shared `scripts/lib_env.sh` for Bash scripts to centralize `.env` loading and validation.
- Implement robust parsing that handles:
    - Values with spaces/quotes.
    - Surrogate-escaped bytes (WSL issue).
    - Port uniqueness validation.

### B. Robust Bash Core (`stackctl.sh` Refactoring)
- Modularize commands into functions.
- Add `diagnose` command: When a service is unhealthy, run specific checks (logs, port availability, disk space).
- Enhance `redeploy`: Add a "safe" mode that backups ClickHouse metadata before hard resets.

### C. Portable Python Verification (`verify_lakehouse_architecture.py`)
- Implement a more aggressive auto-discovery of the "effective host" (Docker bridge vs. Localhost vs. LAN IP).
- Add JSON output mode for programmatic health monitoring.
- Optimize S3/ClickHouse connectivity checks with concurrent probes.

### D. Setup & Bootstrap (`setup.sh`)
- Improve the interactive experience with "suggested" values based on detected system state (e.g., if port 5432 is taken, suggest 25432).
- Add a "Pre-flight Check" phase that validates Docker/Compose/uv versions before asking questions.

## 3. Success Criteria
- `stackctl.sh validate-env` identifies 100% of common configuration errors.
- `setup.sh` completes a full bootstrap in < 2 minutes for a new user.
- Zero "Connection Refused" errors in verification scripts when the stack is healthy.
- Consistent behavior across Linux, macOS, and WSL2.

## 4. Proposed Changeset

| Script | Type | Main Improvement |
| --- | --- | --- |
| `scripts/lib_env.sh` | New | Shared environment logic for Bash. |
| `scripts/setup.sh` | Modify | Pre-flight checks + intelligent port suggestions. |
| `scripts/stackctl.sh` | Modify | Modularization + enhanced diagnostics. |
| `scripts/verify_lakehouse_architecture.py` | Modify | Robust host discovery + parallel probes. |
| `mage/utils/rustfs_layer_reader.py` | Modify | Improved exception handling for S3 connection drops. |

---
**Next Step**: Create Implementation Plan after Design Approval.

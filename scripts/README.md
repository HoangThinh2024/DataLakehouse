# scripts/

Operational scripts for bootstrapping, lifecycle management, ETL automation,
firewall configuration, and system validation.

---

## Script Reference

### `setup.sh` – Initial bootstrap (run once)

Interactive guided setup for a fresh deployment.

```bash
bash scripts/setup.sh
```

What it does:
1. Reads existing `.env` values if present.
2. Prompts for mutable settings (bind IPs, ports, credentials, image tags).
3. Writes a complete `.env` file.
4. Creates the external Docker network `web_network` if missing.
5. Runs `docker compose up -d`.
6. Optionally runs ETL and Superset dashboard provisioning.

---

### `stackctl.sh` – Day-2 lifecycle manager

Single entry point for all operational tasks after initial setup.

```bash
bash scripts/stackctl.sh <command> [options]
```

| Command | Description |
|---------|-------------|
| `up` | Start all services |
| `down` | Stop all services |
| `redeploy` | Pull latest images and recreate containers |
| `redeploy --with-etl` | Redeploy + run ETL pipeline automatically |
| `status` | Show container status (`docker compose ps`) |
| `health` | Run Docker healthchecks on all services |
| `logs <service\|all>` | Stream logs (tail 50 by default) |
| `inspect <service>` | Show full container config |
| `check-env` | Print active `.env` values |
| `validate-env` | Validate port uniqueness and required fields |
| `sync-env` | Interactively update `.env` values |
| `reset` | Remove containers (keep volumes) |
| `reset --hard` | Remove containers and volumes |
| `check-system` | Run architecture validation (`verify_lakehouse_architecture.py`) |

---

### `run_etl_and_dashboard.py` – ETL + dashboard provisioning

Triggers the Mage ETL pipeline and provisions Superset dashboards via the API.

```bash
# Interactive
uv run python scripts/run_etl_and_dashboard.py

# Non-interactive (CI-friendly)
uv run python scripts/run_etl_and_dashboard.py --auto

# Force a specific source table
uv run python scripts/run_etl_and_dashboard.py --auto --table sales_orders

# Create sample table first, then run ETL + dashboard
uv run python scripts/run_etl_and_dashboard.py --auto --create-sample-table --table sales_orders

# ETL only – skip dashboard creation
uv run python scripts/run_etl_and_dashboard.py --auto --skip-dashboard
```

**Dependencies:** `boto3`, `psycopg2-binary`, `requests` (installed via `uv sync`).

---

### `create_superset_demo_dashboard.py` – Superset dashboard provisioner

Programmatically creates Superset datasets, charts, and dashboards using the
Superset REST API. Called internally by `run_etl_and_dashboard.py`.

```bash
uv run python scripts/create_superset_demo_dashboard.py
```

Reads the following from `.env` / environment:
- `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`
- `DLH_SUPERSET_PORT`
- `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`

---

### `demo_to_lakehouse.py` – Sample data loader

Creates and populates a demo source table in PostgreSQL (`demo` or `sales_orders`)
with realistic synthetic data. Used for testing and demonstrations.

```bash
uv run python scripts/demo_to_lakehouse.py
```

---

### `verify_lakehouse_architecture.py` – Architecture validator

End-to-end health check script. Tests connectivity to all services and verifies
data is flowing through the lake layers correctly.

```bash
uv run python scripts/verify_lakehouse_architecture.py
```

Exit codes:
- `0` – all checks passed
- `1` – one or more checks failed

The script auto-detects Docker host IPs/ports from `.env` so it works both
inside and outside the container network.

---

### `maintenance_tasks.py` – Backup and cleanup

Performs scheduled maintenance:
1. **Backup:** Native ClickHouse `BACKUP DATABASE analytics` to RustFS `s3://backups/`.
2. **Cleanup:** Removes Parquet files older than 30 days from Silver and Gold layers.
3. **Cleanup:** Removes ClickHouse backup snapshots older than 30 days.

```bash
# Run manually
docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py

# Schedule with cron (run at 02:00 daily)
0 2 * * * docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py >> /var/log/dlh_maintenance.log 2>&1
```

---

### `realtime_watcher.sh` – File-upload trigger

Monitors the RustFS Docker volume using `inotifywait`. When a new Excel or CSV
file is detected, it immediately triggers the corresponding Mage pipeline.

```bash
bash scripts/realtime_watcher.sh
```

- Excel files (`.xlsx`) → triggers `etl_excel_to_lakehouse`
- CSV files (`.csv`) → triggers `etl_csv_upload_to_reporting`

Useful for non-technical users who upload files via the RustFS Console and
need near-real-time ETL without waiting for the scheduled run.

---

### `setup_ufw_docker.sh` – Firewall management

Manages Docker-aware UFW rules using `ufw-docker` workflow. Reads CIDR and
port settings from `.env`.

```bash
# Apply rules
bash scripts/setup_ufw_docker.sh

# Remove managed rules only
bash scripts/setup_ufw_docker.sh --remove

# Remove rules and stop stack
bash scripts/setup_ufw_docker.sh --down
```

**Important:** This script does **not** modify SSH rules. Safe to run on remote servers.

---

## Dependencies

Host-side scripts require:

```bash
# Install runtime (once)
uv sync --all-groups

# Check
uv run python --version
uv run python -c "import boto3, psycopg2, requests; print('OK')"
```

Python package dependencies are declared in `pyproject.toml`.

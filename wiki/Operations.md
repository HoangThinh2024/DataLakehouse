# Operations

Day-to-day operations reference for managing the DataLakehouse stack lifecycle.

All lifecycle operations go through `scripts/stackctl.sh`.

---

## Lifecycle Management

### Start and stop

```bash
# Start all services
bash scripts/stackctl.sh up

# Stop all services (containers only; volumes are preserved)
bash scripts/stackctl.sh down

# Pull latest images and recreate containers
bash scripts/stackctl.sh redeploy

# Safe redeploy (runs backup before restarting)
bash scripts/stackctl.sh redeploy --safe

# Redeploy and run ETL automatically afterwards
bash scripts/stackctl.sh redeploy --with-etl
```

### Reset

```bash
# Soft reset — remove containers, keep data volumes
bash scripts/stackctl.sh reset

# Hard reset — remove containers AND all data volumes (destructive!)
bash scripts/stackctl.sh reset --hard
```

> **Warning:** `reset --hard` deletes all PostgreSQL, ClickHouse, RustFS, Redis, and Grafana volumes.
> Run a backup before using this with real data.

### Full rebuild from scratch

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

---

## Health Monitoring

### Status and health checks

```bash
# Container up/down state
bash scripts/stackctl.sh status

# Deep health checks (connectivity, data presence)
bash scripts/stackctl.sh health

# Analyze port conflicts and critical log errors
bash scripts/stackctl.sh diagnose
```

### Logs

```bash
# Tail all service logs
bash scripts/stackctl.sh logs all

# Single service logs
bash scripts/stackctl.sh logs dlh-mage
bash scripts/stackctl.sh logs dlh-postgres

# Or use Docker directly (more options)
docker compose logs -f dlh-redis --tail 100
```

### Container inspection

```bash
bash scripts/stackctl.sh inspect dlh-clickhouse
docker compose ps
docker stats    # real-time CPU/memory usage
```

### Architecture validation

```bash
bash scripts/stackctl.sh check-system
# or directly:
uv run python scripts/verify_lakehouse_architecture.py
# for JSON output (CI-friendly):
uv run python scripts/verify_lakehouse_architecture.py --json
```

---

## Environment Management

`.env` is the single source of truth for all service configuration.

```bash
# Print current .env values
bash scripts/stackctl.sh check-env

# Validate — check for duplicate ports and blank required fields
bash scripts/stackctl.sh validate-env

# Interactive update + write back to .env
bash scripts/stackctl.sh sync-env
```

After making changes manually:

```bash
nano .env
bash scripts/stackctl.sh validate-env
bash scripts/stackctl.sh redeploy
```

---

## ETL Operations

### Manual ETL run (interactive)

```bash
uv run python scripts/run_etl_and_dashboard.py
```

### Non-interactive / CI

```bash
# Auto mode — no prompts
uv run python scripts/run_etl_and_dashboard.py --auto

# Force a specific source table
uv run python scripts/run_etl_and_dashboard.py --auto --table sales_orders

# Create sample data, then run ETL
uv run python scripts/run_etl_and_dashboard.py --auto --create-sample-table --table sales_orders

# ETL only — skip dashboard creation
uv run python scripts/run_etl_and_dashboard.py --auto --skip-dashboard
```

### Via Mage UI

1. Open http://localhost:26789
2. Navigate to **Pipelines**
3. Select the desired pipeline
4. Click **Run Pipeline Now**

### Via CLI inside the Mage container

```bash
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
docker compose exec dlh-mage magic run etl_excel_to_lakehouse
docker compose exec dlh-mage magic run etl_csv_upload_to_reporting
```

### Loading sample data into PostgreSQL

```bash
docker exec -i dlh-postgres psql -U postgres -d datalakehouse < postgres/init/002_sample_data.sql
```

---

## Realtime File Watcher

`scripts/realtime_watcher.sh` monitors the RustFS Docker volume and triggers ETL automatically when files are uploaded.

```bash
# Foreground
bash scripts/realtime_watcher.sh

# Background daemon
nohup bash scripts/realtime_watcher.sh >> /var/log/dlh-watcher.log 2>&1 &
```

| File type | Pipeline triggered |
|-----------|-------------------|
| `*.xlsx` | `etl_excel_to_lakehouse` |
| `*.csv` | `etl_csv_upload_to_reporting` |

---

## Redis Operations

### Health check

```bash
docker compose ps dlh-redis
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping   # expected: PONG
```

### Redis Insight GUI

Redis Insight is built into the `redis/redis-stack` image (no separate container required).

Open http://localhost:25540. On first visit, add a connection:
- **Host:** `127.0.0.1`
- **Port:** `6379`
- **Password:** value of `REDIS_PASSWORD` in `.env`

### Inspect Redis databases

```bash
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD"
# In the Redis CLI:
INFO keyspace    # show which DBs have keys
SELECT 2         # switch to Superset cache DB
DBSIZE           # number of keys in current DB
```

### Fix: WARNING Memory overcommit

Set on the host (not inside the container):

```bash
sudo sysctl -w vm.overcommit_memory=1
echo 'vm.overcommit_memory = 1' | sudo tee -a /etc/sysctl.conf
```

---

## Authentik Operations

### Health check

```bash
docker compose ps dlh-authentik-server dlh-authentik-worker
docker compose exec dlh-authentik-worker ak healthcheck
```

### First-run setup

Access the setup wizard at http://localhost:29090/if/flow/initial-setup/ using the credentials in `AUTHENTIK_BOOTSTRAP_EMAIL` / `AUTHENTIK_BOOTSTRAP_PASSWORD`.

### Restart the worker

```bash
docker compose up -d dlh-authentik-worker
```

---

## Maintenance

`scripts/maintenance_tasks.py` handles:
- **ClickHouse backup** to RustFS (`s3://backups/clickhouse/YYYY-MM-DD/`)
- **Cleanup** of old Parquet files and backups older than **30 days** (configurable via `RETENTION_DAYS`)

### Run manually

```bash
docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py
```

### Automate with cron

```bash
# Runs at 02:00 daily — edit crontab: crontab -e
0 2 * * * docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py >> /var/log/dlh_maintenance.log 2>&1
```

---

## Firewall Management

`scripts/setup_ufw_docker.sh` manages Docker-aware UFW rules.

```bash
# Apply rules for current .env/CIDR
bash scripts/setup_ufw_docker.sh

# Remove managed rules only
bash scripts/setup_ufw_docker.sh --remove

# Remove rules and stop the stack
bash scripts/setup_ufw_docker.sh --down
```

> This script uses the `ufw-docker` workflow and **does not touch SSH rules** — safe on remote servers.

---

## Complete `stackctl.sh` Command Reference

| Command | Effect |
|---------|--------|
| `up` | Start all services |
| `down` | Stop all services |
| `redeploy` | Pull images + recreate containers |
| `redeploy --safe` | Backup + redeploy |
| `redeploy --with-etl` | Redeploy + run ETL pipeline |
| `status` | Show container status |
| `health` | Deep health checks |
| `diagnose` | Analyze logs and port conflicts |
| `logs <service\|all>` | Stream logs |
| `inspect <service>` | Show container config/state |
| `check-env` | Print current `.env` values |
| `validate-env` | Validate port uniqueness and required fields |
| `sync-env` | Interactive `.env` update + write back |
| `reset` | Remove containers (keep volumes) |
| `reset --hard` | Remove containers AND volumes |
| `check-system` | Run architecture validation |

---

> See [docs/OPERATIONS.md](../docs/OPERATIONS.md) for the full operations reference.

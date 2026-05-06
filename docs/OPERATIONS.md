# DataLakehouse – Operations Guide

Day-to-day operations reference for developers and system administrators.
Covers lifecycle management, health monitoring, backup/restore, Redis/Authentik
operations, and maintenance procedures.

---

## Table of Contents

1. [Lifecycle Management](#1-lifecycle-management)
2. [Health Monitoring](#2-health-monitoring)
3. [Environment Management](#3-environment-management)
4. [ETL Operations](#4-etl-operations)
5. [Realtime File Watcher](#5-realtime-file-watcher)
6. [Redis Operations](#6-redis-operations)
7. [Authentik Operations](#7-authentik-operations)
8. [Apache Guacamole Operations](#8-apache-guacamole-operations)
9. [Backup and Restore](#9-backup-and-restore)
10. [Maintenance and Cleanup](#10-maintenance-and-cleanup)
11. [Firewall Management](#11-firewall-management)
12. [Common Recovery Procedures](#12-common-recovery-procedures)
13. [Production Checklist](#13-production-checklist)

---

## 1. Lifecycle Management

All lifecycle operations go through `scripts/stackctl.sh`.

### Start / Stop

```bash
# Start all services
bash scripts/stackctl.sh up

# Stop all services (containers only, volumes preserved)
bash scripts/stackctl.sh down

# Pull latest images, recreate containers
bash scripts/stackctl.sh redeploy

# Safe redeploy (runs backup before restarting containers)
bash scripts/stackctl.sh redeploy --safe

# Redeploy + run ETL pipeline automatically
bash scripts/stackctl.sh redeploy --with-etl
```

### Diagnostics

```bash
# Analyze the system for port conflicts and critical errors in logs
bash scripts/stackctl.sh diagnose
```

### Reset

```bash
# Soft reset: remove containers, keep data volumes
bash scripts/stackctl.sh reset

# Hard reset: remove containers AND all data volumes (destructive!)
bash scripts/stackctl.sh reset --hard
```

> **Warning:** `reset --hard` deletes all PostgreSQL, ClickHouse, RustFS, Redis, and Grafana volumes.
> Run a backup before using this in any environment with real data.

### Full Rebuild from Scratch

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

---

## 2. Health Monitoring

### Quick status check

```bash
bash scripts/stackctl.sh status       # container up/down state
bash scripts/stackctl.sh health       # deep health checks
```

### Logs

```bash
bash scripts/stackctl.sh logs all           # all services, tail 50
bash scripts/stackctl.sh logs dlh-mage      # single service
bash scripts/stackctl.sh logs dlh-postgres  # postgres specifically

# Or use Docker directly
docker compose logs -f dlh-redis --tail 100
```

### Container inspection

```bash
bash scripts/stackctl.sh inspect dlh-clickhouse
bash scripts/stackctl.sh inspect dlh-dockhand
docker compose ps
docker stats                  # real-time CPU/memory
```

### Architecture validation

```bash
bash scripts/stackctl.sh check-system
# or run directly:
uv run python scripts/verify_lakehouse_architecture.py
# for machine-readable output:
uv run python scripts/verify_lakehouse_architecture.py --json
```

The validation script checks connectivity to all services and verifies data is
flowing correctly through the lake layers. Exit code 0 = all green.

---

## 3. Environment Management

`.env` is the single source of truth for all service configuration.

```bash
# Show current values
bash scripts/stackctl.sh check-env

# Validate: no duplicate ports, no blank required fields
bash scripts/stackctl.sh validate-env

# Interactive update + write back to .env
bash scripts/stackctl.sh sync-env
```

To change a setting manually:
1. Edit `.env`
2. Run `bash scripts/stackctl.sh validate-env`
3. Run `bash scripts/stackctl.sh redeploy`

See [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md) for all available variables.

---

## 4. ETL Operations

### Manual ETL run (interactive)

```bash
uv run python scripts/run_etl_and_dashboard.py
```

### Loading Sample Data

To verify system stability and table relationships, you can load sample data into the PostgreSQL source table:

```bash
# Load sample data from the init script
docker exec -i dlh-postgres psql -U postgres -d datalakehouse < postgres/init/002_sample_data.sql

# Verify rows in the source table
docker exec dlh-postgres psql -U postgres -d datalakehouse -c "SELECT count(*) FROM public.\"Demo\";"
```

### Non-interactive / CI-friendly

```bash
# Auto mode (no prompts)
uv run python scripts/run_etl_and_dashboard.py --auto

# Force a specific source table
uv run python scripts/run_etl_and_dashboard.py --auto --table sales_orders

# Create sample table first, then run ETL
uv run python scripts/run_etl_and_dashboard.py --auto --create-sample-table --table sales_orders

# ETL only – skip dashboard creation
uv run python scripts/run_etl_and_dashboard.py --auto --skip-dashboard
```

### Run via Mage UI

1. Open `http://localhost:26789`
2. Navigate to **Pipelines**
3. Select `etl_postgres_to_lakehouse`
4. Click **Run Pipeline Now**

### Run via CLI inside container

```bash
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
docker compose exec dlh-mage magic run etl_excel_to_lakehouse
docker compose exec dlh-mage magic run etl_csv_upload_to_reporting
```

### Pipeline schedule (default)

| Pipeline | Schedule |
|----------|----------|
| `etl_postgres_to_lakehouse` | Every 6 hours (`0 */6 * * *`) |
| `etl_excel_to_lakehouse` | Manual or watcher-triggered |
| `etl_csv_upload_to_reporting` | Every 5 minutes |

---

## 5. Realtime File Watcher

`scripts/realtime_watcher.sh` monitors the RustFS volume on the Docker host and
triggers the relevant ETL pipeline within seconds of a file being uploaded.

### Start the watcher (runs in foreground)

```bash
bash scripts/realtime_watcher.sh
```

### Run as a background daemon

```bash
nohup bash scripts/realtime_watcher.sh >> /var/log/dlh-watcher.log 2>&1 &
```

### How it works

1. Uses `inotifywait` to watch the Docker volume mount path for RustFS.
2. On `CREATE` events matching `*.xlsx` or `*.csv`:
   - Excel files trigger `etl_excel_to_lakehouse`.
   - CSV files trigger `etl_csv_upload_to_reporting`.
3. Triggers are sent via the Mage API.

---

## 6. Redis Operations

### Health check

```bash
docker compose ps dlh-redis
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping
# Expected: PONG
```

### View Redis logs

```bash
docker compose logs dlh-redis --tail 100
```

### Redis Insight GUI

Redis Insight is bundled inside the `redis/redis-stack` image and runs on container port **8001**,
mapped to `DLH_REDIS_GUI_PORT` (default `25540`) on the host.

```
http://localhost:25540
```

There is no separate `redisinsight` container. On first visit, add a connection:

- **Host**: `127.0.0.1`
- **Port**: `6379`
- **Password**: value of `REDIS_PASSWORD` in `.env`

If Redis Insight is not reachable, verify the port mapping is active:

```bash
docker compose ps dlh-redis        # should show port 0.0.0.0:25540->8001/tcp
docker compose logs dlh-redis --tail 30
```

### Inspect Redis databases

```bash
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD"
# In Redis CLI:
INFO keyspace           # show which DBs have keys
SELECT 2                # switch to Superset cache DB
DBSIZE                  # number of keys
```

### Database allocation

| DB Index | Used by |
|----------|---------|
| 0 | Default (unused) |
| 1 | Authentik queue + cache |
| 2 | Superset dashboard/query cache |
| 3 | Superset SQL Lab results backend |

### When Superset is slow

1. Verify Redis is healthy: `bash scripts/stackctl.sh health`
2. Check `SUPERSET_REDIS_CACHE_DB` and `SUPERSET_REDIS_RESULTS_DB` in `.env`
3. Restart Superset and Redis:

```bash
docker compose up -d dlh-redis superset
```

### Fix: WARNING Memory overcommit

Redis may log `WARNING Memory overcommit must be enabled`. This cannot be set safely
via container sysctl in this stack. Set it on the host instead:

```bash
sudo sysctl -w vm.overcommit_memory=1
echo 'vm.overcommit_memory = 1' | sudo tee -a /etc/sysctl.conf
```

### Fix: Possible SECURITY ATTACK detected

This means HTTP traffic reached the Redis port (common with scanners). Ensure
`REDIS_BIND_IP=127.0.0.1` in `.env` so Redis is not exposed to external networks.

---

## 7. Authentik Operations

### Health check

```bash
docker compose ps dlh-authentik-server dlh-authentik-worker
docker compose exec dlh-authentik-worker ak healthcheck
```

### View logs

```bash
docker compose logs dlh-authentik-server --tail 120
docker compose logs dlh-authentik-worker --tail 120
```

### When background tasks are not processing

1. Verify both `dlh-authentik-worker` and `dlh-redis` are healthy.
2. Check `REDIS_AUTHENTIK_DB` and `REDIS_PASSWORD` are consistent in `.env`.
3. Restart the worker:

```bash
docker compose up -d dlh-authentik-worker
```

### First-run setup

On first boot, Authentik creates an admin account using:
- `AUTHENTIK_BOOTSTRAP_EMAIL`
- `AUTHENTIK_BOOTSTRAP_PASSWORD`

Access the setup wizard at `http://localhost:29090/if/flow/initial-setup/`.

---

## 8. Apache Guacamole Operations

Apache Guacamole provides clientless remote desktop access (RDP, VNC, SSH) to the DataLakehouse server via any web browser.

### Access

- **URL**: `http://localhost:28090/guacamole/`
- **Default Credentials**: `guacadmin` / `guacadmin`

> **Security Warning:** Change the default password immediately after first login.

### Service health

```bash
docker compose ps dlh-guacamole dlh-guacd
# Both should be 'Up' and 'Healthy'
```

### View logs

```bash
docker compose logs dlh-guacamole --tail 100
docker compose logs dlh-guacd --tail 100
```

### Database management

Guacamole stores connection data in a dedicated PostgreSQL database:
- **DB Name**: `dlh_guacamole` (set via `GUACAMOLE_DB_NAME`)
- **DB User**: `dlh_guacamole_user` (set via `GUACAMOLE_DB_USER`)

### Adding connections

1. Log in to Guacamole as an administrator.
2. Go to **Settings** -> **Connections** -> **New Connection**.
3. For **SSH access** to the host, use hostname `host.docker.internal` (if enabled) or the LAN IP of the server.

---

## 9. Backup and Restore

### ClickHouse backup

The `scripts/maintenance_tasks.py` script uses ClickHouse's native `BACKUP` command
to create a compressed snapshot stored in RustFS (`s3://backups/clickhouse/YYYY-MM-DD/`).

**Run manually:**

```bash
docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py
```

**Automate with cron** (runs at 02:00 daily):

```bash
# Add to crontab: crontab -e
0 2 * * * docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py >> /var/log/dlh_maintenance.log 2>&1
```

### ClickHouse restore

1. Open RustFS Console at `http://localhost:29101` → bucket `backups` → find the desired date.
2. Connect to ClickHouse and run:

```sql
-- Step 1: Drop the damaged database (CAUTION – irreversible)
DROP DATABASE IF EXISTS analytics;

-- Step 2: Restore from the S3 backup (replace YYYY-MM-DD with your target date)
RESTORE DATABASE analytics FROM S3(
    'http://dlh-rustfs:9000/backups/clickhouse/YYYY-MM-DD/',
    'rustfsadmin',       -- or your RUSTFS_ACCESS_KEY value
    'rustfsadmin'        -- or your RUSTFS_SECRET_KEY value
);
```

3. Verify row counts after restore:

```sql
SELECT table, count() FROM system.parts
WHERE database = 'analytics' AND active
GROUP BY table ORDER BY table;
```

> All credentials for backup/restore are read from `.env` at runtime.
> Ensure `RUSTFS_ACCESS_KEY` and `RUSTFS_SECRET_KEY` match between Mage and RustFS.

### PostgreSQL backup

Docker volumes can be backed up using standard Docker volume backup procedures:

```bash
docker run --rm -v datalakehouse_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /data
```

---

## 9. Maintenance and Cleanup

`scripts/maintenance_tasks.py` also handles cleanup:

- **Retention policy:** Keeps the last **30 days** of data.
- **Cleaned objects:**
  - Old Parquet files in RustFS `silver/` and `gold/` layers.
  - Old ClickHouse backups in `s3://backups/` older than 30 days.

Run manually:

```bash
docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py
```

To add custom retention logic, edit `scripts/maintenance_tasks.py` and adjust the
`RETENTION_DAYS` constant.

---

## 10. Firewall Management

`scripts/setup_ufw_docker.sh` manages Docker-aware UFW rules.

### Apply rules

```bash
bash scripts/setup_ufw_docker.sh
```

This reads `DLH_LAN_CIDR`, `DLH_APP_BIND_IP`, `DLH_DATA_BIND_IP`, and
`UFW_ALLOW_DATA_PORTS` from `.env` and creates appropriately scoped rules.

### Remove managed rules only

```bash
bash scripts/setup_ufw_docker.sh --remove
```

### Remove rules and stop stack

```bash
bash scripts/setup_ufw_docker.sh --down
```

### Important behaviors

- Uses `ufw-docker` workflow for Docker-published ports.
- **Does not touch SSH rules** — safe to run on remote servers.
- Each rule has an explicit comment for auditing.
- `--remove` cleans up only the rules added by this script.

### Recommended network split

```ini
# App ports: UI tools behind reverse proxy, local only
DLH_APP_BIND_IP=127.0.0.1

# Data ports: Postgres/ClickHouse/RustFS accessible from LAN
DLH_DATA_BIND_IP=0.0.0.0
UFW_ALLOW_DATA_PORTS=true
DLH_LAN_CIDR=192.168.1.0/24
```

---

## 11. Common Recovery Procedures

### Service not healthy

```bash
bash scripts/stackctl.sh health
bash scripts/stackctl.sh logs <service>
# For a specific service:
docker compose logs dlh-mage --tail 200
docker compose up -d dlh-mage     # restart one service
```

### Port conflict on startup

```bash
bash scripts/stackctl.sh validate-env   # shows duplicate/conflicting ports
bash scripts/stackctl.sh sync-env       # interactive: update port values
bash scripts/stackctl.sh redeploy
```

### WSL / encoding errors in `.env`

If you see `invalid UTF-8` or surrogate encoding errors during PostgreSQL connection:

```bash
uv run python scripts/run_etl_and_dashboard.py --auto
```

The runner sanitizes BOM/Windows encodings and malformed inherited env values
automatically on WSL.

### ClickHouse tables missing after redeploy

ClickHouse schema is applied by `clickhouse/init/001_analytics_schema.sql` only on
first-time volume initialisation. If the volume already exists, the init script does
**not** re-run. To re-apply schema:

```bash
bash scripts/stackctl.sh reset --hard   # deletes ClickHouse volume
bash scripts/setup.sh                   # re-initialises everything
```

### Mage pipelines not visible

```bash
docker compose logs dlh-mage --tail 100
# If Mage shows no pipelines, restart it:
docker compose up -d dlh-mage
```

---

## 12. Production Checklist

Before promoting to a production environment:

- [ ] **Rotate all default passwords** — every `change-*` and `replace-*` value in `.env`.
- [ ] **Pin all image tags** — replace `latest` with specific versions in `.env`.
- [ ] **Restrict bind IPs** — `DLH_APP_BIND_IP=127.0.0.1`, expose only via reverse proxy.
- [ ] **Enable TLS** — configure Nginx Proxy Manager with valid certificates.
- [ ] **Configure firewall** — run `setup_ufw_docker.sh` with appropriate `DLH_LAN_CIDR`.
- [ ] **Set up automated backups** — add cron job for `maintenance_tasks.py`.
- [ ] **Test restore procedure** — verify backup files in RustFS and practice the RESTORE SQL.
- [ ] **Monitor with Grafana** — confirm `pipeline_runs` dashboard is showing recent run data.
- [ ] **Validate architecture** — `bash scripts/stackctl.sh check-system` returns no errors.

# Troubleshooting

Common issues, their causes, and how to fix them.

---

## Quick Diagnostics

Before digging into a specific issue, run the built-in diagnostics:

```bash
bash scripts/stackctl.sh health          # deep health checks
bash scripts/stackctl.sh diagnose        # analyze logs + port conflicts
bash scripts/stackctl.sh logs all        # tail all service logs
```

---

## Services Not Starting or Unhealthy

### Symptoms
- `docker compose ps` shows a container as `unhealthy`, `restarting`, or `exited`
- `bash scripts/stackctl.sh health` reports failures

### Steps

1. Check status and logs:
   ```bash
   bash scripts/stackctl.sh status
   bash scripts/stackctl.sh logs dlh-<service>
   ```

2. Restart the single failing service:
   ```bash
   docker compose up -d dlh-<service>
   ```

3. If still failing, hard reset and start fresh:
   ```bash
   bash scripts/stackctl.sh reset --hard
   bash scripts/setup.sh
   ```

---

## Port Conflicts

### Symptoms
- Services fail to start with `bind: address already in use`
- `validate-env` reports duplicate ports

### Steps

```bash
bash scripts/stackctl.sh validate-env   # shows which ports conflict
bash scripts/stackctl.sh sync-env       # interactively change port values
bash scripts/stackctl.sh redeploy       # apply new ports
```

If a system process already uses a port, reassign the `DLH_*_PORT` variable in `.env`.

---

## ClickHouse Data Missing

### Symptoms
- ClickHouse tables are empty after a pipeline run
- Superset dashboards show no data

### Cause 1 — Schema not initialised

ClickHouse schema (`clickhouse/init/001_analytics_schema.sql`) only runs on **first** volume creation. If the volume already exists but the schema was not applied, tables will be missing.

**Fix:**
```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

### Cause 2 — Pipeline did not run successfully

Check the pipeline run status:
```bash
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
bash scripts/stackctl.sh logs dlh-mage
```

Or open the Mage UI at http://localhost:26789 → **Pipelines** → select pipeline → **Runs**.

### Cause 3 — No source data

Verify rows exist in the source table:
```bash
docker exec dlh-postgres psql -U postgres -d datalakehouse \
  -c 'SELECT count(*) FROM public."Demo";'
```

Load sample data if needed:
```bash
docker exec -i dlh-postgres psql -U postgres -d datalakehouse \
  < postgres/init/002_sample_data.sql
```

---

## Mage Pipelines Not Visible

### Symptoms
- The Mage UI shows no pipelines

### Steps

```bash
docker compose logs dlh-mage --tail 100
docker compose up -d dlh-mage
```

If pipelines disappear after a redeploy, ensure the `mage/` directory is correctly mounted as a volume in `docker-compose.yaml`.

---

## WSL Encoding Errors

### Symptoms
- `invalid UTF-8` or surrogate encoding errors on PostgreSQL connection
- Errors during `.env` reading on WSL2

### Fix

Use the automation script which sanitizes BOM/Windows encodings automatically:

```bash
uv run python scripts/run_etl_and_dashboard.py --auto
```

---

## Redis Insight Not Accessible

### Symptoms
- http://localhost:25540 is unreachable

### Steps

Redis Insight is **built into** the `redis/redis-stack` image — there is no separate container. Verify the `dlh-redis` container is healthy and the port is mapped:

```bash
docker compose ps dlh-redis        # should show port 0.0.0.0:25540->8001/tcp
docker compose logs dlh-redis --tail 30
```

On first visit add a connection:
- **Host:** `127.0.0.1`
- **Port:** `6379`
- **Password:** value of `REDIS_PASSWORD` in `.env`

---

## Superset Is Slow or Dashboards Fail to Load

### Symptoms
- Superset dashboard queries time out
- SQL Lab results never return

### Steps

1. Verify Redis is healthy:
   ```bash
   docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping
   ```

2. Check `.env` cache variables are correct:
   ```
   SUPERSET_REDIS_CACHE_DB=2
   SUPERSET_REDIS_RESULTS_DB=3
   ```

3. Restart Superset and Redis:
   ```bash
   docker compose up -d dlh-redis dlh-superset
   ```

---

## Authentik Background Tasks Not Processing

### Symptoms
- Authentik emails not sent
- SSO flows timing out

### Steps

```bash
docker compose ps dlh-authentik-server dlh-authentik-worker
docker compose logs dlh-authentik-worker --tail 100
```

Ensure `REDIS_AUTHENTIK_DB` and `REDIS_PASSWORD` are consistent in `.env`. Restart the worker:

```bash
docker compose up -d dlh-authentik-worker
```

---

## Redis WARNING: Memory Overcommit

### Symptoms
- Redis logs: `WARNING Memory overcommit must be enabled!`

### Fix

Set on the **host** (cannot be set safely via container sysctl):

```bash
sudo sysctl -w vm.overcommit_memory=1
echo 'vm.overcommit_memory = 1' | sudo tee -a /etc/sysctl.conf
```

---

## Redis: Possible SECURITY ATTACK Detected

### Symptoms
- Redis logs: `Possible SECURITY ATTACK detected`

### Cause

HTTP traffic has reached the Redis port (common with port scanners). Redis is not meant to receive HTTP requests.

### Fix

In `.env`, ensure Redis is not exposed externally:

```ini
REDIS_BIND_IP=127.0.0.1
```

Then redeploy:

```bash
bash scripts/stackctl.sh redeploy
```

---

## ETL Pipeline Fails with "Table not found"

### Symptoms
- `extract_postgres.py` raises `ValueError: Table not found`

### Fix

Set the source table name in `.env`:

```ini
SOURCE_TABLE=Demo
# Or, for fallback auto-detection:
SOURCE_TABLE_CANDIDATES=Demo,sales_orders,transactions
```

Verify the table exists:

```bash
docker exec dlh-postgres psql -U postgres -d datalakehouse \
  -c "\dt public.*"
```

---

## Full Rebuild

When nothing else works:

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

> **Warning:** `reset --hard` deletes all Docker volumes (all data). Back up first if needed.

---

## Collecting Information for Bug Reports

When reporting an issue, include the output of:

```bash
bash scripts/stackctl.sh health
bash scripts/stackctl.sh diagnose
bash scripts/stackctl.sh logs all 2>&1 | tail -200
uv run python scripts/verify_lakehouse_architecture.py --json
```

---

> See [docs/OPERATIONS.md § Common Recovery Procedures](../docs/OPERATIONS.md#11-common-recovery-procedures) for additional recovery steps.

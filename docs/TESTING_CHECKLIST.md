# DataLakehouse – Testing Checklist

Use this checklist to verify a complete end-to-end deployment of the DataLakehouse stack.
Run after initial setup or after any major change.

---

## Pre-flight Checks

```bash
# All containers must be running and healthy
bash scripts/stackctl.sh health

# Verify Docker volumes exist
docker volume ls | grep datalakehouse_

# Environment sanity
bash scripts/stackctl.sh validate-env
```

Expected: no red lines, all healthchecks pass.

---

## Architecture Compliance

Run the built-in validation script:

```bash
uv run python scripts/verify_lakehouse_architecture.py
```

Expected: all checks print `✓`.

Manual checks (if the script is unavailable):

- [ ] PostgreSQL is reachable: `docker compose exec dlh-postgres pg_isready -U dlh_admin -d datalakehouse`
- [ ] RustFS S3 API responds: `curl -s http://localhost:29100/health`
- [ ] RustFS Console responds: `curl -s http://localhost:29101/rustfs/console/health`
- [ ] ClickHouse responds: `curl -s http://localhost:28123/ping`  → expected: `Ok.`
- [ ] Redis responds: `docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping` → expected: `PONG`
- [ ] Mage UI loads: `curl -s http://localhost:26789/api/status | python3 -m json.tool`
- [ ] Superset UI loads: `curl -s -o /dev/null -w "%{http_code}" http://localhost:28088/health` → expected: `200`
- [ ] Grafana UI loads: `curl -s -o /dev/null -w "%{http_code}" http://localhost:23001/api/health` → expected: `200`

---

## RustFS Layer Structure

Verify that the three lake buckets exist:

```bash
# Using MinIO CLI (if available on host)
mc alias set local http://localhost:29100 <RUSTFS_ACCESS_KEY> <RUSTFS_SECRET_KEY>
mc ls local/
# Expected: bronze  silver  gold  (at minimum)
```

Or check via the RustFS Console at `http://localhost:29101`.

---

## Pipeline Smoke Test: etl_postgres_to_lakehouse

### Step 1 – Trigger the pipeline

```bash
# Via Mage UI: http://localhost:26789 → Pipelines → etl_postgres_to_lakehouse → Run Now
# Or via CLI:
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
```

### Step 2 – Monitor execution

Watch pipeline logs in the Mage UI or:

```bash
docker compose logs dlh-mage --follow
```

- [ ] `extract_postgres` block completes (green)
- [ ] `bronze_to_rustfs` block completes (green)
- [ ] `transform_silver` block completes (green)
- [ ] `silver_to_rustfs` block completes (green)
- [ ] `transform_gold` block completes (green)
- [ ] `gold_to_rustfs` block completes (green)
- [ ] `load_to_clickhouse` block completes (green)

### Step 3 – Verify RustFS partitions

```bash
TODAY=$(date +%Y-%m-%d)

mc ls local/bronze/demo/dt=$TODAY/
mc ls local/silver/demo/dt=$TODAY/
mc ls local/gold/demo_daily/dt=$TODAY/
mc ls local/gold/demo_by_region/dt=$TODAY/
```

Each directory should contain at least one `.parquet` file.

### Step 4 – Verify ClickHouse data

```bash
docker compose exec dlh-clickhouse clickhouse-client \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  --query="SELECT table, count() as rows FROM system.parts WHERE database='analytics' AND active GROUP BY table ORDER BY table"
```

Expected tables with row counts > 0:
- `silver_demo`
- `gold_demo_daily`
- `gold_demo_by_region`
- `gold_demo_by_category`
- `pipeline_runs`

### Step 5 – Verify data lineage metadata

```bash
docker compose exec dlh-clickhouse clickhouse-client \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  --query="SELECT DISTINCT _pipeline_run_id, _source_table, _extracted_at FROM analytics.silver_demo LIMIT 5"
```

Expected: rows with valid UUIDs in `_pipeline_run_id` and a timestamp in `_extracted_at`.

---

## Pipeline Smoke Test: etl_csv_upload_to_reporting

```bash
# Upload a test CSV to the bronze bucket
echo "id,name,value,region
1,Test Item,100.00,North" > /tmp/test_upload.csv

mc cp /tmp/test_upload.csv local/bronze/csv_upload/test_upload.csv

# Wait up to 5 minutes for the pipeline to run, then check:
docker compose exec dlh-clickhouse clickhouse-client \
  --user="${CLICKHOUSE_USER}" --password="${CLICKHOUSE_PASSWORD}" \
  --query="SELECT COUNT(*) FROM analytics.csv_clean_rows"
```

Expected: count > 0.

---

## Pipeline Smoke Test: etl_excel_to_lakehouse

```bash
# Upload a sample Excel file from the samples/ directory
mc cp samples/Tong\ hop\ tien\ do\ 12\ du\ an.xlsx local/bronze/excel_upload/

# Trigger manually via Mage UI or:
docker compose exec dlh-mage magic run etl_excel_to_lakehouse

# Then verify:
docker compose exec dlh-clickhouse clickhouse-client \
  --user="${CLICKHOUSE_USER}" --password="${CLICKHOUSE_PASSWORD}" \
  --query="SELECT COUNT(*) FROM analytics.project_reports"
```

Expected: count > 0.

---

## Dashboard Verification

### Superset

1. Log in at `http://localhost:28088` (default: admin / admin).
2. Navigate to **Dashboards**.
3. Open **Sales Overview** (or any available dashboard).
4. Charts should render data without errors.

### Grafana

1. Log in at `http://localhost:23001` (default: admin / admin).
2. Navigate to **Dashboards → DataLakehouse Monitoring**.
3. Verify `pipeline_runs` panel shows recent pipeline executions.
4. All panels should be green / have data.

---

## Performance Baseline

After a successful first run:

- [ ] Pipeline execution time: < 5 minutes (for demo-scale data)
- [ ] ClickHouse query on `silver_demo`: response in < 1 second
- [ ] Superset dashboard initial load: < 5 seconds
- [ ] RustFS storage used: ~ 50 MB – 500 MB (depending on data size)

---

## Sign-Off

| Field | Value |
|-------|-------|
| Tested by | |
| Date | |
| Environment | local / staging / production |
| Stack version (`git log --oneline -1`) | |
| Status | ☐ Passed ☐ Failed ☐ Issues noted below |

**Notes:**

---

*Reference:*
*[ARCHITECTURE.md](ARCHITECTURE.md) – full data flow and schema reference.*
*[PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) – detailed pipeline block documentation.*

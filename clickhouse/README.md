# clickhouse/

ClickHouse configuration and initialisation files for the DataLakehouse analytics layer.

## Structure

```
clickhouse/
└── init/
    └── 001_analytics_schema.sql    # DDL: creates all analytics tables on first run
```

---

## Init Scripts

The `init/` directory is mounted to `/docker-entrypoint-initdb.d/` in the `dlh-clickhouse`
container. ClickHouse executes these files **only once**, when the data volume is
first created.

> **Note:** If the ClickHouse data volume already exists (e.g., after a `stackctl reset`
> without `--hard`), init scripts will **not** re-run. To re-apply schema, use
> `stackctl reset --hard` followed by `setup.sh`.

---

## Schema Overview (`001_analytics_schema.sql`)

**Database:** `analytics`

All tables use the `ReplacingMergeTree` engine to enable idempotent re-ingestion —
running the ETL pipeline multiple times with the same data will not create duplicate rows.

### PostgreSQL pipeline tables

| Table | Engine | Primary Key | Description |
|-------|--------|-------------|-------------|
| `silver_demo` | ReplacingMergeTree | `id, _pipeline_run_id` | Cleaned, typed rows from PostgreSQL source |
| `gold_demo_daily` | ReplacingMergeTree | `order_date, _pipeline_run_id` | Daily sales aggregation |
| `gold_demo_weekly` | ReplacingMergeTree | `week_start, _pipeline_run_id` | Weekly sales aggregation |
| `gold_demo_monthly` | ReplacingMergeTree | `year, month, _pipeline_run_id` | Monthly sales aggregation |
| `gold_demo_yearly` | ReplacingMergeTree | `year, _pipeline_run_id` | Yearly sales aggregation |
| `gold_demo_by_region` | ReplacingMergeTree | `region, _pipeline_run_id` | Per-region metrics |
| `gold_demo_by_category` | ReplacingMergeTree | `category, _pipeline_run_id` | Per-category metrics |
| `pipeline_runs` | ReplacingMergeTree | `run_id` | Pipeline execution log |

### Excel pipeline tables

| Table | Engine | Description |
|-------|--------|-------------|
| `project_reports` | ReplacingMergeTree | Detailed task rows from uploaded Excel project reports |
| `gold_projects_summary` | ReplacingMergeTree | Per-project KPI rollup (completion rate, overdue count) |
| `gold_workload_report` | ReplacingMergeTree | Per-person workload summary |

### CSV pipeline tables

| Table | Engine | Description |
|-------|--------|-------------|
| `csv_clean_rows` | ReplacingMergeTree | Cleaned rows from CSV uploads |

---

## Connecting to ClickHouse

### Via HTTP API

```bash
# Ping
curl http://localhost:28123/ping

# Run a query
curl -u "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
  "http://localhost:28123/?query=SELECT+COUNT(*)+FROM+analytics.silver_demo"
```

### Via clickhouse-client (inside the container)

```bash
docker compose exec dlh-clickhouse clickhouse-client \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  --database="analytics"
```

### Via CloudBeaver (web UI)

Open `http://localhost:28978`, create a new ClickHouse connection:

- Host: `dlh-clickhouse`
- Port: `8123` (HTTP) or `9000` (TCP)
- Database: `analytics`
- User / Password: from `.env`

---

## Useful Queries

```sql
-- List all tables with row counts
SELECT table, sum(rows) AS total_rows
FROM system.parts
WHERE database = 'analytics' AND active
GROUP BY table ORDER BY table;

-- Check recent pipeline runs
SELECT run_id, pipeline_name, status, rows_loaded, started_at
FROM analytics.pipeline_runs
ORDER BY started_at DESC LIMIT 10;

-- Inspect Silver data quality
SELECT
    count() AS total_rows,
    countIf(id IS NULL) AS null_ids,
    countIf(name = '') AS empty_names,
    min(_extracted_at) AS earliest,
    max(_extracted_at) AS latest
FROM analytics.silver_demo;
```

---

## Backup and Restore

See [docs/OPERATIONS.md – Backup and Restore section](../docs/OPERATIONS.md#8-backup-and-restore)
for instructions on using the native ClickHouse `BACKUP` / `RESTORE` commands via RustFS.

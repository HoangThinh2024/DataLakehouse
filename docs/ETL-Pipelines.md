# ETL Pipelines

The DataLakehouse stack ships with three pre-built Mage.ai pipelines that cover
the most common data ingestion patterns.

---

## Pipeline Overview

| Pipeline | Schedule | Source | Output |
|----------|----------|--------|--------|
| `etl_postgres_to_lakehouse` | Every 6 h (`0 */6 * * *`) | PostgreSQL table | RustFS Bronze/Silver/Gold + ClickHouse |
| `etl_excel_to_lakehouse` | Manual / file-upload watcher | Excel files in RustFS `bronze/excel_upload/` | ClickHouse `project_reports`, gold summary tables |
| `etl_csv_upload_to_reporting` | Every 5 min | CSV files in RustFS `bronze/csv_upload/` | RustFS Silver + ClickHouse `csv_clean_rows` |

---

## Pipeline 1: `etl_postgres_to_lakehouse`

**Purpose:** Full Medallion Architecture pipeline — extracts from PostgreSQL, produces Bronze/Silver/Gold Parquet files in RustFS, and loads ClickHouse.

**Schedule:** Every 6 hours (`0 */6 * * *`).

**Source detection logic:**

```
1. If SOURCE_TABLE is set → use that exact table
2. Otherwise → try each name in SOURCE_TABLE_CANDIDATES (case-insensitive)
3. If none found → raise ValueError listing all available tables
```

### Blocks

| Order | Block | Type | File |
|-------|-------|------|------|
| 1 | `extract_postgres` | data_loader | `mage/data_loaders/extract_postgres.py` |
| 2 | `bronze_to_rustfs` | data_exporter | `mage/data_exporters/bronze_to_rustfs.py` |
| 3 | `transform_silver` | transformer | `mage/transformers/transform_silver.py` |
| 4 | `silver_to_rustfs` | data_exporter | `mage/data_exporters/silver_to_rustfs.py` |
| 5 | `transform_gold` | transformer | `mage/transformers/transform_gold.py` |
| 6 | `gold_to_rustfs` | data_exporter | `mage/data_exporters/gold_to_rustfs.py` |
| 7 | `load_to_clickhouse` | data_exporter | `mage/data_exporters/load_to_clickhouse.py` |

### What each block does

**`extract_postgres`** — Connects to the PostgreSQL source database, auto-discovers the configured table, and returns a DataFrame annotated with:
- `_pipeline_run_id` — unique UUID for this run
- `_extracted_at` — timestamp
- `_source_table` — table name

**`bronze_to_rustfs`** — Writes the raw DataFrame as Parquet to:
```
s3://bronze/{table}/dt=YYYY-MM-DD/{run_id}.parquet
```

**`transform_silver`** — Cleans the Bronze DataFrame:
- Removes duplicate rows
- Casts column types
- Validates email fields
- Normalises whitespace

**`silver_to_rustfs`** — Writes cleaned data to:
```
s3://silver/{table}/dt=YYYY-MM-DD/{run_id}.parquet
```

**`transform_gold`** — Aggregates the Silver DataFrame into six slices:
- `gold_daily` — by calendar day
- `gold_weekly` — by ISO week
- `gold_monthly` — by month
- `gold_yearly` — by year
- `gold_region` — by geographic region
- `gold_category` — by product category

**`gold_to_rustfs`** — Writes each Gold slice to:
```
s3://gold/{table}_{granularity}/dt=YYYY-MM-DD/{run_id}.parquet
```

**`load_to_clickhouse`** — Reads the **latest Silver and Gold Parquet files directly from RustFS** (ignoring in-memory pipeline data) and performs `INSERT INTO` for each ClickHouse analytics table using `ReplacingMergeTree` idempotency.

---

## Pipeline 2: `etl_excel_to_lakehouse`

**Purpose:** Processes Excel project-management reports uploaded to RustFS and produces ClickHouse tables for Superset dashboards.

**Trigger:** Manual or automatically via `scripts/realtime_watcher.sh` when `.xlsx` files appear in `bronze/excel_upload/`.

### Blocks

| Order | Block | Type | File |
|-------|-------|------|------|
| 1 | `extract_excel_from_rustfs` | data_loader | `mage/data_loaders/extract_excel_from_rustfs.py` |
| 2 | `clean_excel_data` | transformer | `mage/transformers/clean_excel_data.py` |
| 3 | `load_excel_to_clickhouse` | data_exporter | `mage/data_exporters/load_excel_to_clickhouse.py` |

**`extract_excel_from_rustfs`** — Lists and downloads all Excel files from `bronze/excel_upload/`, concatenates them into a single DataFrame.

**`clean_excel_data`** — Strips junk rows (empty IDs), normalises Vietnamese status values, fills missing assignees.

**`load_excel_to_clickhouse`** — Loads cleaned data into three ClickHouse tables:
- `analytics.project_reports` — full task row detail
- `analytics.gold_projects_summary` — per-project KPIs (completion rate, overdue count)
- `analytics.gold_workload_report` — per-person workload metrics

---

## Pipeline 3: `etl_csv_upload_to_reporting`

**Purpose:** Continuously polls for new CSV uploads and makes them available as a queryable ClickHouse table.

**Schedule:** Every 5 minutes — polls RustFS `bronze/csv_upload/` for new files.

### Blocks

| Order | Block | Type | File |
|-------|-------|------|------|
| 1 | `extract_csv_from_rustfs` | data_loader | `mage/data_loaders/extract_csv_from_rustfs.py` |
| 2 | `clean_csv_for_reporting` | transformer | `mage/transformers/clean_csv_for_reporting.py` |
| 3 | `csv_to_rustfs_silver` | data_exporter | `mage/data_exporters/csv_to_rustfs_silver.py` |
| 4 | `load_csv_reporting_clickhouse` | data_exporter | `mage/data_exporters/load_csv_reporting_clickhouse.py` |

---

## Triggering Pipelines

### Via Mage UI

1. Open http://localhost:26789
2. Navigate to **Pipelines**
3. Select a pipeline
4. Click **Run Pipeline Now**

### Via CLI inside the Mage container

```bash
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
docker compose exec dlh-mage magic run etl_excel_to_lakehouse
docker compose exec dlh-mage magic run etl_csv_upload_to_reporting
```

### Via automation script

```bash
# Full ETL + Superset dashboard provisioning
uv run python scripts/run_etl_and_dashboard.py --auto

# Force a specific source table
uv run python scripts/run_etl_and_dashboard.py --auto --table sales_orders

# Create sample data, then run ETL
uv run python scripts/run_etl_and_dashboard.py --auto --create-sample-table --table sales_orders

# ETL only (skip dashboard creation)
uv run python scripts/run_etl_and_dashboard.py --auto --skip-dashboard
```

### Via stackctl redeploy

```bash
bash scripts/stackctl.sh redeploy --with-etl
```

---

## Realtime File Watcher

`scripts/realtime_watcher.sh` uses `inotifywait` to watch the Docker volume mount path for RustFS and triggers the appropriate pipeline within seconds of a file upload.

| File type | Pipeline triggered |
|-----------|-------------------|
| `*.xlsx` | `etl_excel_to_lakehouse` |
| `*.csv` | `etl_csv_upload_to_reporting` |

**Start the watcher:**

```bash
# Foreground
bash scripts/realtime_watcher.sh

# Background daemon
nohup bash scripts/realtime_watcher.sh >> /var/log/dlh-watcher.log 2>&1 &
```

---

## Uploading Files to RustFS

1. Open the RustFS Console at http://localhost:29101.
2. Log in with your `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY`.
3. Navigate to the target bucket and prefix:
   - Excel files → `bronze` bucket → `excel_upload/` prefix
   - CSV files → `bronze` bucket → `csv_upload/` prefix
4. Upload the file. The watcher (if running) will trigger the pipeline automatically.

---

## Monitoring Pipeline Runs

Grafana is pre-configured to visualise the `analytics.pipeline_runs` table in ClickHouse.

- Open Grafana at http://localhost:23001
- Navigate to the **Pipeline Monitoring** dashboard
- Each row in `pipeline_runs` records: run UUID, pipeline name, status, row counts, error message, and timestamps.

---

> See [docs/PIPELINE_GUIDE.md](../docs/PIPELINE_GUIDE.md) for detailed block-by-block documentation.

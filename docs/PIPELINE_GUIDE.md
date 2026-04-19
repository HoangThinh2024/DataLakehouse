# ⚙️ ETL Pipeline Guide – DataLakehouse

This document describes the two ETL pipelines in DataLakehouse in detail, including each block, the variables used, and how to customize them.

---

## Table of Contents

1. [Pipeline Architecture Overview](#1-pipeline-architecture-overview)
2. [Pipeline 1: etl_postgres_to_lakehouse](#2-pipeline-1-etl_postgres_to_lakehouse)
3. [Pipeline 2: etl_csv_upload_to_reporting](#3-pipeline-2-etl_csv_upload_to_reporting)
4. [I/O Configuration (io_config.yaml)](#4-io-configuration-io_configyaml)
5. [Adding a New Source Table](#5-adding-a-new-source-table)
6. [Customizing the Pipeline](#6-customizing-the-pipeline)
7. [Error Handling and Logging](#7-error-handling-and-logging)
8. [ClickHouse Schema](#8-clickhouse-schema)

---

## 1. Pipeline Architecture Overview

### Design Philosophy

DataLakehouse follows a strict **Lakehouse Architecture**:

1. **Immutability:** Data in RustFS is never deleted or overwritten
2. **RustFS is the Source of Truth:** ClickHouse is only the serving layer, reading from RustFS
3. **Traceability:** Every pipeline run has a unique UUID `run_id`
4. **Recovery:** ClickHouse can be fully rebuilt from RustFS at any time

### Overall Data Flow

```
Source (PostgreSQL / CSV)
    │
    ▼ EXTRACT
[Data Loader]
    │ DataFrame + metadata columns
    ▼ TRANSFORM
[Transformer 1: Silver]  ← Clean: dedup, validate, cast
    │ Silver DataFrame
    ▼ TRANSFORM
[Transformer 2: Gold]    ← Aggregate: daily/weekly/monthly/yearly/region/category
    │ Dict{silver, gold_daily, gold_weekly, gold_monthly, gold_yearly, gold_region, gold_category}
    ▼ EXPORT (parallel)
[bronze_to_rustfs]       ← Parquet to bronze/
[silver_to_rustfs]       ← Parquet to silver/
[gold_to_rustfs]         ← Parquet to gold/
    │ (completed)
    ▼ EXPORT
[load_to_clickhouse]     ← Read from RustFS → INSERT into ClickHouse
```

---

## 2. Pipeline 1: etl_postgres_to_lakehouse

**File:** `mage/pipelines/etl_postgres_to_lakehouse/`
**Schedule:** Every 6 hours (cron: `0 */6 * * *`)
**Source:** PostgreSQL
**Destination:** RustFS (Bronze/Silver/Gold) + ClickHouse

---

### Block 1: `extract_postgres.py` (Data Loader)

**File:** `mage/data_loaders/extract_postgres.py`

**Description:** Connects to PostgreSQL, finds the source table, and reads all data into a DataFrame.

**Environment variables used:**

| Variable | Container Default | Description |
|----------|-----------------|-------------|
| `SOURCE_DB_HOST` | `dlh-postgres` | Source PostgreSQL host |
| `SOURCE_DB_PORT` | `5432` | Source PostgreSQL port |
| `SOURCE_DB_NAME` | `datalakehouse` | Database containing the source table |
| `SOURCE_DB_USER` | `dlh_admin` | User for reading data |
| `SOURCE_DB_PASSWORD` | *(from .env)* | User password |
| `SOURCE_SCHEMA` | `public` | PostgreSQL schema |
| `SOURCE_TABLE` | *(empty)* | Specific table name (if set) |
| `SOURCE_TABLE_CANDIDATES` | `Demo,test_projects` | Candidate table list |
| `SOURCE_DB_CONNECT_TIMEOUT` | `15` | Connection timeout (seconds) |

**Table selection logic:**

```python
# Priority 1: SOURCE_TABLE is explicitly set
if SOURCE_TABLE:
    → Look for this table in information_schema.tables
    → If not found: raise ValueError with list of available tables

# Priority 2: Auto-detect from SOURCE_TABLE_CANDIDATES
else:
    → Try each name in SOURCE_TABLE_CANDIDATES (case-insensitive)
    → Use the first one found
    → If none found: raise ValueError
```

**Metadata columns added to the DataFrame:**

| Column | Type | Description |
|--------|------|-------------|
| `_pipeline_run_id` | `str (UUID)` | Unique ID for this pipeline run |
| `_source_table` | `str` | Name of the extracted table |
| `_extracted_at` | `str (ISO 8601 UTC)` | Extraction timestamp |

**Output:** `pd.DataFrame` with all columns from the source table + 3 metadata columns.

---

### Block 2: `transform_silver.py` (Transformer)

**File:** `mage/transformers/transform_silver.py`

**Description:** Cleans and validates raw data from PostgreSQL. Input is a raw DataFrame; output is a validated DataFrame.

**No environment variables** – logic is hardcoded for the Demo table schema.

**Processing steps:**

| Step | Processing | Columns Applied |
|------|-----------|----------------|
| 1 | Remove duplicates | All columns |
| 2 | Trim whitespace | `name`, `notes` |
| 3 | Title-case | `category`, `region` |
| 4 | Lowercase | `status` |
| 5 | Validate email | `customer_email` |
| 6 | Validate non-negative numbers | `value`, `quantity` |
| 7 | Cast types | `id` → Int64, `quantity` → Int32, `value` → Float64 |
| 8 | Parse dates | `order_date` → `date`, `created_at` → `datetime[UTC]` |
| 9 | Add metadata | `_silver_processed_at` |

**Metadata column added:**

| Column | Type | Description |
|--------|------|-------------|
| `_silver_processed_at` | `str (ISO 8601 UTC)` | Silver transform timestamp |

**Schema of processed Demo columns:**

```
id             Int64       (nullable)
name           str         (trimmed, nullable)
category       str         (title-case, nullable)
value          Float64     (>= 0, nullable)
quantity       Int64       (>= 0, nullable)
order_date     date        (nullable)
region         str         (title-case, nullable)
status         str         (lowercase, nullable)
customer_email str         (validated, nullable)
notes          str         (trimmed, nullable)
created_at     datetime64  (UTC, nullable)
```

**Output:** Cleaned `pd.DataFrame`.

---

### Block 3: `transform_gold.py` (Transformer)

**File:** `mage/transformers/transform_gold.py`

**Description:** Aggregates Silver data into six Gold tables along different analytical dimensions.

**Input:** DataFrame from `transform_silver`

**Output:** `dict` with 7 keys:

```python
{
    'silver': pd.DataFrame,          # Silver data (passed through to exporters)
    'gold_daily': pd.DataFrame,      # Daily aggregation
    'gold_weekly': pd.DataFrame,     # Weekly aggregation (ISO week)
    'gold_monthly': pd.DataFrame,    # Monthly aggregation
    'gold_yearly': pd.DataFrame,     # Yearly aggregation
    'gold_region': pd.DataFrame,     # Regional aggregation
    'gold_category': pd.DataFrame,   # Category aggregation
}
```

**Gold DataFrame schemas:**

**`gold_daily` – Daily aggregation:**
```
order_date          date
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
unique_customers    int64
unique_regions      int64
unique_categories   int64
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_weekly` – Weekly aggregation (ISO week):**
```
year_week           str       (e.g. "2025-W03")
week_start          date      (Monday of the week)
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
unique_customers    int64
unique_regions      int64
unique_categories   int64
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_monthly` – Monthly aggregation:**
```
year_month          str       (e.g. "2025-01")
month_start         date      (first day of month)
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
unique_customers    int64
unique_regions      int64
unique_categories   int64
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_yearly` – Yearly aggregation:**
```
year                int32
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
unique_customers    int64
unique_regions      int64
unique_categories   int64
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_region` – Regional aggregation:**
```
region              str
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
report_date         date
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_category` – Category aggregation:**
```
category            str
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
report_date         date
_pipeline_run_id    str
_gold_processed_at  str
```

**Fallback logic for tables without `order_date`:**

```python
# If source table has no order_date:
# 1. Try using created_at (extract date part)
# 2. If also missing: use today's date
```

---

### Block 4: `bronze_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/bronze_to_rustfs.py`

**Description:** Writes the raw DataFrame (from extract_postgres) to RustFS bronze bucket as Parquet.

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | S3 endpoint |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | S3 credentials |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | S3 credentials |
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Bucket name |

**File path convention:**
```
bronze/demo/dt=YYYY-MM-DD/<run_id>.parquet
```

---

### Block 5: `silver_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/silver_to_rustfs.py`

**Description:** Writes the Silver DataFrame to RustFS silver bucket.

**Environment variables:** Same as `bronze_to_rustfs.py` but uses `RUSTFS_SILVER_BUCKET`.

**File path convention:**
```
silver/demo/dt=YYYY-MM-DD/<run_id>.parquet
```

---

### Block 6: `gold_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/gold_to_rustfs.py`

**Description:** Writes 6 Gold DataFrames to RustFS gold bucket as separate files.

**File path convention:**
```
gold/demo_daily/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_weekly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_monthly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_yearly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_region/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_category/dt=YYYY-MM-DD/<run_id>.parquet
```

---

### Block 7: `load_to_clickhouse.py` (Data Exporter)

**File:** `mage/data_exporters/load_to_clickhouse.py`

**Description:** Reads data from RustFS (silver + gold) and INSERTs into ClickHouse. **Does NOT use in-memory data from the pipeline** – this is a key feature of the lakehouse architecture.

**Environment variables:**

| Variable | Container Default | Description |
|----------|-----------------|-------------|
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | ClickHouse hostname |
| `CLICKHOUSE_TCP_PORT` | `9000` | ClickHouse TCP port (inside network) |
| `CLICKHOUSE_DB` | `analytics` | Target database |
| `CLICKHOUSE_USER` | `default` | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | *(empty)* | ClickHouse password |

**Process:**

```
1. Connect to ClickHouse
2. Create tables if they don't exist (idempotent DDL)
3. Read latest silver Parquet from RustFS
4. INSERT into analytics.silver_demo
5. Read latest 6 gold Parquet files from RustFS
6. INSERT into analytics.gold_demo_daily/weekly/monthly/yearly/by_region/by_category
7. INSERT into analytics.pipeline_runs (run metadata)
```

**Data type handling notes:**
- Datetime columns → Python `datetime` objects (required by ClickHouse)
- Date columns → Python `date` objects
- Object columns → `str`, with `None/nan/NaT` → `None`
- Numpy scalars → Python native types (`.item()`)

**Output:** `{}` (empty dict) – by design, no data is passed downstream.

---

## 3. Pipeline 2: etl_csv_upload_to_reporting

**File:** `mage/pipelines/etl_csv_upload_to_reporting/`
**Schedule:** Every 5 minutes (cron: `*/5 * * * *`)
**Source:** CSV files in RustFS bronze bucket
**Destination:** RustFS silver + ClickHouse (metrics, events, clean rows)

---

### Block 1: `extract_csv_from_rustfs.py` (Data Loader)

**File:** `mage/data_loaders/extract_csv_from_rustfs.py`

**Description:** Scans the bronze bucket for unprocessed CSV files (no record in `csv_upload_events` with `status='success'`).

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | S3 endpoint |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | Credentials |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | Credentials |
| `CSV_UPLOAD_BUCKET` | `bronze` | Bucket to scan |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Priority prefix |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | Scan entire bucket |
| `CSV_UPLOAD_SEPARATOR` | `,` | CSV delimiter |
| `CSV_UPLOAD_ENCODING` | `utf-8` | File encoding |
| `CSV_UPLOAD_SCAN_LIMIT` | `200` | Max files to scan |
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | Used to check if already processed |

**"Already processed" logic:** Query ClickHouse `csv_upload_events` – if a record with `source_key + etag + status='success'` exists, the file was already processed and is skipped.

**File priority logic:**
1. Files under `CSV_UPLOAD_PREFIX` (high priority)
2. Files outside the prefix (if `CSV_UPLOAD_ALLOW_ANYWHERE=true`)
3. Sorted by `LastModified` (oldest first)
4. Only **1 file** per run

**Output when a new file is found:**
```python
{
    'skip': False,
    'dataframe': pd.DataFrame,           # CSV data read
    'bucket': 'bronze',
    'source_key': 'csv_upload/data.csv', # Path in bucket
    'source_etag': 'abc123...',          # File ETag
    'source_size': 12345,                # Size in bytes
    'source_last_modified': '2024-01-01T00:00:00Z',
    'pipeline_run_id': 'uuid-...',
    'raw_rows': 1000,
}
```

**Output when no new files are found:**
```python
{'skip': True, 'message': 'no new csv'}
```

---

### Block 2: `clean_csv_for_reporting.py` (Transformer)

**File:** `mage/transformers/clean_csv_for_reporting.py`

**Description:** Cleans CSV upload data using flexible rules (schema-agnostic).

**No environment variables.**

**Processing steps:**

| Step | Processing | Description |
|------|-----------|-------------|
| 1 | Skip check | If `data.get('skip')` is True, return data unchanged |
| 2 | Normalize headers | Lowercase, strip whitespace, replace spaces with `_` |
| 3 | Drop empty rows | Remove rows that are all `NaN` |
| 4 | Strip string columns | Trim whitespace from all string columns |
| 5 | Drop duplicates | Remove completely duplicate rows |
| 6 | Add metadata | `_row_number` (1-indexed) |
| 7 | Calculate metrics | `raw_rows`, `cleaned_rows`, `dropped_rows`, `duplicate_rows`, `null_cells` |

**Output:** Dict from the extractor + `quality_metrics`:
```python
{
    **data_from_extractor,    # All fields from extractor
    'dataframe': cleaned_df,  # Cleaned DataFrame
    'quality_metrics': {
        'raw_rows': int,
        'cleaned_rows': int,
        'dropped_rows': int,
        'duplicate_rows': int,
        'null_cells': int,
        'processed_at': 'ISO timestamp',
    }
}
```

---

### Block 3: `csv_to_rustfs_silver.py` (Data Exporter)

**File:** `mage/data_exporters/csv_to_rustfs_silver.py`

**Description:** Writes the cleaned CSV DataFrame to RustFS silver layer as Parquet.

**File path convention:**
```
silver/csv_upload/dt=YYYY-MM-DD/<run_id>.parquet
```

---

### Block 4: `load_csv_reporting_clickhouse.py` (Data Exporter)

**File:** `mage/data_exporters/load_csv_reporting_clickhouse.py`

**Description:** Reads the cleaned CSV from RustFS silver and loads it into 4 ClickHouse tables.

**Tables updated:**

| Table | Data | Description |
|-------|------|-------------|
| `analytics.csv_clean_rows` | 1 row per CSV row | JSON of each cleaned row |
| `analytics.csv_quality_metrics` | 1 row per file | Quality metrics |
| `analytics.csv_upload_events` | 1 row per run | Processing status (success/failed) |
| `analytics.pipeline_runs` | 1 row per run | Run history |

**Note:** If ClickHouse insert fails, `status='failed'` is still written to `csv_upload_events` so the file is retried next time (not permanently skipped).

---

## 4. I/O Configuration (io_config.yaml)

**File:** `mage/io_config.yaml`

This file defines connection "profiles" for Mage. Each profile is a set of credentials that can be selected in a Data Loader/Exporter.

```yaml
version: 0.1.1

# Default profile: Mage's internal metadata DB
default:
  POSTGRES_DBNAME: "{{ env_var('MAGE_DB_NAME') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('MAGE_DB_PASSWORD') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: public
  POSTGRES_USER: "{{ env_var('MAGE_DB_USER') }}"
  POSTGRES_CONNECTION_METHOD: direct

# ETL data source profile
source_db:
  POSTGRES_DBNAME: "{{ env_var('POSTGRES_DB') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('POSTGRES_PASSWORD') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: public
  POSTGRES_USER: "{{ env_var('POSTGRES_USER') }}"
  POSTGRES_CONNECTION_METHOD: direct

# User's custom workspace profile
custom_db:
  POSTGRES_DBNAME: "{{ env_var('CUSTOM_DB_NAME', '') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('CUSTOM_DB_PASSWORD', '') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: "{{ env_var('CUSTOM_SCHEMA', 'public') }}"
  POSTGRES_USER: "{{ env_var('CUSTOM_DB_USER', '') }}"
  POSTGRES_CONNECTION_METHOD: direct

# ClickHouse profile
clickhouse:
  CLICKHOUSE_DATABASE: "{{ env_var('CLICKHOUSE_DB') }}"
  CLICKHOUSE_HOST: dlh-clickhouse
  CLICKHOUSE_HTTP_PORT: 8123
  CLICKHOUSE_PASSWORD: "{{ env_var('CLICKHOUSE_PASSWORD') }}"
  CLICKHOUSE_TCP_PORT: 9000
  CLICKHOUSE_USERNAME: "{{ env_var('CLICKHOUSE_USER') }}"
```

**Using profiles in the Mage UI:**
- When creating a PostgreSQL Data Loader: select the `source_db` or `custom_db` profile
- When creating a ClickHouse Data Exporter: select the `clickhouse` profile

---

## 5. Adding a New Source Table

### Method 1: Use `SOURCE_TABLE` (simplest)

```bash
# In .env
SOURCE_TABLE=my_orders_table
SOURCE_DB_NAME=my_business_db
SOURCE_DB_USER=my_db_user
SOURCE_DB_PASSWORD=my_password
SOURCE_SCHEMA=sales
```

The pipeline will extract the entire `sales.my_orders_table` table.

### Method 2: Add to `SOURCE_TABLE_CANDIDATES`

```bash
# In .env – pipeline will auto-find the first existing table
SOURCE_TABLE_CANDIDATES=Demo,test_projects,my_orders,transactions
```

### Method 3: Customize `extract_postgres.py`

For more complex queries (filters, joins, custom columns), edit the file:

```python
# mage/data_loaders/extract_postgres.py
# Change the query:
query = sql.SQL(
    'SELECT id, name, value, created_at FROM {}.{} WHERE status = %s'
).format(
    sql.Identifier(schema),
    sql.Identifier(resolved_table),
)
df = pd.read_sql(query.as_string(conn), conn, params=['active'])
```

### Method 4: Customize `transform_silver.py` for a new schema

If the source table has different columns than the Demo table, update the transformer:

```python
# Add processing for new columns
if 'phone_number' in df.columns:
    # Normalize phone numbers
    df['phone_number'] = df['phone_number'].str.replace(r'[^\d+]', '', regex=True)

if 'order_amount' in df.columns:
    df['order_amount'] = pd.to_numeric(df['order_amount'], errors='coerce')
    df.loc[df['order_amount'] < 0, 'order_amount'] = None
```

---

## 6. Customizing the Pipeline

### Adding a new transform step

1. Create a new file in `mage/transformers/`:

```python
# mage/transformers/enrich_with_geo.py
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer

@transformer
def enrich_with_geo(df: pd.DataFrame, *args, **kwargs):
    """Add geographic information from region code."""
    region_map = {
        'hn': 'Hanoi',
        'hcm': 'Ho Chi Minh City',
        'dn': 'Da Nang',
    }
    if 'region_code' in df.columns:
        df['region_name'] = df['region_code'].map(region_map)
    return df
```

2. Open Mage UI (http://localhost:26789)
3. Go to the `etl_postgres_to_lakehouse` pipeline
4. Click "Add block" → select the new transformer file
5. Drag and drop to arrange the order

### Changing the schedule

```yaml
# In mage/pipelines/etl_postgres_to_lakehouse/metadata.yaml
# Find schedule and change the cron expression
schedule:
  - cron: "0 */6 * * *"   # Every 6 hours → change to:
  # - cron: "0 2 * * *"   # Daily at 2:00 AM
  # - cron: "0 */1 * * *" # Every hour
  # - cron: "*/30 * * * *"# Every 30 minutes
```

Or via Mage UI: Pipelines → Triggers → edit the Schedule.

### Adding failure notifications

In Mage UI: Settings → Alerts → add a Slack/Teams/Email webhook.

---

## 7. Error Handling and Logging

### Log structure

All blocks use a consistent log format:

```python
print(f"[block_name] key=value key=value ...")
```

Example:
```
[extract_postgres] run_id=abc123  rows=100000  table=public.Demo
[transform_silver] Duplicates removed: 123
[transform_silver] Silver rows ready: 99877
[transform_gold] daily=365 rows  weekly=52 rows  monthly=12 rows  yearly=3 rows  by_region=8 rows  by_category=12 rows
[load_to_clickhouse] From RustFS Silver → silver_demo: 99877 rows
[load_to_clickhouse] COMPLETE: run_id=abc123  status=success  silver=99877  daily=365  weekly=52  monthly=12  yearly=3
```

### Viewing pipeline logs

```bash
# View Mage logs in real-time
docker compose logs -f mage

# Filter logs for a specific block
docker compose logs mage | grep "\[extract_postgres\]"
docker compose logs mage | grep "ERROR"

# View run history in ClickHouse
docker compose exec clickhouse clickhouse-client --query "
SELECT
    run_id,
    pipeline_name,
    status,
    rows_silver,
    rows_gold_daily,
    started_at,
    dateDiff('second', started_at, ended_at) AS duration_seconds,
    error_message
FROM analytics.pipeline_runs
ORDER BY started_at DESC
LIMIT 10
FORMAT Pretty"
```

### Handling pipeline failures

```bash
# View failure reason
docker compose exec clickhouse clickhouse-client --query "
SELECT error_message, started_at
FROM analytics.pipeline_runs
WHERE status = 'failed'
ORDER BY started_at DESC
LIMIT 5
FORMAT Pretty"

# Re-run the pipeline
docker compose exec mage mage run etl_postgres_to_lakehouse

# If ClickHouse tables are corrupted: rebuild from RustFS
docker compose exec clickhouse clickhouse-client --query "TRUNCATE TABLE analytics.silver_demo"
docker compose exec mage mage run etl_postgres_to_lakehouse
# load_to_clickhouse will re-read from RustFS
```

### Handling stuck CSV files

If the pipeline writes `status='failed'` to `csv_upload_events`, the file will be retried on the next run. If a file is corrupted or in the wrong format:

```bash
# View failed CSV files
docker compose exec clickhouse clickhouse-client --query "
SELECT source_key, status, error_message, processed_at
FROM analytics.csv_upload_events
WHERE status = 'failed'
ORDER BY processed_at DESC
FORMAT Pretty"

# To skip a file permanently: delete it from RustFS via the Web Console
```

---

## 8. ClickHouse Schema

### analytics.silver_demo

Data from the PostgreSQL Demo table after cleaning.

```sql
CREATE TABLE analytics.silver_demo
(
    id Nullable(Int64),
    name Nullable(String),
    category Nullable(String),
    value Nullable(Float64),
    quantity Nullable(Int32),
    order_date Nullable(Date),
    region Nullable(String),
    status Nullable(String),
    customer_email Nullable(String),
    notes Nullable(String),
    created_at Nullable(DateTime64(3)),
    _pipeline_run_id String DEFAULT '',
    _source_table String DEFAULT 'Demo',
    _silver_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(toDateTime(_silver_processed_at))
ORDER BY (_silver_processed_at, _pipeline_run_id);
```

### analytics.gold_demo_daily

```sql
CREATE TABLE analytics.gold_demo_daily
(
    order_date Date,
    order_count Int64,
    total_revenue Float64,
    avg_order_value Float64,
    total_quantity Int64,
    unique_customers Int64,
    unique_regions Int64,
    unique_categories Int64,
    _pipeline_run_id String DEFAULT '',
    _gold_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (order_date, _pipeline_run_id);
```

### analytics.gold_demo_weekly

```sql
CREATE TABLE analytics.gold_demo_weekly
(
    year_week String,
    week_start Date,
    order_count Int64,
    total_revenue Float64,
    avg_order_value Float64,
    total_quantity Int64,
    unique_customers Int64,
    unique_regions Int64,
    unique_categories Int64,
    _pipeline_run_id String DEFAULT '',
    _gold_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYear(week_start)
ORDER BY (year_week, week_start, _pipeline_run_id);
```

### analytics.gold_demo_monthly

```sql
CREATE TABLE analytics.gold_demo_monthly
(
    year_month String,
    month_start Date,
    order_count Int64,
    total_revenue Float64,
    avg_order_value Float64,
    total_quantity Int64,
    unique_customers Int64,
    unique_regions Int64,
    unique_categories Int64,
    _pipeline_run_id String DEFAULT '',
    _gold_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYear(month_start)
ORDER BY (year_month, month_start, _pipeline_run_id);
```

### analytics.gold_demo_yearly

```sql
CREATE TABLE analytics.gold_demo_yearly
(
    year Int32,
    order_count Int64,
    total_revenue Float64,
    avg_order_value Float64,
    total_quantity Int64,
    unique_customers Int64,
    unique_regions Int64,
    unique_categories Int64,
    _pipeline_run_id String DEFAULT '',
    _gold_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY (year, _pipeline_run_id);
```

### analytics.csv_quality_metrics

```sql
CREATE TABLE analytics.csv_quality_metrics
(
    pipeline_run_id String,
    source_key String,          -- S3 path
    source_etag String,         -- File ETag (fingerprint)
    raw_rows Int64,             -- Row count before cleaning
    cleaned_rows Int64,         -- Row count after cleaning
    dropped_rows Int64,         -- Rows removed (raw - cleaned)
    duplicate_rows Int64,       -- Duplicate rows removed
    null_cells Int64,           -- Total null cells in DataFrame
    processed_at DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(processed_at)
ORDER BY (processed_at, source_key);
```

### analytics.pipeline_runs

```sql
CREATE TABLE analytics.pipeline_runs
(
    run_id String,
    pipeline_name String,
    status String,              -- 'success' or 'failed'
    started_at DateTime64(3),
    ended_at Nullable(DateTime64(3)),
    rows_extracted Int64 DEFAULT 0,
    rows_silver Int64 DEFAULT 0,
    rows_gold_daily Int64 DEFAULT 0,
    rows_gold_region Int64 DEFAULT 0,
    rows_gold_category Int64 DEFAULT 0,
    error_message Nullable(String),
    _created_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY started_at;
```

### Useful queries

```sql
-- Revenue summary by day (last 7 days)
SELECT order_date, total_revenue, order_count
FROM analytics.gold_demo_daily
WHERE order_date >= today() - 7
ORDER BY order_date;

-- Revenue summary by week
SELECT year_week, week_start, total_revenue, order_count
FROM analytics.gold_demo_weekly
ORDER BY year_week DESC
LIMIT 12;

-- Revenue summary by month
SELECT year_month, month_start, total_revenue, order_count
FROM analytics.gold_demo_monthly
ORDER BY year_month DESC;

-- Revenue summary by year
SELECT year, total_revenue, order_count, avg_order_value
FROM analytics.gold_demo_yearly
ORDER BY year DESC;

-- Top categories by revenue
SELECT category, sum(total_revenue) AS revenue
FROM analytics.gold_demo_by_category
GROUP BY category
ORDER BY revenue DESC;

-- CSV quality summary
SELECT
    source_key,
    raw_rows,
    cleaned_rows,
    round(cleaned_rows * 100.0 / raw_rows, 1) AS quality_pct,
    duplicate_rows,
    processed_at
FROM analytics.csv_quality_metrics
ORDER BY processed_at DESC
LIMIT 20;

-- Pipeline success rate (last 7 days)
SELECT
    pipeline_name,
    countIf(status = 'success') AS success,
    countIf(status = 'failed') AS failed,
    round(countIf(status='success') * 100.0 / count(), 1) AS success_rate
FROM analytics.pipeline_runs
WHERE started_at >= now() - INTERVAL 7 DAY
GROUP BY pipeline_name;
```

---

*See also: [README.md](../README.md) | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md)*

# mage/

Mage.ai project directory. This folder is mounted into the `dlh-mage` container at `/home/src`.

## Structure

```
mage/
├── io_config.yaml          # Mage I/O profiles (PostgreSQL + ClickHouse connection configs)
├── requirements.txt        # Python dependencies installed inside the Mage container
├── pipelines/              # Pipeline definitions (metadata + triggers)
│   ├── etl_postgres_to_lakehouse/
│   ├── etl_excel_to_lakehouse/
│   └── etl_csv_upload_to_reporting/
├── data_loaders/           # Extract blocks (source → DataFrame)
├── transformers/           # Transform blocks (clean, aggregate)
├── data_exporters/         # Load blocks (DataFrame → RustFS / ClickHouse)
├── utils/                  # Shared utilities
│   ├── __init__.py
│   └── rustfs_layer_reader.py   # Helper functions for reading RustFS lake layers
└── bronze_local/           # Local staging area for file uploads (used by watchers)
```

---

## Pipelines

| Pipeline | Trigger | Source | Destination |
|----------|---------|--------|-------------|
| `etl_postgres_to_lakehouse` | Scheduled (every 6 h) | PostgreSQL table | RustFS Bronze/Silver/Gold + ClickHouse |
| `etl_excel_to_lakehouse` | Manual / watcher | Excel files in RustFS `bronze/excel_upload/` | ClickHouse `project_reports`, `gold_projects_summary`, `gold_workload_report` |
| `etl_csv_upload_to_reporting` | Scheduled (every 5 min) | CSV files in RustFS `bronze/csv_upload/` | RustFS Silver + ClickHouse `csv_clean_rows` |

---

## I/O Configuration (`io_config.yaml`)

Mage uses `io_config.yaml` to define named connection profiles. Three profiles are configured:

| Profile | Database | Used by |
|---------|----------|---------|
| `default` | `MAGE_DB_NAME` (Mage metadata DB) | Mage internal use |
| `source_db` | `POSTGRES_DB` (operational DB) | ETL extractor blocks |
| `custom_db` | `CUSTOM_DB_NAME` (optional workspace DB) | ETL when custom workspace is configured |
| `clickhouse` | `CLICKHOUSE_DB` | Data loader/exporter blocks that read/write ClickHouse |

All credentials are resolved from environment variables at runtime using Mage's
`{{ env_var('VAR_NAME') }}` syntax.

---

## Key Blocks

### Data Loaders (Extract)

| File | Description |
|------|-------------|
| `data_loaders/extract_postgres.py` | Connects to PostgreSQL, auto-discovers source table, returns DataFrame with lineage metadata |
| `data_loaders/extract_excel_from_rustfs.py` | Lists and downloads Excel files from RustFS `bronze/excel_upload/`, returns concatenated DataFrame |
| `data_loaders/extract_csv_from_rustfs.py` | Lists and downloads CSV files from RustFS `bronze/csv_upload/`, returns raw DataFrame |

**Table selection logic in `extract_postgres.py`:**

```
1. If SOURCE_TABLE is set → use that exact table
2. Otherwise → try each name in SOURCE_TABLE_CANDIDATES (case-insensitive)
3. If none found → raise ValueError listing all available tables
```

### Transformers (Clean / Aggregate)

| File | Description |
|------|-------------|
| `transformers/transform_silver.py` | Deduplication, type casting, email validation, text normalisation |
| `transformers/transform_gold.py` | Aggregation into daily / weekly / monthly / yearly / region / category slices |
| `transformers/clean_excel_data.py` | Strips junk rows (empty IDs), normalises Vietnamese status values, fills missing assignees |
| `transformers/clean_csv_for_reporting.py` | Cleans CSV data, removes empty rows, normalises column names |

### Data Exporters (Load)

| File | Description |
|------|-------------|
| `data_exporters/bronze_to_rustfs.py` | Writes raw DataFrame as Parquet to `s3://bronze/{table}/dt=YYYY-MM-DD/{run_id}.parquet` |
| `data_exporters/silver_to_rustfs.py` | Writes cleaned DataFrame as Parquet to `s3://silver/{table}/dt=YYYY-MM-DD/{run_id}.parquet` |
| `data_exporters/gold_to_rustfs.py` | Writes all Gold aggregation DataFrames to `s3://gold/{table}_{granularity}/dt=YYYY-MM-DD/` |
| `data_exporters/load_to_clickhouse.py` | Reads Silver + Gold from RustFS, inserts into ClickHouse using `ReplacingMergeTree` dedup |
| `data_exporters/csv_to_rustfs_silver.py` | Writes cleaned CSV DataFrame to RustFS Silver layer |
| `data_exporters/load_csv_reporting_clickhouse.py` | Loads cleaned CSV Silver data into ClickHouse `csv_clean_rows` |
| `data_exporters/load_excel_to_clickhouse.py` | Loads cleaned Excel data into ClickHouse `project_reports` and gold summary tables |

---

## Utilities (`utils/rustfs_layer_reader.py`)

Provides Python functions for reading data back from RustFS lake layers. Used by
load blocks and any custom scripts that need to re-read persisted data.

Quick reference:

```python
from utils.rustfs_layer_reader import (
    read_latest_bronze,
    read_latest_silver,
    read_all_gold,
    read_latest_gold_daily,
    read_latest_csv_silver,
    read_latest_layer,          # generic: (bucket, prefix, date_str=None)
    list_layer_partitions,      # list available dt=YYYY-MM-DD partitions
)
```

See [docs/RUSTFS_LAYER_READER_GUIDE.md](../docs/RUSTFS_LAYER_READER_GUIDE.md) for full API documentation.

---

## Adding a New Source Table

1. Set `SOURCE_TABLE=your_table_name` in `.env` (or add to `SOURCE_TABLE_CANDIDATES`).
2. Ensure the table exists in PostgreSQL under the configured `SOURCE_SCHEMA`.
3. If the table has different column names, update `transform_silver.py` accordingly.
4. Run `bash scripts/stackctl.sh redeploy` then trigger the pipeline.

See [docs/PIPELINE_GUIDE.md](../docs/PIPELINE_GUIDE.md) for step-by-step instructions.

---

## Developing Pipeline Blocks

Pipeline blocks are standard Python functions with Mage decorators.

```python
# data_loaders/my_loader.py
from mage_ai.data_preparation.decorators import data_loader

@data_loader
def load_data(*args, **kwargs):
    # return a pandas DataFrame
    return df
```

- Blocks run inside the `dlh-mage` container.
- All environment variables from `.env` / `docker-compose.yaml` are available via `os.environ`.
- `io_config.yaml` profiles are accessible via Mage's built-in connector classes.
- Install extra Python packages in `requirements.txt` (applied on next container start).

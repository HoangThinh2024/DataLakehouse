# Developer Guide

This page is for contributors who want to add new data sources, create new pipelines,
or modify existing ETL blocks.

---

## Repository Structure

```
DataLakehouse/
├── docker-compose.yaml         # Full stack definition
├── .env.example                # Environment variable template
├── pyproject.toml              # Host-side Python dependencies (uv)
│
├── clickhouse/                 # ClickHouse init SQL (schema DDL)
├── grafana/                    # Grafana provisioning (datasources, dashboards)
├── mage/                       # Mage.ai project: pipelines, blocks, utilities
│   ├── io_config.yaml          # Mage I/O connection profiles
│   ├── requirements.txt        # Python packages installed in Mage container
│   ├── pipelines/              # Pipeline definitions (metadata + triggers)
│   ├── data_loaders/           # Extract blocks (source → DataFrame)
│   ├── transformers/           # Transform blocks (clean, aggregate)
│   ├── data_exporters/         # Load blocks (DataFrame → RustFS / ClickHouse)
│   └── utils/
│       └── rustfs_layer_reader.py   # Helper API for reading lake layers
├── postgres/                   # PostgreSQL init scripts and sample data
├── superset/                   # Superset configuration
├── samples/                    # Sample Excel/CSV files for testing
│
├── scripts/                    # Operational scripts
└── docs/                       # Detailed reference documentation
```

---

## Setting Up a Development Environment

### 1. Install host dependencies

```bash
uv sync --all-groups
```

### 2. Start the stack

```bash
bash scripts/setup.sh
# or manually:
docker network create web_network
docker compose up -d
```

### 3. Verify the stack is healthy

```bash
bash scripts/stackctl.sh health
```

---

## Developing Pipeline Blocks

Pipeline blocks are standard Python functions decorated with Mage decorators. They run inside the `dlh-mage` container.

### Block types

| Type | Decorator | Purpose |
|------|-----------|---------|
| Data Loader | `@data_loader` | Extract data from a source; return a DataFrame |
| Transformer | `@transformer` | Clean or aggregate a DataFrame; return a DataFrame |
| Data Exporter | `@data_exporter` | Write a DataFrame to a destination |

### Example: data loader

```python
# mage/data_loaders/my_loader.py
from mage_ai.data_preparation.decorators import data_loader
import pandas as pd

@data_loader
def load_data(*args, **kwargs):
    # All .env variables are available via os.environ
    import os
    pg_host = os.environ['POSTGRES_HOST']
    # ... connect and fetch ...
    return df  # pandas DataFrame
```

### Example: transformer

```python
# mage/transformers/my_transformer.py
from mage_ai.data_preparation.decorators import transformer
import pandas as pd

@transformer
def transform(df: pd.DataFrame, *args, **kwargs):
    df = df.drop_duplicates()
    df['column'] = df['column'].str.strip()
    return df
```

### Example: data exporter

```python
# mage/data_exporters/my_exporter.py
from mage_ai.data_preparation.decorators import data_exporter

@data_exporter
def export_data(df, *args, **kwargs):
    # Write to RustFS, ClickHouse, etc.
    pass
```

### Installing extra Python packages

Add the package to `mage/requirements.txt`. It will be installed on the next container start:

```bash
docker compose up -d dlh-mage
```

---

## Reading Data from RustFS Lake Layers

Use the shared utility in `mage/utils/rustfs_layer_reader.py`:

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

# Read latest silver data
df = read_latest_silver(table='Demo')

# Read all gold aggregations for a table
gold_dict = read_all_gold(table='Demo')
# gold_dict keys: gold_daily, gold_weekly, gold_monthly, gold_yearly,
#                 gold_region, gold_category

# Read a specific partition
df = read_latest_layer(bucket='silver', prefix='Demo', date_str='2024-11-01')
```

> See [docs/RUSTFS_LAYER_READER_GUIDE.md](../docs/RUSTFS_LAYER_READER_GUIDE.md) for the full API reference.

---

## Adding a New Source Table

1. Ensure the table exists in PostgreSQL under `SOURCE_SCHEMA` (default: `public`).

2. Configure the source table in `.env`:
   ```ini
   SOURCE_TABLE=your_table_name
   # Or use auto-detection fallbacks:
   SOURCE_TABLE_CANDIDATES=Demo,your_table_name,transactions
   ```

3. If the table has different column names, update `mage/transformers/transform_silver.py` to handle the schema.

4. Redeploy and run the pipeline:
   ```bash
   bash scripts/stackctl.sh redeploy
   uv run python scripts/run_etl_and_dashboard.py --auto --table your_table_name
   ```

---

## Adding a New Pipeline

1. **Create the pipeline** in the Mage UI (http://localhost:26789) or add a folder under `mage/pipelines/`.

2. **Create block files** in the appropriate `mage/data_loaders/`, `mage/transformers/`, or `mage/data_exporters/` directories.

3. **Set a schedule** in the Mage UI or edit the pipeline's `triggers.yaml`.

4. **Add ClickHouse tables** if needed in `clickhouse/init/001_analytics_schema.sql`. Note: DDL changes only apply on first volume creation; use `reset --hard` + `setup.sh` to re-initialise.

5. **Test** the pipeline via the Mage UI or CLI:
   ```bash
   docker compose exec dlh-mage magic run your_new_pipeline
   ```

---

## ClickHouse Schema Changes

Schema DDL is in `clickhouse/init/001_analytics_schema.sql`.

> **Important:** ClickHouse runs init scripts only when the volume is first created.
> To re-apply schema changes after the volume already exists:
> ```bash
> bash scripts/stackctl.sh reset --hard
> bash scripts/setup.sh
> ```

For production-safe migrations, use ClickHouse `ALTER TABLE` statements via CloudBeaver or `clickhouse-client` instead:

```sql
ALTER TABLE analytics.silver_demo ADD COLUMN new_col String DEFAULT '';
```

---

## Environment Variables in Blocks

All variables from `.env` / `docker-compose.yaml` are available inside Mage blocks via `os.environ`:

```python
import os

pg_host = os.environ['POSTGRES_HOST']
ch_host = os.environ['CLICKHOUSE_HOST']
s3_endpoint = os.environ['RUSTFS_ENDPOINT']
```

`io_config.yaml` profiles can be used with Mage's built-in connector classes for cleaner connection management.

---

## Writing Sample Data

Sample data files are in `samples/`. To load the PostgreSQL sample dataset:

```bash
docker exec -i dlh-postgres psql -U postgres -d datalakehouse \
  < postgres/init/002_sample_data.sql
```

---

## Running the Architecture Validator

After making changes, verify the stack is healthy end-to-end:

```bash
uv run python scripts/verify_lakehouse_architecture.py
# or:
bash scripts/stackctl.sh check-system
```

---

## Useful Scripts

| Script | Description |
|--------|-------------|
| `scripts/run_etl_and_dashboard.py` | End-to-end ETL + Superset provisioning |
| `scripts/create_superset_demo_dashboard.py` | Programmatic Superset dashboard creation via API |
| `scripts/demo_to_lakehouse.py` | Load sample data into PostgreSQL and run ETL |
| `scripts/verify_lakehouse_architecture.py` | End-to-end architecture health check |
| `scripts/maintenance_tasks.py` | ClickHouse backup + RustFS cleanup |
| `scripts/realtime_watcher.sh` | File-upload event watcher → ETL trigger |

---

> See [docs/PIPELINE_GUIDE.md](../docs/PIPELINE_GUIDE.md) for detailed block-by-block documentation.
> See [docs/RUSTFS_LAYER_READER_GUIDE.md](../docs/RUSTFS_LAYER_READER_GUIDE.md) for the RustFS Python API.

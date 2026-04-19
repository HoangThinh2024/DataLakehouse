# DataLakehouse – Architecture (Updated)

## 1. Layers

1. INGEST
   - Web upload / API / manual tools

2. STORAGE
   - PostgreSQL: central metadata/config + operational source data
   - RustFS: object storage for Bronze/Silver/Gold (Parquet files)
   - ClickHouse: OLAP serving engine

3. PROCESS
   - Mage.ai: orchestration + ETL pipeline (scheduled every 6 hours)

4. SERVING
   - NocoDB
   - Nginx Proxy Manager

5. REPORT
   - Superset: business analytics dashboard (connected to ClickHouse)
   - Grafana: pipeline monitoring dashboard (connected to ClickHouse)

## 2. Data Flow

```
PostgreSQL (public."Demo")
    │
    ▼ [Mage: extract_postgres]
Bronze bucket (RustFS)         ← raw Parquet
    │
    ▼ [Mage: transform_silver]
Silver bucket (RustFS)         ← cleaned, typed Parquet
    │
    ▼ [Mage: transform_gold]
Gold bucket  (RustFS)          ← aggregated Parquet (daily/weekly/monthly/yearly/region/category)
    │
    ▼ [Mage: load_to_clickhouse]
ClickHouse analytics DB        ← silver_demo, gold_demo_*, pipeline_runs
    │
    ├──▶ Superset  (business dashboards)
    └──▶ Grafana   (ETL monitoring dashboard)
```

## 3. Mage.ai ETL Pipeline

Pipeline: `etl_postgres_to_lakehouse`
Schedule: every 6 hours (`0 */6 * * *`)

Blocks (in order):
| Block | Type | Description |
|---|---|---|
| `extract_postgres` | data_loader | Extract from PostgreSQL public."Demo" |
| `bronze_to_rustfs` | data_exporter | Save raw Parquet to bronze/ |
| `transform_silver` | transformer | Clean: dedup, cast types, validate email, normalize text |
| `silver_to_rustfs` | data_exporter | Save cleaned Parquet to silver/ |
| `transform_gold` | transformer | Aggregate: by day / week / month / year / region / category |
| `gold_to_rustfs` | data_exporter | Save aggregated Parquet to gold/ |
| `load_to_clickhouse` | data_exporter | Load silver + gold into ClickHouse; write pipeline_runs |

## 4. ClickHouse Schema

Database: `analytics`

| Table | Layer | Description |
|---|---|---|
| `silver_demo` | Silver | Typed, cleaned data |
| `gold_demo_daily` | Gold | Daily sales metrics |
| `gold_demo_weekly` | Gold | Weekly sales metrics (ISO week) |
| `gold_demo_monthly` | Gold | Monthly sales metrics |
| `gold_demo_yearly` | Gold | Yearly sales metrics |
| `gold_demo_by_region` | Gold | Per-region metrics |
| `gold_demo_by_category` | Gold | Per-category metrics |
| `pipeline_runs` | Monitoring | Run status, row counts, errors |

## 5. Grafana Dashboard

File: `grafana/provisioning/dashboards/lakehouse_monitoring.json`
Datasource: ClickHouse (`analytics.pipeline_runs`)

Panels:
- Total Runs, Last Status, Time Since Last Success (stat panels)
- Row Counts per Run (time series)
- Run Status Distribution (pie chart)
- Recent Pipeline Runs table (last 50 with duration + error)

## 6. Superset Dashboard

Connection string (ClickHouse):
```
clickhousedb://default@dlh-clickhouse:8123/analytics
```
Requires `clickhouse-connect` (installed automatically in the Superset container).

Suggested charts:
- Revenue by Region (bar chart from `gold_demo_by_region`)
- Revenue by Category (pie from `gold_demo_by_category`)
- Daily Revenue Trend (line from `gold_demo_daily`)
- Weekly Revenue Trend (line from `gold_demo_weekly`)
- Monthly Revenue Trend (line from `gold_demo_monthly`)
- Yearly Revenue Summary (bar from `gold_demo_yearly`)
- Order Status Distribution (pie from `silver_demo`)

## 7. RustFS Object Key Convention

```
bronze/demo/dt=YYYY-MM-DD/<run_id>.parquet
silver/demo/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_daily/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_weekly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_monthly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_yearly/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_region/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_category/dt=YYYY-MM-DD/<run_id>.parquet
```

## 8. ClickHouse "Lake Ready" Pattern Applied in This Stack

- RustFS (S3-compatible) is the primary data lake layer.
- ClickHouse is used for analytical serving only, not as a data lake replacement.
- The storage-compute separation design scales well for BI/OLAP workloads.

## 9. Operational Notes

- Container names are prefixed with `dlh-` to avoid conflicts with other environments.
- Port mappings use a custom range to reduce local conflicts.
- Metadata/config is centralized in PostgreSQL for easier operations.
- Mage pipeline code is mounted from `./mage/` (bind mount) for easy version control.
- ClickHouse init SQL in `./clickhouse/init/` runs automatically on first container startup.
- Grafana provisioning in `./grafana/provisioning/` automatically creates datasources and dashboards.

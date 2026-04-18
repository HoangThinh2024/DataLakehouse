# DataLakehouse – Architecture (Updated)

## 1. Layers

1. INGEST
- Web upload / API / manual tools

2. STORAGE
- PostgreSQL: central metadata/config + operational source data
- RustFS: object storage cho Bronze/Silver/Gold (Parquet files)
- ClickHouse: OLAP serving engine

3. PROCESS
- Mage.ai: orchestration + ETL pipeline (scheduled every 6 hours)

4. SERVING
- NocoDB
- Nginx Proxy Manager

5. REPORT
- Superset: business analytics dashboard (kết nối ClickHouse)
- Grafana: pipeline monitoring dashboard (kết nối ClickHouse)

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
Gold bucket  (RustFS)          ← aggregated Parquet (daily/region/category)
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
| `extract_postgres` | data_loader | Extract từ PostgreSQL public."Demo" |
| `bronze_to_rustfs` | data_exporter | Lưu raw Parquet vào bronze/ |
| `transform_silver` | transformer | Làm sạch: dedup, cast types, validate email, normalize text |
| `silver_to_rustfs` | data_exporter | Lưu cleaned Parquet vào silver/ |
| `transform_gold` | transformer | Tổng hợp: by day / region / category |
| `gold_to_rustfs` | data_exporter | Lưu aggregated Parquet vào gold/ |
| `load_to_clickhouse` | data_exporter | Load silver + gold vào ClickHouse; ghi pipeline_runs |

## 4. ClickHouse Schema

Database: `analytics`

| Table | Layer | Description |
|---|---|---|
| `bronze_demo` | Bronze | Raw string columns |
| `silver_demo` | Silver | Typed, cleaned data |
| `gold_demo_daily` | Gold | Daily sales metrics |
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
Requires `clickhouse-connect` (installed automatically in Superset container).

Suggested charts:
- Revenue by Region (bar chart from `gold_demo_by_region`)
- Revenue by Category (pie from `gold_demo_by_category`)
- Daily Revenue Trend (line from `gold_demo_daily`)
- Order Status Distribution (pie from `silver_demo`)

## 7. RustFS Object Key Convention

```
bronze/demo/dt=YYYY-MM-DD/<run_id>.parquet
silver/demo/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_daily/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_region/dt=YYYY-MM-DD/<run_id>.parquet
gold/demo_by_category/dt=YYYY-MM-DD/<run_id>.parquet
```

## 8. ClickHouse "Lake Ready" áp dụng trong stack này

- RustFS (S3-compatible) là lớp data lake chính.
- ClickHouse dùng cho analytical serving, không thay thế data lake.
- Thiết kế tách storage và compute giúp scale tốt hơn cho workload BI/OLAP.

## 9. Operational Notes

- Tên container đã prefixed `dlh-` để tránh đụng môi trường khác.
- Port map dùng dải riêng để giảm xung đột local.
- Metadata/config tập trung vào PostgreSQL cho vận hành dễ hơn.
- Mage pipeline code được mount từ `./mage/` (bind mount) để dễ version control.
- ClickHouse init SQL trong `./clickhouse/init/` chạy tự động khi container khởi tạo lần đầu.
- Grafana provisioning trong `./grafana/provisioning/` tự động tạo datasources và dashboard.


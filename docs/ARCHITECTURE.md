# Architecture

This page describes the system layers, component roles, data flow, and deployment topology of the DataLakehouse stack.

---

## System Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 – INGEST                                                   │
│  PostgreSQL (CDC)  •  Excel/CSV upload                              │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ raw records / events
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 2 – BROKER & STORAGE (Data Lake)                             │
│  Redpanda (Kafka-compatible broker + Tiered Storage)                │
│  RustFS S3-compatible object store                                  │
│    bronze/  →  silver/  →  gold/   (Parquet, partitioned by date)  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ events / parquet
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 3 – PROCESS (ETL & CDC)                                      │
│  Redpanda Connect (ultra-light CDC engine)                          │
│  Mage.ai orchestration engine (batch & dbt)                         │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ unified records
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 4 – SERVING (OLAP Warehouse)                                 │
│  ClickHouse  (columnar, analytics-optimized)                        │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ SQL queries
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 5 – REPORTING                                                │
│  Apache Superset  (business dashboards)                             │
│  Grafana          (operational monitoring)                          │
└─────────────────────────────────────────────────────────────────────┘
```

Supporting infrastructure (cuts across all layers):
- **Redis** – shared cache and queue.
- **Authentik** – centralised identity provider (SSO, RBAC).
- **Redpanda Console** – Web UI for managing topics and events.
- **Data Healer** – autonomous lake-to-warehouse consistency engine.

---

## Component Catalog

| Container | Image | Role | Default Port |
|-----------|-------|------|--------------|
| `dlh-redpanda` | `redpandadata/redpanda:v23.2.19` | Kafka broker with Tiered Storage (Archival to S3) | `29092` |
| `dlh-ingest-cdc` | `redpandadata/connect` | Ultra-light CDC engine (Postgres → ClickHouse/Redpanda) | `4195` |
| `dlh-redpanda-console` | `redpandadata/console` | Web UI for Redpanda topic management | `29080` |
| `dlh-postgres` | `postgres:17-alpine` | Central metadata DB + Source DB (Logical Replication enabled) | `25432` |
| `dlh-rustfs` | `rustfs/rustfs` | S3-compatible object storage (Lake layers) | API `29100` |
| `dlh-clickhouse` | `clickhouse/clickhouse-server` | Columnar OLAP engine for real-time & batch | TCP `29000` |
| `dlh-mage` | `mageai/mageai` | ETL orchestration — batch pipelines + dbt | `26789` |

---

## Data Flow

### 1. Real-time Pipeline (CDC): PostgreSQL → ClickHouse

```
PostgreSQL public.demo (Source)
    │
    ▼ [Redpanda Connect - Go engine]
    ├──▶ [Speed Layer] Direct INSERT into ClickHouse analytics.silver_demo
    └──▶ [Storage Layer] Push to Redpanda Topic: dbserver1.public.demo
            │
            ▼ [Redpanda Tiered Storage]
            Automatically archived to s3://bronze/topics/dbserver1.public.demo/
```

### 2. Batch Pipeline: Excel/CSV → Lakehouse

```
Excel file uploaded locally or to RustFS
    │
    ▼ [scripts/realtime_watcher.sh]
    Triggers Ingestion to RustFS Bronze
    │
    ▼ [Mage.ai Pipeline]
    Bronze (Raw) → Silver (Cleaned) → Gold (Aggregated) → ClickHouse
```

### 3. Unified Serving: dbt Transformations

```
ClickHouse analytics.silver_demo (CDC)
ClickHouse analytics.project_reports (Excel)
    │
    ▼ [dbt Mart: fct_projects_summary]
    Standardises and Unions both sources into a single Reporting Table
    │
    ▼ [Superset Dashboard]
    Real-time unified project visibility
```

### Excel upload → Lakehouse

```
Excel file uploaded to RustFS bronze/excel_upload/
    │
    ▼  [extract_excel_from_rustfs.py]
    ▼  [clean_excel_data.py]
    ▼  [load_excel_to_clickhouse.py]  →  ClickHouse analytics.project_reports
                                          analytics.gold_projects_summary
                                          analytics.gold_workload_report
```

### CSV upload → Reporting

```
CSV file uploaded to RustFS bronze/csv_upload/
    │
    ▼  [extract_csv_from_rustfs.py]
    ▼  [clean_csv_for_reporting.py]
    ▼  [csv_to_rustfs_silver.py]     →  s3://silver/csv_upload/dt=YYYY-MM-DD/
    ▼  [load_csv_reporting_clickhouse.py]  →  ClickHouse analytics.csv_clean_rows
```

---

## Medallion Architecture — Lake Layers

| Layer | Bucket | Contents | Format |
|-------|--------|----------|--------|
| **Bronze** | `s3://bronze/` | Raw records as extracted from source; no changes | Parquet, partitioned by `dt=YYYY-MM-DD` |
| **Silver** | `s3://silver/` | Cleaned data: dedup, type-cast, validated | Parquet, partitioned by `dt=YYYY-MM-DD` |
| **Gold** | `s3://gold/` | Aggregated metrics: daily, weekly, monthly, yearly, by region, by category | Parquet, partitioned by `dt=YYYY-MM-DD` |

> RustFS is the **source of truth**. ClickHouse can be fully rebuilt from RustFS at any time.

---

## ClickHouse Schema

**Database:** `analytics`  
**Engine:** All tables use `ReplacingMergeTree` (deduplication on re-ingestion).

### Primary pipeline tables

| Table | Layer | Description |
|-------|-------|-------------|
| `silver_demo` | Silver | Cleaned, typed rows from PostgreSQL source |
| `gold_demo_daily` | Gold | Daily aggregated sales metrics |
| `gold_demo_weekly` | Gold | Weekly aggregated metrics (ISO week) |
| `gold_demo_monthly` | Gold | Monthly aggregated metrics |
| `gold_demo_yearly` | Gold | Yearly aggregated metrics |
| `gold_demo_by_region` | Gold | Metrics grouped by geographic region |
| `gold_demo_by_category` | Gold | Metrics grouped by product category |
| `pipeline_runs` | Monitoring | Run ID, status, row counts, error messages per execution |

### Excel pipeline tables

| Table | Description |
|-------|-------------|
| `project_reports` | Detailed task rows from each uploaded Excel report |
| `gold_projects_summary` | Per-project KPI summary (completion rate, overdue count) |
| `gold_workload_report` | Per-person workload metrics |

### CSV pipeline tables

| Table | Description |
|-------|-------------|
| `csv_clean_rows` | Cleaned and normalised rows from CSV uploads |

Schema DDL: `clickhouse/init/001_analytics_schema.sql`

---

## PostgreSQL Metadata Databases

Each service has its own isolated PostgreSQL database. The `postgres-bootstrap` init container creates all roles on every `docker compose up`:

| Database | Owner Role | Used by |
|----------|-----------|---------|
| `datalakehouse` | `dlh_admin` | Admin / source data |
| `dlh_mage` | `dlh_mage_user` | Mage pipeline metadata |
| `dlh_superset` | `dlh_superset_user` | Superset dashboard metadata |
| `dlh_grafana` | `dlh_grafana_user` | Grafana settings |
| `dlh_authentik` | `dlh_authentik_user` | Authentik identity data |
| `dlh_custom` | `dlh_custom_user` | Optional business workspace DB |

---

## Redis Database Allocation

| DB Index | Used by |
|----------|---------|
| 0 | Default (unused) |
| 1 | Authentik queue + cache |
| 2 | Superset dashboard/query cache |
| 3 | Superset SQL Lab results backend |

---

## Deployment Topology

All services are deployed via `docker-compose.yaml` on a shared Docker bridge network (`web_network`).

**Port allocation strategy:** all host ports are in the `2xxxx` range to avoid conflicts with common system services.

**Recommended production topology:**

```
Internet
   │
   ▼
[Nginx Proxy Manager]  ──  TLS termination
   │
   ├──▶ dlh-mage:6789        (pipeline UI)
   ├──▶ dlh-superset:8088    (dashboards)
   ├──▶ dlh-grafana:3000     (monitoring)
   ├──▶ dlh-rustfs:9001      (object store console)
   └──▶ dlh-authentik:9000   (identity provider)

LAN clients
   │
   ├──▶ dlh-postgres:5432    (direct DB access)
   ├──▶ dlh-clickhouse:8123  (HTTP API)
   └──▶ dlh-rustfs:9000      (S3 API)
```

---

## Security Boundaries

- All container credentials are externalized in `.env` — no secrets in `docker-compose.yaml`.
- Host port binding is controlled by `DLH_BIND_IP` / `DLH_APP_BIND_IP` / `DLH_DATA_BIND_IP`.
- LAN exposure is gated by `DLH_LAN_CIDR` and enforced via `setup_ufw_docker.sh`.
- Redis requires password authentication.
- Authentik provides SSO and RBAC for UI services.
- Each stack service has an isolated PostgreSQL database and role — no service shares the admin account.

---

> See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the full architecture reference.

# Architecture

This page describes the system layers, component roles, data flow, and deployment topology of the DataLakehouse stack.

---

## System Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 – INGEST                                                   │
│  PostgreSQL  •  Excel/CSV upload                                    │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ raw records
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 2 – STORAGE (Data Lake)                                      │
│  RustFS S3-compatible object store                                  │
│    bronze/  →  silver/  →  gold/   (Parquet, partitioned by date)  │
│  PostgreSQL  (service metadata databases)                           │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ cleaned/aggregated Parquet
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 3 – PROCESS (ETL)                                            │
│  Mage.ai orchestration engine                                       │
│    Pipelines: etl_postgres_to_lakehouse, etl_excel_to_lakehouse,   │
│               etl_csv_upload_to_reporting                           │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ INSERT from RustFS gold
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 4 – SERVING (OLAP Warehouse)                                 │
│  ClickHouse  (columnar, analytics-optimized)                        │
│    database: analytics                                              │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ SQL queries
┌──────────────────────▼──────────────────────────────────────────────┐
│  LAYER 5 – REPORTING                                                │
│  Apache Superset  (business dashboards)                             │
│  Grafana          (operational / pipeline monitoring)               │
└─────────────────────────────────────────────────────────────────────┘
```

Supporting infrastructure (cuts across all layers):
- **Redis** – shared cache and queue (Superset results, Authentik sessions).
- **Authentik** – centralised identity provider (SSO, RBAC).
- **CloudBeaver** – web SQL IDE for PostgreSQL and ClickHouse.
- **Nginx Proxy Manager** – optional reverse proxy with automatic TLS.
- **Data Healer** – autonomous reconciliation service that ensures Lake-to-Warehouse consistency.

---

## Component Catalog

| Container | Image | Role | Default Port |
|-----------|-------|------|--------------|
| `dlh-postgres` | `postgres:17-alpine` | Central metadata DB for all stack services + operational source data | `25432` |
| `dlh-postgres-bootstrap` | `postgres:17-alpine` | One-shot init: creates per-service DB roles and schemas | — |
| `dlh-rustfs` | `rustfs/rustfs` | S3-compatible object storage (Bronze / Silver / Gold lake buckets) | API `29100`, Console `29101` |
| `dlh-rustfs-init` | `minio/mc` | One-shot init: creates `bronze`, `silver`, `gold` buckets | — |
| `dlh-clickhouse` | `clickhouse/clickhouse-server:25.4-alpine` | Columnar OLAP engine | HTTP `28123`, TCP `29000` |
| `dlh-redis` | `redis/redis-stack:7.4.2-v3` | Shared cache/queue + Redis Insight GUI | Redis `26379`, GUI `25540` |
| `dlh-mage` | `mageai/mageai:0.9.76` | ETL orchestration — runs and schedules pipelines | `26789` |
| `dlh-superset` | `apache/superset:4.1.2` | Business intelligence dashboard UI | `28088` |
| `dlh-grafana` | `grafana/grafana:12.0.0` | Operational monitoring | `23001` |
| `dlh-authentik-server` | `goauthentik/server:2026.2.1` | Identity provider — web + API server | `29090` |
| `dlh-authentik-worker` | `goauthentik/server:2026.2.1` | Background worker for Authentik tasks | — |
| `dlh-cloudbeaver` | `dbeaver/cloudbeaver` | Web SQL IDE | `28978` |
| `dlh-dockhand` | `fnsys/dockhand:latest` | Docker management UI | `23000` |
| `dlh-nginx-proxy-manager` | `jc21/nginx-proxy-manager` | Reverse proxy + TLS termination | `80`, `443`, admin `28081` |

All containers share the external Docker network `web_network`.

---

## Data Flow

### Primary pipeline: PostgreSQL → Lakehouse

```
PostgreSQL source table
    │
    ▼  [extract_postgres.py]
    DataFrame + metadata columns (_pipeline_run_id, _extracted_at, _source_table)
    │
    ├──▶ [bronze_to_rustfs.py]  →  s3://bronze/{table}/dt=YYYY-MM-DD/{run_id}.parquet
    │
    ▼  [transform_silver.py]
    Cleaned DataFrame (dedup, type cast, text normalisation, email validation)
    │
    ├──▶ [silver_to_rustfs.py]  →  s3://silver/{table}/dt=YYYY-MM-DD/{run_id}.parquet
    │
    ▼  [transform_gold.py]
    Aggregated dict: {gold_daily, gold_weekly, gold_monthly, gold_yearly, gold_region, gold_category}
    │
    ├──▶ [gold_to_rustfs.py]    →  s3://gold/{table}_{granularity}/dt=YYYY-MM-DD/{run_id}.parquet
    │
    ▼  [load_to_clickhouse.py]
    Reads Parquet from RustFS Silver + Gold  →  INSERT INTO ClickHouse analytics.*
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

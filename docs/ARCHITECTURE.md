# DataLakehouse – Architecture Reference

This document is the single source of truth for the system architecture, data flow,
component roles, schema design, and operational boundaries of the DataLakehouse stack.

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Layers](#2-system-layers)
3. [Component Catalog](#3-component-catalog)
4. [Data Flow](#4-data-flow)
5. [ETL Pipelines](#5-etl-pipelines)
6. [ClickHouse Schema](#6-clickhouse-schema)
7. [Control Plane](#7-control-plane)
8. [Deployment Topology](#8-deployment-topology)
9. [Security Boundaries](#9-security-boundaries)
10. [Visual Diagram](#10-visual-diagram)

---

## 1. Overview

DataLakehouse is a **local-first, Docker Compose–based analytics platform** that implements the
[Medallion Architecture](https://databricks.com/glossary/medallion-architecture) (Bronze → Silver → Gold)
using commodity open-source components.

Core design principles:

| Principle | Implementation |
|-----------|----------------|
| **Immutability** | Data written to RustFS (object storage) is never overwritten; new partitions are added per run. |
| **RustFS is the Source of Truth** | ClickHouse is the *serving* layer only — it can be fully rebuilt from RustFS at any time. |
| **Traceability** | Every pipeline run generates a unique UUID (`_pipeline_run_id`) stamped on every row. |
| **Idempotency** | ClickHouse tables use `ReplacingMergeTree`; re-running a pipeline never produces duplicate rows. |
| **Separation of Concerns** | Storage, processing, serving, and reporting are independent layers with explicit handoffs. |

---

## 2. System Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 – INGEST                                                   │
│  PostgreSQL  •  Excel/CSV upload                                   │
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
│               etl_csv_upload_to_reporting                          │
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

- **Redis** – shared cache and queue backend (Superset results, Authentik sessions).
- **Authentik** – centralised identity provider (SSO, RBAC).
- **CloudBeaver** – web-based SQL IDE connected to PostgreSQL and ClickHouse.
- **Nginx Proxy Manager** – optional reverse proxy with automatic TLS.

---

## 3. Component Catalog

| Container | Image | Role | Default Port |
|-----------|-------|------|--------------|
| `dlh-postgres` | `postgres:17-alpine` | Central metadata DB for all stack services + operational source data | `25432` |
| `dlh-postgres-bootstrap` | `postgres:17-alpine` | One-shot init: creates per-service DB roles and schemas | — |
| `dlh-rustfs` | `rustfs/rustfs` | S3-compatible object storage (Bronze / Silver / Gold lake buckets) | API `29100`, Console `29101` |
| `dlh-rustfs-init` | `minio/mc` | One-shot init: creates `bronze`, `silver`, `gold` buckets | — |
| `dlh-clickhouse` | `clickhouse/clickhouse-server:25.4-alpine` | Columnar OLAP engine — analytics serving layer | HTTP `28123`, TCP `29000` |
| `dlh-redis` | `redis/redis-stack` | Shared cache/queue (Superset cache+results, Authentik queue) + Redis Insight GUI | `26379` (Redis), `25540` (GUI) |
| `dlh-mage` | `mageai/mageai:0.9.76` | ETL orchestration — runs and schedules pipelines | `26789` |
| `dlh-superset` | `apache/superset:4.1.2` | Business intelligence / dashboard UI connected to ClickHouse | `28088` |
| `dlh-grafana` | `grafana/grafana:12.0.0` | Operational monitoring; ingests `analytics.pipeline_runs` | `23001` |
| `dlh-authentik-server` | `goauthentik/server:2026.2.1` | Identity provider — web + API server | `29090` |
| `dlh-authentik-worker` | `goauthentik/server:2026.2.1` | Background worker for Authentik tasks | — |
| `dlh-cloudbeaver` | `dbeaver/cloudbeaver` | Web SQL IDE for exploring PostgreSQL and ClickHouse | `28978` |
| `dlh-dockhand` | `fnsys/dockhand:latest` | Lightweight web-based Docker management UI | `23000` |
| `dlh-nginx-proxy-manager` | `jc21/nginx-proxy-manager` | Optional reverse proxy + TLS termination | `80`, `443`, admin `28081` |

All containers share the external Docker network `web_network`.

---

## 4. Data Flow

### 4a. PostgreSQL → Lakehouse (primary pipeline)

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

### 4b. Excel upload → Lakehouse

```
Excel file uploaded to RustFS bronze/excel_upload/ (via RustFS Console or watcher)
    │
    ▼  [extract_excel_from_rustfs.py]
    ▼  [clean_excel_data.py]
    ▼  [load_excel_to_clickhouse.py]  →  ClickHouse analytics.project_reports
                                          analytics.gold_projects_summary
                                          analytics.gold_workload_report
```

### 4c. CSV upload → Reporting

```
CSV file uploaded to RustFS bronze/csv_upload/
    │
    ▼  [extract_csv_from_rustfs.py]
    ▼  [clean_csv_for_reporting.py]
    ▼  [csv_to_rustfs_silver.py]     →  s3://silver/csv_upload/dt=YYYY-MM-DD/
    ▼  [load_csv_reporting_clickhouse.py]  →  ClickHouse analytics.csv_clean_rows
```

### 4d. Control / cache path

```
Redis  →  Superset  (cache DB=2, results DB=3)
       →  Authentik (queue/cache DB=1)
```

### 4e. Metadata databases (PostgreSQL)

Each service uses its own isolated PostgreSQL database. The `postgres-bootstrap` init
container creates all roles and schemas on every `docker compose up`:

| Database | Owner Role | Used by |
|----------|-----------|---------|
| `datalakehouse` | `dlh_admin` | Admin / source data |
| `dlh_mage` | `dlh_mage_user` | Mage pipeline metadata |
| `dlh_superset` | `dlh_superset_user` | Superset dashboard metadata |
| `dlh_grafana` | `dlh_grafana_user` | Grafana settings |
| `dlh_authentik` | `dlh_authentik_user` | Authentik identity data |
| `dlh_custom` | `dlh_custom_user` | Optional business workspace DB |

---

## 5. ETL Pipelines

### Pipeline 1: `etl_postgres_to_lakehouse`

**Schedule:** Every 6 hours (`0 */6 * * *`)
**Source:** PostgreSQL (auto-detects table from `SOURCE_TABLE` or `SOURCE_TABLE_CANDIDATES`)

| Block | Type | File |
|-------|------|------|
| `extract_postgres` | data_loader | `mage/data_loaders/extract_postgres.py` |
| `bronze_to_rustfs` | data_exporter | `mage/data_exporters/bronze_to_rustfs.py` |
| `transform_silver` | transformer | `mage/transformers/transform_silver.py` |
| `silver_to_rustfs` | data_exporter | `mage/data_exporters/silver_to_rustfs.py` |
| `transform_gold` | transformer | `mage/transformers/transform_gold.py` |
| `gold_to_rustfs` | data_exporter | `mage/data_exporters/gold_to_rustfs.py` |
| `load_to_clickhouse` | data_exporter | `mage/data_exporters/load_to_clickhouse.py` |

### Pipeline 2: `etl_excel_to_lakehouse`

**Trigger:** Manual or file-upload watcher (`scripts/realtime_watcher.sh`)
**Source:** Excel files in RustFS `bronze/excel_upload/`

| Block | Type | File |
|-------|------|------|
| `extract_excel_from_rustfs` | data_loader | `mage/data_loaders/extract_excel_from_rustfs.py` |
| `clean_excel_data` | transformer | `mage/transformers/clean_excel_data.py` |
| `load_excel_to_clickhouse` | data_exporter | `mage/data_exporters/load_excel_to_clickhouse.py` |

### Pipeline 3: `etl_csv_upload_to_reporting`

**Schedule:** Every 5 minutes (polls RustFS for new CSV files)
**Source:** CSV files in RustFS `bronze/csv_upload/`

| Block | Type | File |
|-------|------|------|
| `extract_csv_from_rustfs` | data_loader | `mage/data_loaders/extract_csv_from_rustfs.py` |
| `clean_csv_for_reporting` | transformer | `mage/transformers/clean_csv_for_reporting.py` |
| `csv_to_rustfs_silver` | data_exporter | `mage/data_exporters/csv_to_rustfs_silver.py` |
| `load_csv_reporting_clickhouse` | data_exporter | `mage/data_exporters/load_csv_reporting_clickhouse.py` |

---

## 6. ClickHouse Schema

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
| `pipeline_runs` | Monitoring | Run ID, status, row counts, error messages per pipeline execution |

### Excel pipeline tables (12-project dashboard)

| Table | Description |
|-------|-------------|
| `project_reports` | Detailed task rows from each uploaded Excel report |
| `gold_projects_summary` | Per-project KPI summary (completion rate, overdue count) |
| `gold_workload_report` | Per-person workload metrics (task count, urgent task count) |

### CSV pipeline tables

| Table | Description |
|-------|-------------|
| `csv_clean_rows` | Cleaned and normalised rows from CSV uploads |

Schema DDL is in `clickhouse/init/001_analytics_schema.sql`.

---

## 7. Control Plane

### Bootstrap

```
scripts/setup.sh
  │
  ├─ Prompts for all config values
  ├─ Writes .env
  ├─ Creates docker network  web_network
  ├─ docker compose up -d
  └─ Optionally runs ETL + Superset provisioning
```

### Day-2 lifecycle (`stackctl.sh`)

| Command | Effect |
|---------|--------|
| `up` | Start all services |
| `down` | Stop all services |
| `redeploy` | Pull images, recreate containers |
| `redeploy --with-etl` | Redeploy + run ETL pipeline |
| `status` | Show container status |
| `health` | Run health checks on all services |
| `logs <service\|all>` | Stream logs |
| `inspect <service>` | Show container config/state |
| `check-env` | Print current .env values |
| `validate-env` | Validate port uniqueness and required fields |
| `sync-env` | Write updated values back to .env |
| `reset` | Remove containers (keep volumes) |
| `reset --hard` | Remove containers AND volumes |
| `check-system` | Run architecture validation script |

### Automation scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_etl_and_dashboard.py` | End-to-end ETL + Superset provisioning (supports `--auto` for CI) |
| `scripts/create_superset_demo_dashboard.py` | Programmatic Superset dashboard creation via API |
| `scripts/verify_lakehouse_architecture.py` | End-to-end architecture health checks (connectivity, data presence) |
| `scripts/realtime_watcher.sh` | Watches RustFS volumes, triggers ETL within seconds of file upload |
| `scripts/setup_ufw_docker.sh` | Docker-aware UFW firewall rule management |
| `scripts/maintenance_tasks.py` | ClickHouse backup to RustFS + cleanup of old Parquet files |

---

## 8. Deployment Topology

All services are deployed via `docker-compose.yaml` on a shared Docker bridge network
(`web_network`, created externally before first `compose up`).

**Port allocation strategy:**

- All host ports are in the `2xxxx` range to avoid collision with common system services.
- App/UI ports are bound to `DLH_APP_BIND_IP` (default `127.0.0.1`).
- Data/DB ports are bound to `DLH_DATA_BIND_IP` (default `127.0.0.1`; set to `0.0.0.0` for LAN access).

**Recommended production topology:**

```
Internet
   │
   ▼
[Nginx Proxy Manager]  ──  TLS termination
   │
   ├──▶ dlh-mage:6789     (pipeline UI)
   ├──▶ dlh-superset:8088 (dashboards)
   ├──▶ dlh-grafana:3000  (monitoring)
   ├──▶ dlh-dockhand:3000 (docker mgmt)
   ├──▶ dlh-rustfs:9001   (object store console)
   └──▶ dlh-authentik:9000 (identity provider)

LAN clients
   │
   ├──▶ dlh-postgres:5432    (direct DB access, data bind IP)
   ├──▶ dlh-clickhouse:8123  (HTTP API, data bind IP)
   └──▶ dlh-rustfs:9000      (S3 API, data bind IP)
```

---

## 9. Security Boundaries

- All container credentials are **externalized in `.env`** — no secrets in `docker-compose.yaml`.
- Host port binding is controlled by `DLH_BIND_IP` / `DLH_APP_BIND_IP` / `DLH_DATA_BIND_IP`.
- LAN exposure is gated by `DLH_LAN_CIDR` and enforced via `setup_ufw_docker.sh`.
- Firewall automation uses `ufw-docker` flow — it does **not** modify SSH rules.
- Redis is protected-mode enabled and requires password authentication.
- Authentik provides SSO and RBAC for UI services.
- Each stack service has an **isolated PostgreSQL database and role** — no service shares the admin account.

---

## 10. Visual Diagram

The architecture diagram is maintained at `docs/assets/datalakehouse-architecture.svg`
and embedded in the root `README.md`.

---

*For deployment steps see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).*
*For pipeline details see [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md).*
*For environment variables see [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md).*
*For day-2 operations see [OPERATIONS.md](OPERATIONS.md).*
CE.md).*
*For day-2 operations see [OPERATIONS.md](OPERATIONS.md).*

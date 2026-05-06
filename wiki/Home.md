# DataLakehouse Wiki

Welcome to the **DataLakehouse** project wiki. This is a production-ready, local-first
Data Lakehouse stack built entirely with Docker Compose. It implements the
**Medallion Architecture** (Bronze → Silver → Gold), automated ETL pipelines, OLAP analytics,
and business intelligence dashboards — all on a single host.

![Architecture diagram](../docs/assets/datalakehouse-architecture.svg)

---

## Quick Navigation

| Page | Description |
|------|-------------|
| [Architecture](Architecture) | System layers, components, and data flow |
| [Getting Started](Getting-Started) | Prerequisites, installation, first run |
| [ETL Pipelines](ETL-Pipelines) | Pipeline blocks, schedules, and trigger methods |
| [Configuration](Configuration) | `.env` reference and key variables |
| [Operations](Operations) | Lifecycle, health checks, logs, and environment management |
| [Backup and Restore](Backup-and-Restore) | ClickHouse and PostgreSQL data protection |
| [Troubleshooting](Troubleshooting) | Common issues and fixes |
| [Developer Guide](Developer-Guide) | Adding new pipelines and developing pipeline blocks |
| [Security](Security) | Hardening guide and production checklist |

---

## Stack at a Glance

| Layer | Component | Role |
|-------|-----------|------|
| **Ingest** | PostgreSQL, RustFS Console, CSV/Excel upload | Source data entry points |
| **Storage (Lake)** | RustFS (S3-compatible) | Parquet files in Bronze / Silver / Gold buckets |
| **Process (ETL)** | Mage.ai | Orchestrates Extract → Transform → Load pipelines |
| **Warehouse** | ClickHouse | Columnar OLAP engine — serves analytics queries |
| **Dashboards** | Apache Superset | Business intelligence dashboards |
| **Monitoring** | Grafana | Pipeline operational monitoring |
| **Identity** | Authentik | Centralised SSO and RBAC |
| **Cache / GUI** | Redis Stack | Shared cache/queue + built-in Redis Insight UI |
| **SQL IDE** | CloudBeaver | Web-based SQL client for PostgreSQL and ClickHouse |
| **Remote Desktop** | Apache Guacamole | Browser-based VNC/RDP/SSH remote desktop gateway |
| **Docker Mgmt** | Dockhand | Lightweight web-based Docker management UI |
| **Proxy** | Nginx Proxy Manager | Optional TLS reverse proxy |

---

## Service URLs (default ports)

| Service | URL | Default credentials |
|---------|-----|---------------------|
| RustFS Console | http://localhost:29101 | `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` |
| Mage | http://localhost:26789 | `MAGE_DEFAULT_OWNER_USERNAME` / `MAGE_DEFAULT_OWNER_PASSWORD` |
| Superset | http://localhost:28088 | `SUPERSET_ADMIN_USER` / `SUPERSET_ADMIN_PASSWORD` |
| Grafana | http://localhost:23001 | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` |
| Authentik | http://localhost:29090 | `AUTHENTIK_BOOTSTRAP_EMAIL` / `AUTHENTIK_BOOTSTRAP_PASSWORD` |
| CloudBeaver | http://localhost:28978 | Configured on first login |
| Guacamole | http://localhost:28090/guacamole/ | `guacadmin` / `guacadmin` |
| Dockhand | http://localhost:23000 | No auth by default |
| Nginx Proxy Manager | http://localhost:28081 | Configured on first login |
| PostgreSQL | localhost:25432 | `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| ClickHouse HTTP | http://localhost:28123 | `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` |
| Redis | localhost:26379 | `REDIS_PASSWORD` |
| Redis Insight | http://localhost:25540 | Add connection manually |

> All credentials are defined in `.env`. Default placeholder values are for **local development only** — rotate all passwords before any production deployment.

---

## Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Immutability** | Data in RustFS is never overwritten; new partitions are added per run |
| **Single source of truth** | RustFS holds the canonical data; ClickHouse is a *serving* layer rebuilt at any time |
| **Traceability** | Every pipeline run stamps a unique `_pipeline_run_id` UUID on every row |
| **Idempotency** | ClickHouse uses `ReplacingMergeTree`; re-running a pipeline never creates duplicate rows |
| **Separation of concerns** | Storage, processing, serving, and reporting are independent layers |

---

## Further Documentation

The `docs/` directory in the repository contains detailed reference documents:

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](../docs/ARCHITECTURE.md) | Full system architecture reference |
| [DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) | Step-by-step deployment guide |
| [PIPELINE_GUIDE.md](../docs/PIPELINE_GUIDE.md) | Every ETL block explained |
| [VARIABLES_REFERENCE.md](../docs/VARIABLES_REFERENCE.md) | Complete `.env` variable reference |
| [OPERATIONS.md](../docs/OPERATIONS.md) | Day-2 operations: health, backup, restore |
| [RUSTFS_LAYER_READER_GUIDE.md](../docs/RUSTFS_LAYER_READER_GUIDE.md) | Python API for reading Bronze/Silver/Gold layers |
| [TESTING_CHECKLIST.md](../docs/TESTING_CHECKLIST.md) | End-to-end verification checklist |

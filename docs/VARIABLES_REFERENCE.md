# 📖 Environment Variables Reference – DataLakehouse

This document describes every environment variable in the DataLakehouse `.env` file.

> **How to use:**
> 1. Copy `.env.example` → `.env`
> 2. Edit the variables for your environment
> 3. Variables marked ⚠️ **MUST** be changed before production

---

## Table of Contents

1. [Global Settings](#1-global-settings)
2. [Docker Image Versions](#2-docker-image-versions)
3. [PostgreSQL – Admin](#3-postgresql--admin)
4. [PostgreSQL – Custom Workspace](#4-postgresql--custom-workspace)
5. [RustFS – Object Storage](#5-rustfs--object-storage)
6. [ClickHouse – OLAP Engine](#6-clickhouse--olap-engine)
7. [Mage.ai – ETL Orchestration](#7-mageai--etl-orchestration)
8. [NocoDB – No-code DB UI](#8-nocodb--no-code-db-ui)
9. [Apache Superset – Analytics](#9-apache-superset--analytics)
10. [Grafana – Monitoring](#10-grafana--monitoring)
11. [Nginx Proxy Manager (Optional)](#11-nginx-proxy-manager-optional)
12. [Quick Reference Table](#12-quick-reference-table)

---

## 1. Global Settings

### `TZ`

| Property | Value |
|----------|-------|
| **Default** | `Asia/Ho_Chi_Minh` |
| **Required** | ✅ |
| **Affects** | All containers |

**Description:** Timezone applied uniformly across the entire stack. Affects:
- Log timestamps in all services
- Mage.ai pipeline cron schedule
- Grafana/Superset time display
- `PGTZ` in PostgreSQL (timezone for datetime queries)

**Valid values:** Standard IANA timezone names

```bash
# Common timezone examples
TZ=Asia/Ho_Chi_Minh   # Vietnam (UTC+7)
TZ=UTC                # Coordinated Universal Time
TZ=America/New_York   # Eastern Time
TZ=Europe/London      # GMT/BST
TZ=Asia/Singapore     # Singapore (UTC+8)
```

---

### `DLH_BIND_IP`

| Property | Value |
|----------|-------|
| **Default** | `127.0.0.1` |
| **Required** | ✅ |
| **Affects** | All `ports:` entries in docker-compose.yaml |

**Description:** The IP address on the host machine to which service ports are bound. This is the most important network security control.

**How it works:** Ports are defined in `docker-compose.yaml` as:
```yaml
ports:
  - "${DLH_BIND_IP}:${DLH_MAGE_PORT}:6789"
```
Docker resolves this as `127.0.0.1:26789:6789` – meaning only connections from `127.0.0.1` (localhost) can reach port 26789.

**Options:**

| Value | Who can access | Use case |
|-------|---------------|---------|
| `127.0.0.1` | Only the machine running Docker | Local development, most secure |
| `192.168.1.x` | All machines on the same LAN | Team development, internal demo |
| `0.0.0.0` | Everyone | **Only with firewall + reverse proxy!** |

```bash
# Find your LAN IP
ip addr show        # Linux
ifconfig            # macOS
ipconfig            # Windows
```

---

### `POSTGRES_HOST`

| Property | Value |
|----------|-------|
| **Default** | `dlh-postgres` |
| **Required** | ✅ |
| **Affects** | Mage, Superset, Grafana, NocoDB |

**Description:** Hostname of the PostgreSQL server **inside the Docker network**. When containers communicate with each other, they use the container name as the hostname.

**When to change:**
- Using an external PostgreSQL (managed DB service, separate VPS)
- Example: `POSTGRES_HOST=db.example.com` or `POSTGRES_HOST=10.0.0.5`

> ⚠️ If you change `POSTGRES_HOST`, also update `mage/io_config.yaml` to ensure Mage uses the correct host.

---

## 2. Docker Image Versions

These variables control which Docker image versions are pulled. Defined in one place for easy stack-wide upgrades.

| Variable | Default | Service |
|----------|---------|---------|
| `POSTGRES_IMAGE_VERSION` | `17-alpine` | PostgreSQL |
| `RUSTFS_IMAGE_VERSION` | `latest` | RustFS |
| `MINIO_MC_IMAGE_VERSION` | `latest` | MinIO mc (used by rustfs-init) |
| `CLICKHOUSE_IMAGE_VERSION` | `latest` | ClickHouse |
| `MAGE_IMAGE_VERSION` | `latest` | Mage.ai |
| `NOCODB_IMAGE_VERSION` | `latest` | NocoDB |
| `SUPERSET_IMAGE_VERSION` | `latest` | Apache Superset |
| `GRAFANA_IMAGE_VERSION` | `latest` | Grafana |

**Production recommendation:**

```bash
# Pin specific versions for stability and rollback capability
POSTGRES_IMAGE_VERSION=17.2-alpine
CLICKHOUSE_IMAGE_VERSION=24.3.3.102
MAGE_IMAGE_VERSION=0.9.73
GRAFANA_IMAGE_VERSION=10.4.2
SUPERSET_IMAGE_VERSION=3.1.3
```

**Check currently running versions:**
```bash
docker compose images
```

---

## 3. PostgreSQL – Admin

### `POSTGRES_DB`

| Property | Value |
|----------|-------|
| **Default** | `datalakehouse` |
| **Required** | ✅ |

**Description:** Name of the admin database created when PostgreSQL starts for the first time. This is the "home" database for the superuser `POSTGRES_USER`. It also contains the Demo sample data (100k rows) created by `002_sample_data.sql`.

**Related to:** `SOURCE_DB_NAME` – the ETL pipeline extracts from this database (if `SOURCE_DB_NAME` is not set separately).

---

### `POSTGRES_USER`

| Property | Value |
|----------|-------|
| **Default** | `dlh_admin` |
| **Required** | ✅ |

**Description:** The PostgreSQL superuser created when the container initializes. This user has `SUPERUSER`, `CREATEDB`, `CREATEROLE` permissions. The bootstrap script (`000_create_app_security.sh`) uses this user to create the other users and databases for Mage, Superset, Grafana, and NocoDB.

---

### `POSTGRES_PASSWORD`

| Property | Value |
|----------|-------|
| **Default** | `change-this-admin-password` |
| **Required** | ✅ ⚠️ **CHANGE IMMEDIATELY** |

**Description:** Password for the PostgreSQL superuser. Used by **multiple services** to connect to PostgreSQL:
- `postgres-bootstrap` to create roles
- `source_db` profile in Mage
- Grafana datasource

**Strong password requirement:**
```bash
# Generate a random 32-character password
openssl rand -base64 24
# Example output: X9mK2pLqR8vYnJwZ3tHbFcDsAeGu4iNo
```

---

### `DLH_POSTGRES_PORT`

| Property | Value |
|----------|-------|
| **Default** | `25432` |
| **Required** | – |

**Description:** PostgreSQL port exposed to the host machine. Port 5432 is PostgreSQL's default, so a non-standard port (25432) avoids conflicts if you already have PostgreSQL installed locally.

**Connect from the host:**
```bash
psql -h localhost -p 25432 -U dlh_admin -d datalakehouse
```

---

## 4. PostgreSQL – Custom Workspace

This group of variables creates a separate workspace database for business data, isolated from system metadata.

### `CUSTOM_DB_NAME`

| Property | Value |
|----------|-------|
| **Default** | `dlh_custom` |
| **Optional** | Leave empty (`CUSTOM_DB_NAME=`) to skip |

**Description:** Name of the dedicated business workspace database. When this variable has a value, the bootstrap script automatically:
1. Creates database `<CUSTOM_DB_NAME>`
2. Creates user `<CUSTOM_DB_USER>` with full privileges on this database
3. Creates schema `<CUSTOM_SCHEMA>` in the database

**When to use:** When you want to load your own data into a separate database, not mixed with the `datalakehouse` admin DB.

---

### `CUSTOM_DB_USER`

| Property | Value |
|----------|-------|
| **Default** | `dlh_custom_user` |

**Description:** Dedicated PostgreSQL user for the workspace. Has permissions only on `CUSTOM_DB_NAME`, no superuser privileges. Use this user in your applications instead of the superuser.

---

### `CUSTOM_DB_PASSWORD`

| Property | Value |
|----------|-------|
| **Default** | `change-this-custom-password` |
| **⚠️ Change** | Required |

---

### `CUSTOM_SCHEMA`

| Property | Value |
|----------|-------|
| **Default** | `custom_schema` |

**Description:** Schema name inside `CUSTOM_DB_NAME`. Separates your tables from the default `public` schema. Mage ETL will use this schema when `CUSTOM_SCHEMA` is set.

---

## 5. RustFS – Object Storage

RustFS is an S3-compatible object storage written in Rust, used as the data lake layer storing all Parquet and CSV files.

### `RUSTFS_ACCESS_KEY`

| Property | Value |
|----------|-------|
| **Default** | `rustfsadmin` |
| **Required** | ✅ ⚠️ |

**Description:** Access Key for authenticating with the RustFS S3 API. Equivalent to "username" in S3. Used by:
- Mage.ai pipelines (via boto3)
- `rustfs-init` container (creates buckets)
- NocoDB (Litestream backup)
- You when accessing from CLI or code

**Requirements:** 3–20 characters, only letters, digits, underscores, hyphens.

---

### `RUSTFS_SECRET_KEY`

| Property | Value |
|----------|-------|
| **Default** | `rustfsadmin` |
| **Required** | ✅ ⚠️ |

**Description:** Secret Key, equivalent to "password" in S3. Must be at least 8 characters. **Never commit the real value to git.**

```bash
# Generate a random secret key
openssl rand -hex 16
```

---

### `DLH_RUSTFS_API_PORT`

| Property | Value |
|----------|-------|
| **Default** | `29100` |

**Description:** RustFS S3 API port on the host machine. Used to connect from outside Docker (CLI, Python scripts on the host).

**Connect from the host using AWS CLI / mc:**
```bash
# MinIO mc client
mc alias set local http://localhost:29100 rustfsadmin rustfsadmin
mc ls local/

# AWS CLI (with endpoint override)
aws --endpoint-url http://localhost:29100 s3 ls s3://bronze/
```

---

### `DLH_RUSTFS_CONSOLE_PORT`

| Property | Value |
|----------|-------|
| **Default** | `29101` |

**Description:** RustFS Web Console port. Open http://localhost:29101 to upload files and manage buckets through the web interface.

---

### `RUSTFS_ENDPOINT_URL`

| Property | Value |
|----------|-------|
| **Default** | `http://dlh-rustfs:9000` |

**Description:** S3 endpoint URL used by **other containers** to connect to RustFS. Uses the container name `dlh-rustfs` as the hostname (automatically resolved by Docker DNS).

**When to change:** If RustFS runs on a different machine or network.

---

### `RUSTFS_BRONZE_BUCKET` / `RUSTFS_SILVER_BUCKET` / `RUSTFS_GOLD_BUCKET`

| Variable | Default | Purpose |
|----------|---------|---------|
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Raw, unprocessed data |
| `RUSTFS_SILVER_BUCKET` | `silver` | Cleaned and validated data |
| `RUSTFS_GOLD_BUCKET` | `gold` | Aggregated (analytics-ready) data |

**Description:** Bucket names for the Medallion architecture layers. These buckets are created automatically by the `rustfs-init` container when the stack first starts.

**File structure in buckets:**
```
bronze/
  demo/dt=YYYY-MM-DD/<run_id>.parquet

silver/
  demo/dt=YYYY-MM-DD/<run_id>.parquet
  csv_upload/dt=YYYY-MM-DD/<run_id>.parquet

gold/
  demo_daily/dt=YYYY-MM-DD/<run_id>.parquet
  demo_weekly/dt=YYYY-MM-DD/<run_id>.parquet
  demo_monthly/dt=YYYY-MM-DD/<run_id>.parquet
  demo_yearly/dt=YYYY-MM-DD/<run_id>.parquet
  demo_by_region/dt=YYYY-MM-DD/<run_id>.parquet
  demo_by_category/dt=YYYY-MM-DD/<run_id>.parquet
```

---

### `RUSTFS_CORS_ALLOWED_ORIGINS` / `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS`

| Variable | Default |
|----------|---------|
| `RUSTFS_CORS_ALLOWED_ORIGINS` | `http://localhost:29100` |
| `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS` | `http://localhost:29101` |

**Description:** Origins allowed in CORS headers. Required when JavaScript frontends make direct S3 API calls from the browser.

**When deployed on a server:**
```bash
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=https://storage-console.yourdomain.com
```

---

### `LITESTREAM_S3_ENDPOINT`

| Property | Value |
|----------|-------|
| **Default** | `http://dlh-rustfs:9000` |

**Description:** S3 endpoint for Litestream – the NocoDB SQLite real-time backup tool. Litestream streams NocoDB's SQLite WAL to RustFS continuously, ensuring no data loss on container restart.

---

## 6. ClickHouse – OLAP Engine

### `CLICKHOUSE_HOST`

| Property | Value |
|----------|-------|
| **Default** | `dlh-clickhouse` |

**Description:** Hostname of ClickHouse **inside the Docker network**. Used by Mage pipelines (clickhouse-driver) and Grafana datasource.

---

### `CLICKHOUSE_DB`

| Property | Value |
|----------|-------|
| **Default** | `analytics` |

**Description:** Default analytics database in ClickHouse. All data tables (silver, gold, metrics) are created in this database.

**Tables in `analytics`:**

| Table | Approximate Size | Description |
|-------|-----------------|-------------|
| `silver_demo` | ~100k rows | Cleaned PostgreSQL data |
| `gold_demo_daily` | ~365 rows/year | Daily aggregation |
| `gold_demo_weekly` | ~52 rows/year | Weekly aggregation (ISO week) |
| `gold_demo_monthly` | ~12 rows/year | Monthly aggregation |
| `gold_demo_yearly` | 1 row/year | Yearly aggregation |
| `gold_demo_by_region` | ~10 rows | Regional aggregation |
| `gold_demo_by_category` | ~10 rows | Category aggregation |
| `csv_clean_rows` | Varies | Processed CSV rows (JSON) |
| `csv_quality_metrics` | 1 row/file | CSV quality metrics |
| `csv_upload_events` | 1 row/run | Upload event log |
| `pipeline_runs` | 1 row/run | ETL run history |

---

### `CLICKHOUSE_USER`

| Property | Value |
|----------|-------|
| **Default** | `default` |

**Description:** ClickHouse username. `default` is the built-in user with full privileges. For production, it is recommended to create a dedicated user with limited permissions.

---

### `CLICKHOUSE_PASSWORD`

| Property | Value |
|----------|-------|
| **Default** | *(empty)* |
| **⚠️ Change for production** | |

**Description:** ClickHouse password. **Leaving it empty** is valid for local environments since ClickHouse in the Docker network is not exposed to the internet. However, **always set a password for production**.

```bash
# Generate a password and SHA256 hash (ClickHouse uses SHA256)
echo -n "YourPassword123" | sha256sum
```

---

### `DLH_CLICKHOUSE_HTTP_PORT`

| Property | Value |
|----------|-------|
| **Default** | `28123` |

**Description:** ClickHouse HTTP API port on the host. Used for:
- Browser access (Play UI at `http://localhost:28123/play`)
- `curl` queries
- Grafana datasource when connecting from the host
- DBeaver, DataGrip with ClickHouse JDBC driver

---

### `DLH_CLICKHOUSE_TCP_PORT`

| Property | Value |
|----------|-------|
| **Default** | `29000` |

**Description:** ClickHouse native TCP protocol port. Used by the `clickhouse-driver` Python library (better performance than HTTP for bulk inserts).

> **Note:** ClickHouse's default TCP port is 9000, but since RustFS also uses 9000 inside its container, we map to 29000 on the host to avoid confusion.

---

## 7. Mage.ai – ETL Orchestration

### Database Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `MAGE_DB_NAME` | `dlh_mage` | PostgreSQL database storing Mage's internal metadata (pipeline definitions, run history). |
| `MAGE_DB_USER` | `dlh_mage_user` | Dedicated PostgreSQL user for Mage. Created automatically by bootstrap. |
| `MAGE_DB_PASSWORD` | `change-this-mage-password` | ⚠️ Must be changed. |
| `MAGE_CODE_PATH` | `/home/src` | Code directory path **inside the container** (mounted from `./mage`). |

### ETL Source – PostgreSQL Data Source

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCE_DB_HOST` | `dlh-postgres` | Source ETL database host. |
| `SOURCE_DB_PORT` | `5432` | Source PostgreSQL port. |
| `SOURCE_DB_NAME` | `datalakehouse` | Source database name for data extraction. When `CUSTOM_DB_NAME` is set, use that value. |
| `SOURCE_DB_USER` | `dlh_admin` | PostgreSQL user for reading source data. |
| `SOURCE_DB_PASSWORD` | *(same as POSTGRES_PASSWORD)* | Source user password. |
| `SOURCE_SCHEMA` | `public` | PostgreSQL schema containing the source table. |
| `SOURCE_TABLE` | *(empty)* | Specific table name to extract. **Leave empty** = auto-detect from `SOURCE_TABLE_CANDIDATES`. |
| `SOURCE_TABLE_CANDIDATES` | `Demo,test_projects` | Comma-separated list of candidate table names. Pipeline tries each until one is found. |

### CSV Upload Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `CSV_UPLOAD_BUCKET` | `bronze` | RustFS bucket to scan for new CSV files. |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Virtual directory prefix to scan for CSV files first. |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | `true` = accept CSVs anywhere in the bucket (not just `CSV_UPLOAD_PREFIX`). |
| `CSV_UPLOAD_SEPARATOR` | `,` | Column separator character. Use `;` for European CSV, `\t` for TSV. |
| `CSV_UPLOAD_ENCODING` | `utf-8` | CSV file encoding. Use `utf-8-sig` for BOM files (from Excel). |
| `CSV_UPLOAD_SCAN_LIMIT` | `200` | Maximum number of files to scan per pipeline run. Increase if the bucket has many files. |

---

## 8. NocoDB – No-code Database UI

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_NOCODB_PORT` | `28082` | NocoDB Web UI port exposed to host. |
| `NOCODB_DB_NAME` | `dlh_nocodb` | PostgreSQL database for NocoDB metadata. |
| `NOCODB_DB_USER` | `dlh_nocodb_user` | Dedicated PostgreSQL user for NocoDB. |
| `NOCODB_DB_PASSWORD` | `change-this-nocodb-password` | ⚠️ Must be changed. |
| `NOCODB_PUBLIC_URL` | `http://127.0.0.1:28082` | NocoDB's public URL (used for redirects, SSO callbacks). Change when deploying with a real domain. |
| `NOCODB_BACKEND_URL` | `http://127.0.0.1:28082` | NocoDB backend API URL. |

---

## 9. Apache Superset – Analytics Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_SUPERSET_PORT` | `28088` | Superset Web UI port. |
| `SUPERSET_SECRET_KEY` | `replace-this-secret` | ⚠️ **MUST be changed!** Flask session encryption key. Generate with `openssl rand -hex 32`. |
| `SUPERSET_DB_NAME` | `dlh_superset` | PostgreSQL database for Superset metadata (dashboards, charts, users). |
| `SUPERSET_DB_USER` | `dlh_superset_user` | Dedicated PostgreSQL user for Superset. |
| `SUPERSET_DB_PASSWORD` | `change-this-superset-db-password` | ⚠️ Must be changed. |
| `SUPERSET_ADMIN_USER` | `admin` | Superset admin login name. |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | ⚠️ **MUST be changed for production!** |
| `SUPERSET_ADMIN_EMAIL` | `admin@superset.local` | Superset admin email. |
| `SUPERSET_LOAD_EXAMPLES` | `no` | `yes` = load Superset sample data (adds 2–3 minutes). |

---

## 10. Grafana – Monitoring & Alerting

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_GRAFANA_PORT` | `23001` | Grafana Web UI port. |
| `GRAFANA_DB_NAME` | `dlh_grafana` | PostgreSQL database for Grafana metadata (dashboards, users, config). |
| `GRAFANA_DB_USER` | `dlh_grafana_user` | Dedicated PostgreSQL user for Grafana. |
| `GRAFANA_DB_PASSWORD` | `change-this-grafana-db-password` | ⚠️ Must be changed. |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin login name. |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | ⚠️ **MUST be changed for production!** |
| `GF_DATABASE_HOST` | `dlh-postgres:5432` | Host:port PostgreSQL for Grafana (Grafana's special format). |
| `GF_INSTALL_PLUGINS` | `grafana-piechart-panel,grafana-clickhouse-datasource` | Grafana plugins to install automatically at startup. |

---

## 11. Nginx Proxy Manager (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_NPM_HTTP_PORT` | `28080` | Nginx Proxy Manager HTTP port. |
| `DLH_NPM_HTTPS_PORT` | `28443` | HTTPS port (SSL termination). |
| `DLH_NPM_ADMIN_PORT` | `28081` | Nginx Proxy Manager Admin UI port. |

> 💡 To enable Nginx Proxy Manager, uncomment the `nginx-proxy-manager` section in `docker-compose.yaml`.

---

## 12. Quick Reference Table

| Variable | Default | Must Change for Production |
|----------|---------|--------------------------|
| `TZ` | `Asia/Ho_Chi_Minh` | Recommended |
| `DLH_BIND_IP` | `127.0.0.1` | Set to LAN IP or keep as-is |
| `POSTGRES_PASSWORD` | `change-this-admin-password` | ✅ YES |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | ✅ YES |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | ✅ YES |
| `CLICKHOUSE_PASSWORD` | *(empty)* | ✅ YES |
| `MAGE_DB_PASSWORD` | `change-this-mage-password` | ✅ YES |
| `NOCODB_DB_PASSWORD` | `change-this-nocodb-password` | ✅ YES |
| `SUPERSET_SECRET_KEY` | `replace-this-secret` | ✅ YES (critical!) |
| `SUPERSET_DB_PASSWORD` | `change-this-superset-db-password` | ✅ YES |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | ✅ YES |
| `GRAFANA_DB_PASSWORD` | `change-this-grafana-db-password` | ✅ YES |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | ✅ YES |
| `CUSTOM_DB_PASSWORD` | `change-this-custom-password` | ✅ YES |

**Quick secure setup for production:**
```bash
# Generate all passwords at once
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
echo "RUSTFS_ACCESS_KEY=prod$(openssl rand -hex 8)"
echo "RUSTFS_SECRET_KEY=$(openssl rand -base64 32)"
echo "CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)"
echo "MAGE_DB_PASSWORD=$(openssl rand -base64 24)"
echo "NOCODB_DB_PASSWORD=$(openssl rand -base64 24)"
echo "SUPERSET_SECRET_KEY=$(openssl rand -hex 32)"
echo "SUPERSET_DB_PASSWORD=$(openssl rand -base64 24)"
echo "SUPERSET_ADMIN_PASSWORD=$(openssl rand -base64 16)"
echo "GRAFANA_DB_PASSWORD=$(openssl rand -base64 24)"
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)"
echo "CUSTOM_DB_PASSWORD=$(openssl rand -base64 24)"
```

---

*See also: [README.md](../README.md) | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md)*

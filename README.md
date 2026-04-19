# 🏗️ DataLakehouse – Modern Data Stack

> A fully integrated **Data Lakehouse** stack – from raw storage through ETL to analytics dashboards, deployed with a single Docker Compose command.

📚 **Documentation:**
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Environment Variables Reference](docs/VARIABLES_REFERENCE.md)
- [ETL Pipeline Guide](docs/PIPELINE_GUIDE.md)
- [Lakehouse Architecture](docs/LAKEHOUSE_ARCHITECTURE.md)

---

## 📋 Table of Contents

| Section |
|---------|
| [Quick Start](#-quick-start) |
| [Architecture](#-architecture) |
| [Components](#-components) |
| [Environment Variables](#-environment-variables-reference) |
| [Project Structure](#-project-structure) |
| [Usage](#-usage) |
| [Dashboards](#-dashboards) |
| [API](#-api) |
| [Troubleshooting](#-troubleshooting) |

---

# 🚀 Quick Start

## Prerequisites

| Requirement | Minimum Version | Check |
|-------------|----------------|-------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| Available RAM | 4 GB | 8 GB recommended |
| Disk space | 10 GB | For data volumes |
| Open ports | See table below | Check before running |

### Check open ports

```bash
# Verify all DataLakehouse ports are free
for port in 25432 29100 29101 28123 29000 26789 28082 28088 23001; do
  ss -tlnp | grep -q ":$port " && echo "⚠ Port $port is IN USE" || echo "✓ Port $port is free"
done
```

---

## Step 1 – Clone & Configure

```bash
# Clone the repository
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse

# Copy the example configuration file
cp .env.example .env
```

> 💡 **Recommended:** Use the interactive setup wizard:
> ```bash
> bash scripts/setup.sh
> ```
> The script prompts for each variable, writes `.env`, creates the network, and starts the stack.

**Or** edit `.env` manually – see [Environment Variables Reference](#-environment-variables-reference).

---

## Step 2 – Create Docker Network

```bash
docker network create web_network
```

> ⚠️ This only needs to be done **once**. Docker will report an error if it already exists, which is harmless.

---

## Step 3 – Start the Stack

```bash
# Start all services in background mode
docker compose up -d

# Check status (wait for all services to be "healthy")
docker compose ps

# View combined logs
docker compose logs -f
```

> ⏳ **First run:** Takes 5–15 minutes to pull images and initialize 100k rows of sample data.

---

## Step 4 – Access the Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| 🗄 **RustFS Console** (Object Storage) | http://localhost:29101 | See `RUSTFS_ACCESS_KEY` in `.env` |
| 📊 **Superset** (Analytics Dashboard) | http://localhost:28088 | `admin` / `admin` |
| 📈 **Grafana** (Monitoring) | http://localhost:23001 | `admin` / `admin` |
| ⚙️ **Mage.ai** (ETL Orchestration) | http://localhost:26789 | No login required |
| 🗃 **NocoDB** (No-code DB UI) | http://localhost:28082 | Create account on first visit |

> 🔐 **Security:** Change all default passwords in `.env` before deploying to production!

---

# 🏛️ Architecture

## Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                              │
│          PostgreSQL  ·  CSV Upload  ·  APIs  ·  Streaming        │
└───────────────────────────┬──────────────────────────────────────┘
                            │  Extract
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   LAYER 3 – PROCESS (Mage.ai)                    │
│                                                                  │
│  Pipeline 1: etl_postgres_to_lakehouse  (every 6 hours)          │
│    extract_postgres → transform_silver → transform_gold           │
│    → bronze_to_rustfs → silver_to_rustfs → gold_to_rustfs         │
│    → load_to_clickhouse                                           │
│                                                                  │
│  Pipeline 2: etl_csv_upload_to_reporting  (every 5 minutes)      │
│    extract_csv_from_rustfs → clean_csv_for_reporting              │
│    → csv_to_rustfs_silver → load_csv_reporting_clickhouse         │
└──────┬────────────────────────────────────────────┬──────────────┘
       │ Write                                      │ Write
       ▼                                            ▼
┌─────────────────────┐              ┌──────────────────────────────┐
│  LAYER 2 – STORAGE  │              │  LAYER 2 – METADATA          │
│  RustFS (S3-compat) │              │  PostgreSQL 17               │
│                     │              │                              │
│  bronze/ ← raw data │              │  dlh_mage     (Mage meta)    │
│  silver/ ← cleaned  │              │  dlh_superset (Superset meta)│
│  gold/   ← aggregated│              │  dlh_grafana  (Grafana meta) │
│  csv_upload/ ← CSVs │              │  dlh_nocodb   (NocoDB meta)  │
└──────────┬──────────┘              │  dlh_custom   (Workspace)    │
           │ Read (lakehouse)         └──────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   LAYER 4 – SERVE (ClickHouse)                   │
│                                                                  │
│  analytics.silver_demo            (cleaned source data)          │
│  analytics.gold_demo_daily        (daily aggregation)            │
│  analytics.gold_demo_weekly       (weekly aggregation)           │
│  analytics.gold_demo_monthly      (monthly aggregation)          │
│  analytics.gold_demo_yearly       (yearly aggregation)           │
│  analytics.gold_demo_by_region    (regional aggregation)         │
│  analytics.gold_demo_by_category  (category aggregation)         │
│  analytics.csv_clean_rows         (processed CSV rows)           │
│  analytics.csv_quality_metrics    (CSV quality metrics)          │
│  analytics.csv_upload_events      (upload events)                │
│  analytics.pipeline_runs          (pipeline history)             │
└──────────────────────┬───────────────────────────────────────────┘
                       │ Query
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐      ┌──────────────────────────┐
│  LAYER 5 – REPORT│      │  LAYER 5 – MONITOR        │
│  Apache Superset  │      │  Grafana                  │
│  (Analytics UI)   │      │  (Monitoring & Alerts)    │
└──────────────────┘      └──────────────────────────┘
          │                         │
          ▼                         ▼
┌──────────────────────────────────────────────────────┐
│                      END USERS                        │
│   Business Analysts · Data Scientists · Developers   │
└──────────────────────────────────────────────────────┘
```

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Separation of Concerns** | Metadata (PostgreSQL), Lake Storage (RustFS), Analytics (ClickHouse) |
| **Medallion Architecture** | Bronze (raw) → Silver (clean) → Gold (aggregated) |
| **Immutability** | Data in RustFS is never overwritten; ClickHouse reads from the lake |
| **Recoverability** | All data can be rebuilt from RustFS at any time |
| **Non-technical UX** | Upload CSV via web → auto-ingest → dashboard immediately |
| **No external dependencies** | No dbt, no GX, no external validation services |

---

# 🔧 Components

| Component | Role | Host Port | Database | Image |
|-----------|------|-----------|----------|-------|
| **PostgreSQL 17** | Central metadata/config for all services | `25432` | `datalakehouse` | `postgres:17-alpine` |
| **RustFS** | S3-compatible object storage (Bronze/Silver/Gold) | `29100` (API), `29101` (Console) | – | `rustfs/rustfs` |
| **ClickHouse** | OLAP analytics engine | `28123` (HTTP), `29000` (TCP) | `analytics` | `clickhouse/clickhouse-server` |
| **Mage.ai** | ETL pipeline orchestration with scheduling | `26789` | `dlh_mage` | `mageai/mageai` |
| **NocoDB** | No-code UI for viewing/editing PostgreSQL | `28082` | `dlh_nocodb` | `nocodb/nocodb` |
| **Apache Superset** | Analytics dashboards & charts | `28088` | `dlh_superset` | `apache/superset` |
| **Grafana** | Monitoring, alerting, metrics | `23001` | `dlh_grafana` | `grafana/grafana` |

---

# 🔐 Environment Variables Reference

> 📖 See full documentation: [docs/VARIABLES_REFERENCE.md](docs/VARIABLES_REFERENCE.md)

## Global Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TZ` | `Asia/Ho_Chi_Minh` | Timezone for all containers. Affects log timestamps, pipeline schedules, and Grafana/Superset display. Use standard IANA timezone names (e.g. `UTC`, `America/New_York`). |
| `DLH_BIND_IP` | `127.0.0.1` | IP address on the host machine to which service ports are bound. `127.0.0.1` = local access only. Set to your LAN IP (e.g. `192.168.1.10`) for team access. **Do not use `0.0.0.0` on a public server without a firewall.** |
| `POSTGRES_HOST` | `dlh-postgres` | Hostname of the PostgreSQL container inside the Docker network. |

## Docker Image Versions

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_IMAGE_VERSION` | `17-alpine` | PostgreSQL image tag. |
| `RUSTFS_IMAGE_VERSION` | `latest` | RustFS image tag. Pin a specific version for production. |
| `MINIO_MC_IMAGE_VERSION` | `latest` | MinIO Client tag (used by `rustfs-init`). |
| `CLICKHOUSE_IMAGE_VERSION` | `latest` | ClickHouse image tag. |
| `MAGE_IMAGE_VERSION` | `latest` | Mage.ai image tag. |
| `NOCODB_IMAGE_VERSION` | `latest` | NocoDB image tag. |
| `SUPERSET_IMAGE_VERSION` | `latest` | Apache Superset image tag. |
| `GRAFANA_IMAGE_VERSION` | `latest` | Grafana image tag. |

> ⚠️ **Production:** Always pin specific versions instead of `latest` for stability.

## PostgreSQL – Central Database

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `POSTGRES_DB` | `datalakehouse` | ✅ | Name of the admin database created at startup. Contains sample data (100k rows). |
| `POSTGRES_USER` | `dlh_admin` | ✅ | PostgreSQL superuser with CREATEDB, CREATEROLE permissions. |
| `POSTGRES_PASSWORD` | `change-this-admin-password` | ✅ ⚠️ | Superuser password. **Must be changed before deploying to production!** |
| `DLH_POSTGRES_PORT` | `25432` | – | PostgreSQL port exposed to host. Non-standard port avoids conflict with local PostgreSQL. |

## Custom Workspace (PostgreSQL)

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_DB_NAME` | `dlh_custom` | Name of the business workspace database. Leave empty to skip creation. |
| `CUSTOM_DB_USER` | `dlh_custom_user` | Dedicated user for this workspace. No superuser privileges. |
| `CUSTOM_DB_PASSWORD` | `change-this-custom-password` | ⚠️ Must be changed. |
| `CUSTOM_SCHEMA` | `custom_schema` | Schema inside `CUSTOM_DB_NAME`. ETL pipeline uses this when set. |

## RustFS – Object Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | ⚠️ S3 Access Key (username equivalent). **Change for production.** |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | ⚠️ S3 Secret Key (password equivalent). **Change for production.** |
| `DLH_RUSTFS_API_PORT` | `29100` | S3 API endpoint port (used by boto3, mc client). |
| `DLH_RUSTFS_CONSOLE_PORT` | `29101` | RustFS Web Console port. |
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | S3 endpoint URL between containers in Docker network. |
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Bucket for raw data. Created automatically by `rustfs-init`. |
| `RUSTFS_SILVER_BUCKET` | `silver` | Bucket for cleaned data. |
| `RUSTFS_GOLD_BUCKET` | `gold` | Bucket for aggregated data. |

## ClickHouse – OLAP Engine

| Variable | Default | Description |
|----------|---------|-------------|
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | ClickHouse hostname inside Docker network. |
| `CLICKHOUSE_DB` | `analytics` | Default analytics database. Contains all gold, silver, and metrics tables. |
| `CLICKHOUSE_USER` | `default` | ClickHouse username. |
| `CLICKHOUSE_PASSWORD` | *(empty)* | ClickHouse password. Leave empty for local. ⚠️ Set for production. |
| `DLH_CLICKHOUSE_HTTP_PORT` | `28123` | ClickHouse HTTP API port. |
| `DLH_CLICKHOUSE_TCP_PORT` | `29000` | ClickHouse native TCP protocol port (used by Python `clickhouse-driver`). |

## Mage.ai – ETL Orchestration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAGE_DB_NAME` | `dlh_mage` | PostgreSQL database for Mage internal metadata. |
| `MAGE_DB_USER` | `dlh_mage_user` | Dedicated PostgreSQL user for Mage. |
| `MAGE_DB_PASSWORD` | `change-this-mage-password` | ⚠️ Must be changed. |
| `SOURCE_DB_HOST` | `dlh-postgres` | ETL source database host. |
| `SOURCE_DB_NAME` | `datalakehouse` | Source database name for ETL extraction. |
| `SOURCE_DB_USER` | `dlh_admin` | PostgreSQL user for reading source data. |
| `SOURCE_TABLE_CANDIDATES` | `Demo,test_projects` | Comma-separated list of candidate table names. Pipeline tries each until found. |
| `CSV_UPLOAD_BUCKET` | `bronze` | RustFS bucket to scan for new CSV files. |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Virtual directory prefix to scan for CSV files. |

## Apache Superset – Analytics Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_SUPERSET_PORT` | `28088` | Superset Web UI port. |
| `SUPERSET_SECRET_KEY` | `replace-this-secret` | ⚠️ **Must be changed!** Flask session encryption key. Generate with `openssl rand -hex 32`. |
| `SUPERSET_ADMIN_USER` | `admin` | Superset admin login name. |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | ⚠️ **Must be changed for production!** |

## Grafana – Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_GRAFANA_PORT` | `23001` | Grafana Web UI port. |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin login. |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | ⚠️ **Must be changed for production!** |

### ⚠️ Variables REQUIRED to change before production

```bash
# Generate a random secret key for Superset
openssl rand -hex 32

# In .env:
POSTGRES_PASSWORD=<strong-password>
RUSTFS_ACCESS_KEY=<new-access-key>
RUSTFS_SECRET_KEY=<new-secret-key>
SUPERSET_SECRET_KEY=<openssl-output>
SUPERSET_ADMIN_PASSWORD=<strong-password>
GRAFANA_ADMIN_PASSWORD=<strong-password>
MAGE_DB_PASSWORD=<strong-password>
CLICKHOUSE_PASSWORD=<strong-password>
```

---

# �� Project Structure

```
DataLakehouse/
│
├── 📄 docker-compose.yaml          # All service definitions and volumes
├── 📄 .env.example                 # Environment variable template (copy to .env)
├── 📄 .gitignore                   # Excludes .env and data volumes
├── 📄 io_config.yaml               # Project-level I/O config (legacy)
│
├── 📂 postgres/
│   └── init/
│       ├── 000_create_app_security.sh   # Creates users, databases, schemas
│       ├── 001_lakehouse_metadata.sql   # Lakehouse metadata schema
│       └── 002_sample_data.sql          # 100,000 rows of sample data (Demo table)
│
├── 📂 clickhouse/
│   └── init/
│       └── 001_analytics_schema.sql     # DDL for all analytics tables
│
├── 📂 mage/                         # ETL code and Mage.ai configuration
│   ├── io_config.yaml               # Connection profiles (default, source_db, clickhouse)
│   ├── requirements.txt             # Required Python packages
│   │
│   ├── 📂 data_loaders/             # EXTRACT step – reads source data
│   │   ├── extract_postgres.py      # Reads from PostgreSQL table
│   │   └── extract_csv_from_rustfs.py  # Picks up new CSV files from RustFS bronze
│   │
│   ├── 📂 transformers/             # TRANSFORM step – clean and aggregate
│   │   ├── transform_silver.py      # Clean: dedup, trim, validate, cast types
│   │   ├── transform_gold.py        # Aggregate: daily/weekly/monthly/yearly/region/category
│   │   └── clean_csv_for_reporting.py  # Clean uploaded CSV for reporting
│   │
│   ├── 📂 data_exporters/           # LOAD step – write to destinations
│   │   ├── bronze_to_rustfs.py      # Write raw data to RustFS bronze/
│   │   ├── silver_to_rustfs.py      # Write cleaned data to RustFS silver/
│   │   ├── gold_to_rustfs.py        # Write aggregated data to RustFS gold/
│   │   ├── csv_to_rustfs_silver.py  # Write cleaned CSV to RustFS silver/
│   │   ├── load_to_clickhouse.py    # Read from RustFS and load into ClickHouse
│   │   └── load_csv_reporting_clickhouse.py  # Load CSV metrics into ClickHouse
│   │
│   ├── 📂 pipelines/                # Pipeline definitions (block order)
│   │   ├── etl_postgres_to_lakehouse/   # PostgreSQL → Lakehouse pipeline
│   │   └── etl_csv_upload_to_reporting/ # CSV upload → Dashboard pipeline
│   │
│   └── 📂 utils/
│       └── rustfs_layer_reader.py   # Helper to read Parquet files from RustFS layers
│
├── 📂 superset/
│   └── superset_config.py           # Flask/Superset config (DB URI, cache, security)
│
├── 📂 grafana/
│   └── provisioning/
│       ├── dashboards/              # JSON dashboard definitions
│       └── datasources/             # ClickHouse & PostgreSQL datasource config
│
├── 📂 scripts/
│   ├── setup.sh                             # Interactive setup wizard
│   ├── run_etl_and_dashboard.py             # Run ETL + create demo dashboard
│   ├── create_superset_demo_dashboard.py    # Create Superset demo dashboard
│   ├── demo_to_lakehouse.py                 # Run demo ETL manually
│   └── verify_lakehouse_architecture.py     # Validate the full stack
│
└── 📂 docs/
    ├── DEPLOYMENT_GUIDE.md                  # Detailed deployment guide
    ├── VARIABLES_REFERENCE.md               # Full environment variable reference
    ├── PIPELINE_GUIDE.md                    # ETL pipeline guide
    ├── LAKEHOUSE_ARCHITECTURE.md            # Detailed lakehouse architecture
    ├── ARCHITECTURE_MODERN_STACK.md         # Modern Data Stack overview
    └── architecture.md                      # Architecture diagram
```

---

# 📊 Usage

## 1. Upload CSV (Non-technical users)

```
User → RustFS Console → bronze bucket → csv_upload/
                                              ↓
                                   Mage scans every 5 minutes
                                              ↓
                         extract → clean → write silver → load ClickHouse
                                              ↓
                                   Superset Dashboard updates
```

**Steps:**

1. Open **http://localhost:29101** (RustFS Console)
2. Login with `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` from `.env`
3. Navigate to the **`bronze`** bucket
4. Create the `csv_upload/` folder (if it doesn't exist)
5. Upload your CSV file (first row must be column headers, UTF-8 encoding)
6. Wait for the Mage pipeline to run (up to 5 minutes)
7. View results at **http://localhost:28088**

**CSV format requirements:**
- First row is column headers
- Encoding: UTF-8 (default) or `UTF-8-BOM` (from Excel)
- Separator: `,` (default) – configure via `CSV_UPLOAD_SEPARATOR`
- No limit on columns or rows

## 2. Run PostgreSQL → Lakehouse ETL

### Automatic (scheduled – every 6 hours):
1. Mage extracts the table from PostgreSQL (`SOURCE_TABLE` or auto-detect from `SOURCE_TABLE_CANDIDATES`)
2. Writes raw Parquet to RustFS `bronze/`
3. Transformer cleans data → writes to `silver/`
4. Transformer aggregates by day, week, month, year, region, category → writes to `gold/`
5. Exporter reads from RustFS and loads into ClickHouse
6. Grafana dashboard updates

### Trigger manually:

```bash
# Via Mage CLI (inside container)
docker compose exec mage mage run etl_postgres_to_lakehouse

# Via Mage Web UI
# Open http://localhost:26789 → Pipelines → etl_postgres_to_lakehouse → Run

# Via Mage API
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_run": {"pipeline_uuid": "etl_postgres_to_lakehouse"}}'
```

## 3. Monitor & Observe

```bash
# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f mage
docker compose logs -f clickhouse

# Check service status
docker compose ps

# Check ClickHouse data
docker compose exec clickhouse clickhouse-client \
  --query "SELECT pipeline_name, status, rows_silver, rows_gold_daily, started_at FROM analytics.pipeline_runs ORDER BY started_at DESC LIMIT 10"

# Check row counts
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.gold_demo_daily"
```

## 4. Manage Data via NocoDB

1. Open **http://localhost:28082**
2. Create an admin account on first visit
3. Connect to PostgreSQL at: `postgresql://dlh_admin:<password>@dlh-postgres:5432/datalakehouse`
4. View and edit data without writing SQL

---

# 📈 Dashboards

## Superset – Analytics

**URL:** http://localhost:28088

**Dashboard: Data Lakehouse CSV Demo**

| Chart | Data Source | Description |
|-------|-------------|-------------|
| CSV Data Overview | `csv_quality_metrics` | 10 most recently processed CSV files |
| CSV Quality Metrics | `csv_quality_metrics` | raw/cleaned/dropped/duplicate ratio per file |
| CSV Upload Events | `csv_upload_events` | Status log, errors, processing time |
| CSV Row Comparison | `csv_quality_metrics` | Timeseries: cleaned vs dropped rows over time |

**Recreate the dashboard:**
```bash
docker compose exec -T \
  -e SUPERSET_URL=http://127.0.0.1:8088 \
  superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

## Grafana – Monitoring

**URL:** http://localhost:23001

**Dashboard: Lakehouse Command Center**

| Panel | Description |
|-------|-------------|
| Pipeline Status | Status of the most recent ETL runs |
| Rows Processed | Rows extracted/silver/gold over time |
| CSV Ingestion Rate | CSV ingestion rate (rows/minute) |
| Data Quality Score | Cleaned vs dropped ratio |
| Error Alerts | Alerts when a pipeline fails |

---

# 🔌 API

## Mage.ai API

```bash
# List all pipelines
curl http://localhost:26789/api/pipelines

# Trigger a pipeline
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_run": {"pipeline_uuid": "etl_postgres_to_lakehouse"}}'

# Get run status
curl http://localhost:26789/api/pipeline_runs/<run_id>
```

## ClickHouse HTTP API

```bash
# Simple query
curl "http://localhost:28123/?query=SELECT+count()+FROM+analytics.pipeline_runs"

# Multi-line query
curl http://localhost:28123 \
  -u "default:" \
  -d "SELECT pipeline_name, status, rows_silver FROM analytics.pipeline_runs ORDER BY started_at DESC LIMIT 5 FORMAT Pretty"

# Daily revenue summary
curl http://localhost:28123 \
  -d "SELECT order_date, total_revenue, order_count FROM analytics.gold_demo_daily ORDER BY order_date DESC LIMIT 10 FORMAT JSONEachRow"

# Weekly revenue summary
curl http://localhost:28123 \
  -d "SELECT year_week, week_start, total_revenue, order_count FROM analytics.gold_demo_weekly ORDER BY year_week DESC LIMIT 10 FORMAT JSONEachRow"

# Monthly revenue summary
curl http://localhost:28123 \
  -d "SELECT year_month, month_start, total_revenue, order_count FROM analytics.gold_demo_monthly ORDER BY year_month DESC FORMAT JSONEachRow"

# Yearly revenue summary
curl http://localhost:28123 \
  -d "SELECT year, total_revenue, order_count FROM analytics.gold_demo_yearly ORDER BY year DESC FORMAT JSONEachRow"
```

## Superset REST API

```bash
# Login and get token
TOKEN=$(curl -s -X POST http://localhost:28088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "db"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List dashboards
curl http://localhost:28088/api/v1/dashboard \
  -H "Authorization: Bearer $TOKEN"

# List datasources
curl http://localhost:28088/api/v1/database \
  -H "Authorization: Bearer $TOKEN"
```

---

# 🐛 Troubleshooting

## Service not starting

```bash
# View logs for a specific service
docker compose logs -f mage
docker compose logs -f clickhouse
docker compose logs -f dlh-postgres

# Check service health
docker compose ps

# Restart a single service
docker compose restart mage
```

## Error: "Cannot connect to Docker daemon"

```bash
sudo systemctl start docker
# or on macOS: start Docker Desktop
```

## Error: "Port already in use"

```bash
# Find the process using a port (e.g. 28123)
sudo lsof -i :28123
# or
sudo ss -tlnp | grep 28123

# Change the port in .env
DLH_CLICKHOUSE_HTTP_PORT=38123
```

## ClickHouse not responding

```bash
# Check health
docker compose exec clickhouse wget -qO- http://127.0.0.1:8123/ping

# Open ClickHouse shell
docker compose exec clickhouse clickhouse-client

# Check databases
docker compose exec clickhouse clickhouse-client --query "SHOW DATABASES"

# Check tables in analytics
docker compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
```

## Mage pipeline failing

```bash
# View error logs
docker compose logs mage | grep -i error | tail -20

# Check environment variables inside the container
docker compose exec mage env | grep -E "SOURCE|RUSTFS|CLICKHOUSE"

# Re-run pipeline manually with detailed output
docker compose exec mage mage run etl_postgres_to_lakehouse
```

## RustFS not accessible

```bash
# Check health
docker compose exec rustfs sh -c "curl -s http://127.0.0.1:9000/health"

# View RustFS logs
docker compose logs rustfs | tail -30

# Recreate buckets
docker compose run --rm rustfs-init
```

## Superset dashboard empty / no data

```bash
# Check if data exists in ClickHouse
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.csv_quality_metrics"

# If 0, run the ETL pipeline first:
docker compose exec mage mage run etl_postgres_to_lakehouse

# Recreate Superset dashboard
docker compose exec -T -e SUPERSET_URL=http://127.0.0.1:8088 superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

## Full stack reset

```bash
# ⚠️ Warning: Deletes ALL data in volumes!
docker compose down -v
docker network rm web_network

# Restart from scratch
docker network create web_network
docker compose up -d
```

## Validate the entire system

```bash
# Automated validation script
python3 scripts/verify_lakehouse_architecture.py
```

---

# 📍 Default Ports

| Service | Host Port | Container Port | Notes |
|---------|-----------|---------------|-------|
| PostgreSQL | `25432` | `5432` | Non-standard port to avoid conflicts |
| RustFS S3 API | `29100` | `9000` | boto3, mc client |
| RustFS Console | `29101` | `9001` | Web upload UI |
| ClickHouse HTTP | `28123` | `8123` | REST/curl queries |
| ClickHouse TCP | `29000` | `9000` | Python clickhouse-driver |
| Mage.ai | `26789` | `6789` | ETL UI & API |
| NocoDB | `28082` | `8080` | No-code DB UI |
| Superset | `28088` | `8088` | Analytics dashboards |
| Grafana | `23001` | `3000` | Monitoring UI |

---

# 📝 Important Notes

| Topic | Note |
|-------|------|
| **First run** | Takes 5–15 minutes to pull images and initialize 100k rows of sample data. Run `docker compose ps` and wait for all services to be `healthy`. |
| **Data persistence** | Data is stored in Docker named volumes. `docker compose down` does NOT delete data. `docker compose down -v` does. |
| **Production security** | Change all default passwords. Set `DLH_BIND_IP` appropriately. Add a reverse proxy with SSL/TLS. |
| **Backup** | Regularly back up the `postgres_data`, `clickhouse_data`, and `rustfs_data` volumes. |
| **Scaling** | For production: separate Mage onto its own server, configure ClickHouse replication, use managed PostgreSQL. |
| **Timezone** | Replace `TZ=Asia/Ho_Chi_Minh` with your local timezone. Affects pipeline schedules and log timestamps. |

---

**Author:** HoangThinh2024  
**License:** MIT  
**Documentation:** [docs/](docs/)

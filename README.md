# 🏗️ DataLakehouse – Modern Data Stack
*A minimal, production-ready data lakehouse stack with real-time dashboards and non-technical data upload*

**[Tiếng Việt](#tiếng-việt) | English**

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Components](#components)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Dashboards](#dashboards)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose (v20+)
- 4GB+ RAM available
- Ports: 25432, 28123, 29100-29101, 28088, 23001, 26789 (check [Default Ports](#default-ports))

### Step 1: Clone & Configure

```bash
cd DataLakehouse
cp .env.example .env
```

### Step 2: Create Docker Network

```bash
docker network create web_network
```

### Step 3: Start Stack

```bash
# Start all services
docker compose up -d

# Verify services
docker compose ps
```

### Step 4: Initialize Data (Optional)

```bash
# Automatic bucket creation (one-time)
docker compose --profile bootstrap up -d rustfs-init
```

### Step 5: Access Dashboards

- **Superset Dashboard:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/
  - User: `admin` | Password: `admin`
- **Grafana:** http://localhost:23001
  - User: `admin` | Password: `admin`
- **RustFS Console:** http://localhost:29101
  - Access Key: See `.env` (`RUSTFS_ACCESS_KEY`)

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Data Sources                       │
│   (PostgreSQL, CSV Upload, APIs, Streaming)         │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│               Orchestration & ETL                    │
│   (Mage.ai – scheduled pipelines & transformations) │
│   - etl_postgres_to_lakehouse (every 6 hours)       │
│   - etl_csv_upload_to_reporting (every 5 minutes)   │
└────────┬──────────────────────┬─────────────────────┘
         │                      │
         ▼                      ▼
┌──────────────────┐    ┌────────────────────────────┐
│   RustFS (S3)    │    │   PostgreSQL (Metadata)    │
│  Bronze/Silver   │    │   - App Metadata           │
│    /Gold Layers  │    │   - Configuration          │
└─────────┬────────┘    └──────────────┬─────────────┘
          │                            │
          ▼                            │
┌──────────────────────────────────────────────┐
│         ClickHouse (Analytics Layer)         │
│   - Fast OLAP queries on lake data           │
│   - Real-time aggregations                   │
│   - csv_quality_metrics                      │
│   - csv_upload_events                        │
│   - gold_demo_* (dimensional tables)         │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    ┌──────────┐      ┌──────────┐
    │ Superset │      │ Grafana  │
    │(Analytics│      │(Monitoring
    │ Charts)  │      │ Alerts)  │
    └──────────┘      └──────────┘
```

**Key Principles:**
- **Separation of Concerns:** Metadata (PostgreSQL), Lake Storage (RustFS), Analytics (ClickHouse)
- **Scalability:** Horizontally scalable pipeline & query layers
- **Non-technical UX:** CSV upload via web console → automatic ingestion → instant dashboards
- **Minimal Dependencies:** No dbt, dbt Cloud, GX, or external auth services
- **Data Lakehouse Compliance:** ALL data flows through RustFS layers (Bronze → Silver → Gold) before ClickHouse ingestion

**📘 For detailed architecture documentation, see [Lakehouse Architecture](docs/LAKEHOUSE_ARCHITECTURE.md)**

---

## 🔧 Components

| Component | Role | Port | Database |
|-----------|------|------|----------|
| **PostgreSQL 17** | Central metadata/config | 25432 | - |
| **RustFS** | S3-compatible lake storage | 29100-29101 | - |
| **ClickHouse** | OLAP query acceleration | 28123 | `analytics` |
| **Mage.ai** | Orchestration & ETL pipelines | 26789 | `dlh_mage` |
| **NocoDB** | No-code database UI | 28082 | `dlh_nocodb` |
| **Superset** | Analytics charts & dashboards | 28088 | `dlh_superset` |
| **Grafana** | Monitoring & alerts | 23001 | `dlh_grafana` |

---

## 🔐 Environment Variables

### PostgreSQL

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `dlh_admin` | Superuser for cluster |
| `POSTGRES_PASSWORD` | `change-me` | **⚠️ CHANGE THIS** |
| `POSTGRES_INITDB_ARGS` | (preset) | Initialization arguments |

### RustFS (S3-compatible Storage)

| Variable | Default | Description |
|----------|---------|-------------|
| `RUSTFS_ACCESS_KEY` | `minioadmin` | S3 access key |
| `RUSTFS_SECRET_KEY` | `minioadmin` | S3 secret key |
| `RUSTFS_VOLUMES` | `/data` | Data mount path in container |
| `CSV_UPLOAD_BUCKET` | `bronze` | Bucket for CSV uploads |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Default prefix for CSV files |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | Accept CSV at bucket root |

### ClickHouse

| Variable | Default | Description |
|----------|---------|-------------|
| `CLICKHOUSE_DB` | `analytics` | Default database |
| `CLICKHOUSE_USER` | `default` | Default user (no password) |
| `CLICKHOUSE_HTTP_URL` | `http://dlh-clickhouse:8123` | Internal HTTP endpoint |

### Mage.ai

| Variable | Default | Description |
|----------|---------|-------------|
| `MAGE_DB_NAME` | `dlh_mage` | Mage metadata database |
| `MAGE_DB_USER` | `dlh_mage_user` | Mage DB user |
| `MAGE_DB_PASSWORD` | `change-me` | **⚠️ CHANGE THIS** |
| `SOURCE_DB_NAME` | `dlh_superset` | Source Postgres DB for ETL |
| `SOURCE_TABLE` | `test_projects` | Default source table |
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | RustFS S3 endpoint |

### Superset

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERSET_DB_NAME` | `dlh_superset` | Superset metadata DB |
| `SUPERSET_DB_USER` | `dlh_superset_user` | Superset DB user |
| `SUPERSET_DB_PASSWORD` | `change-me` | **⚠️ CHANGE THIS** |
| `SUPERSET_ADMIN_USER` | `admin` | Dashboard admin user |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | **⚠️ CHANGE THIS** |
| `SUPERSET_SECRET_KEY` | (auto-generated) | Session encryption key |

### Grafana

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_DB_NAME` | `dlh_grafana` | Grafana metadata DB |
| `GRAFANA_DB_USER` | `dlh_grafana_user` | Grafana DB user |
| `GRAFANA_DB_PASSWORD` | `change-me` | **⚠️ CHANGE THIS** |
| `GRAFANA_ADMIN_USER` | `admin` | Dashboard admin user |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | **⚠️ CHANGE THIS** |

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `TZ` | `Asia/Ho_Chi_Minh` | Timezone for all services |
| `DLH_BIND_IP` | `127.0.0.1` | Bind address for services |

---

## 📁 Project Structure

```
DataLakehouse/
├── docker-compose.yaml          # Service orchestration
├── .env.example                 # Template for environment variables
├── .gitignore                   # Git ignore rules
│
├── postgres/
│   └── init/
│       ├── 000_create_app_security.sh    # User & DB setup
│       ├── 001_lakehouse_metadata.sql    # Metadata schema
│       └── 002_sample_data.sql           # Sample data (100k rows)
│
├── clickhouse/
│   └── init/
│       └── 001_analytics_schema.sql      # Analytics tables
│
├── mage/                        # ETL orchestration
│   ├── io_config.yaml           # Mage I/O configuration
│   ├── metadata.yaml            # Pipeline metadata
│   ├── data_loaders/            # Data extraction
│   │   ├── extract_postgres.py
│   │   └── extract_csv_from_rustfs.py
│   ├── transformers/            # Data transformation
│   │   ├── transform_silver.py
│   │   ├── transform_gold.py
│   │   └── clean_csv_for_reporting.py
│   ├── data_exporters/          # Data loading
│   │   ├── load_to_clickhouse.py
│   │   └── load_csv_reporting_clickhouse.py
│   └── pipelines/               # Pipeline definitions
│       ├── etl_postgres_to_lakehouse/
│       └── etl_csv_upload_to_reporting/
│
├── superset/
│   └── superset_config.py       # Superset configuration
│
├── grafana/
│   └── provisioning/
│       ├── dashboards/          # Dashboard JSON files
│       └── datasources/         # ClickHouse datasource config
│
├── scripts/
│   ├── create_superset_demo_dashboard.py  # Auto dashboard creation
│   └── demo_to_lakehouse.py     # Manual demo script
│
├── docs/
│   ├── ARCHITECTURE_MODERN_STACK.md
│   └── architecture.md
│
└── README.md                    # This file
```

---

## 📊 Usage

### 1. Upload CSV (Non-technical Users)

**Via RustFS Web Console:**

1. Open **http://localhost:29101**
2. Login with `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` from `.env`
3. Navigate to bucket `bronze`
4. Upload CSV to `csv_upload/` folder (or anywhere if `CSV_UPLOAD_ALLOW_ANYWHERE=true`)
5. Mage pipeline (runs every 5 min) automatically:
   - Detects new CSV
   - Cleans data (trim, dedup, normalize headers)
   - Loads to `analytics.csv_quality_metrics` in ClickHouse
   - Creates quality report in Superset dashboard

### 2. Monitor CSV Ingestion

**Superset Dashboard:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/

Charts available:
- **CSV Data Overview:** Latest 10 ingested files
- **CSV Quality Metrics:** Latest 50 files with row counts
- **CSV Upload Events:** Success/error logs
- **CSV Row Processing Comparison:** Cleaned vs dropped rows (timeseries chart)

### 3. PostgreSQL ETL

**Automatic (every 6 hours):**
1. Mage extracts from `dlh_superset.test_projects` (100k rows)
2. Writes to RustFS bronze layer
3. Transforms to silver/gold in ClickHouse
4. Updates Grafana dashboard

**Manual Trigger:**
```bash
docker compose exec mage mage run etl_postgres_to_lakehouse
```

---

## 📈 Dashboards

### Superset: Data Lakehouse CSV Demo 100k

**URL:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/

**Charts:**
1. **CSV Data Overview (Table)** - Latest 10 ingested files with metadata
2. **CSV Quality Metrics (Table)** - File-level metrics (raw/cleaned/dropped/duplicates)
3. **CSV Upload Events (Table)** - Ingestion status, errors, timestamps
4. **CSV Row Processing Comparison (Timeseries)** - Cleaned vs dropped rows trends

### Grafana: Lakehouse Monitoring

**URL:** http://localhost:23001

**Command Center Dashboard:**
- ETL pipeline status
- CSV ingestion metrics
- Data quality indicators
- Error alerts

---

## 🔌 API Endpoints

### Mage.ai API

```bash
# List pipelines
curl http://localhost:26789/api/pipelines

# Trigger ETL
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_uuid": "etl_postgres_to_lakehouse"}'
```

### Superset API

```bash
# Login
curl -X POST http://localhost:28088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "db"}'

# List dashboards
curl http://localhost:28088/api/v1/dashboard \
  -H "Authorization: Bearer <TOKEN>"
```

### ClickHouse HTTP

```bash
# Query directly
curl http://localhost:28123 \
  -d "SELECT COUNT(*) FROM analytics.csv_quality_metrics"
```

---

## 🐛 Troubleshooting

### Docker Services Not Starting

**Check logs:**
```bash
docker compose logs -f [service_name]
```

**Reset everything:**
```bash
docker compose down -v
docker network rm web_network
docker network create web_network
docker compose up -d
```

### ClickHouse Connection Error

**Verify connectivity:**
```bash
docker compose exec clickhouse clickhouse-client --query "SELECT 1"
```

**Check database:**
```bash
docker compose exec clickhouse clickhouse-client \
  --query "SHOW DATABASES"
```

### Mage Pipeline Fails

**Check logs:**
```bash
docker compose logs mage | grep ERROR
```

**Re-run manually:**
```bash
docker compose exec mage mage run [pipeline_name]
```

### Superset Dashboard Empty

**Verify ClickHouse data:**
```bash
docker compose exec clickhouse clickhouse-client \
  --query "SELECT COUNT(*) FROM analytics.csv_quality_metrics"
```

**Recreate dashboard:**
```bash
docker compose exec -T -e SUPERSET_URL=http://127.0.0.1:8088 superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

---

## 📍 Default Ports

| Service | Port | Note |
|---------|------|------|
| PostgreSQL | 25432 | Changed to avoid conflicts |
| RustFS API | 29100 | S3 endpoint |
| RustFS Console | 29101 | Web UI |
| ClickHouse HTTP | 28123 | Query endpoint |
| ClickHouse TCP | 29000 | Native protocol |
| Mage | 26789 | Orchestration UI |
| NocoDB | 28082 | Database UI |
| Superset | 28088 | Analytics dashboards |
| Grafana | 23001 | Monitoring UI |

---

## 📝 Notes

- **First Run:** First startup may take 5-10 minutes for service initialization and data loading
- **Volume Persistence:** All data persists in Docker volumes. Reset with `docker compose down -v` if needed
- **SSL/TLS:** Not configured by default. Add reverse proxy for production use
- **Scaling:** For production, run separate instances of Mage, ClickHouse replicas, etc.
- **Backup:** Regularly backup `clickhouse_data`, `postgres_data` volumes

---

<a name="tiếng-việt"></a>

---

# 🏗️ DataLakehouse – Ngăn xếp Dữ liệu Hiện đại
*Một ngăn xếp lakehouse tối thiểu, sẵn sàng cho production với bảng điều khiển real-time và upload dữ liệu không kỹ thuật*

---

## 📋 Mục lục

- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Kiến trúc](#kiến-trúc)
- [Thành phần](#thành-phần)
- [Các biến môi trường](#các-biến-môi-trường)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [Cách sử dụng](#cách-sử-dụng)
- [Bảng điều khiển](#bảng-điều-khiển)
- [Điểm cuối API](#điểm-cuối-api)
- [Khắc phục sự cố](#khắc-phục-sự-cố)

---

## 🚀 Bắt đầu nhanh

### Yêu cầu
- Docker & Docker Compose (v20+)
- RAM khả dụng: 4GB+
- Cổng: 25432, 28123, 29100-29101, 28088, 23001, 26789 (xem [Cổng mặc định](#cổng-mặc-định))

### Bước 1: Clone & Cấu hình

```bash
cd DataLakehouse
cp .env.example .env
```

### Bước 2: Tạo Docker Network

```bash
docker network create web_network
```

### Bước 3: Khởi động Ngăn xếp

```bash
# Khởi động tất cả services
docker compose up -d

# Kiểm tra services
docker compose ps
```

### Bước 4: Khởi tạo Dữ liệu (Tùy chọn)

```bash
# Tạo bucket tự động (chỉ một lần)
docker compose --profile bootstrap up -d rustfs-init
```

### Bước 5: Truy cập Bảng điều khiển

- **Superset Dashboard:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/
  - User: `admin` | Mật khẩu: `admin`
- **Grafana:** http://localhost:23001
  - User: `admin` | Mật khẩu: `admin`
- **RustFS Console:** http://localhost:29101
  - Access Key: Xem `.env` (`RUSTFS_ACCESS_KEY`)

---

## 🏛️ Kiến trúc

```
┌─────────────────────────────────────────────────────┐
│                   Nguồn dữ liệu                      │
│   (PostgreSQL, Upload CSV, APIs, Streaming)         │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│               Điều phối & ETL                       │
│   (Mage.ai – scheduled pipelines & transformations) │
│   - etl_postgres_to_lakehouse (cứ 6 giờ)           │
│   - etl_csv_upload_to_reporting (cứ 5 phút)        │
└────────┬──────────────────────┬─────────────────────┘
         │                      │
         ▼                      ▼
┌──────────────────┐    ┌────────────────────────────┐
│   RustFS (S3)    │    │   PostgreSQL (Metadata)    │
│  Bronze/Silver   │    │   - Metadata ứng dụng      │
│    /Gold Layers  │    │   - Cấu hình              │
└─────────┬────────┘    └──────────────┬─────────────┘
          │                            │
          ▼                            │
┌──────────────────────────────────────────────┐
│         ClickHouse (Lớp phân tích)           │
│   - Truy vấn OLAP nhanh trên dữ liệu lake   │
│   - Tổng hợp real-time                     │
│   - csv_quality_metrics                      │
│   - csv_upload_events                        │
│   - gold_demo_* (bảng chiều)                │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    ┌──────────┐      ┌──────────┐
    │ Superset │      │ Grafana  │
    │(Analytics│      │(Giám sát │
    │ Charts)  │      │ Cảnh báo)│
    └──────────┘      └──────────┘
```

**Nguyên tắc chính:**
- **Tách rời các mối quan tâm:** Metadata (PostgreSQL), Lưu trữ Lake (RustFS), Phân tích (ClickHouse)
- **Khả năng mở rộng:** Pipeline & lớp truy vấn có thể mở rộng ngang
- **UX không kỹ thuật:** Upload CSV via web console → tự động nhập → bảng điều khiển tức thì
- **Phụ thuộc tối thiểu:** Không dbt, dbt Cloud, GX, hoặc xác thực bên ngoài

---

## 🔧 Thành phần

| Thành phần | Vai trò | Cổng | Cơ sở dữ liệu |
|-----------|--------|------|--------------|
| **PostgreSQL 17** | Metadata/config trung tâm | 25432 | - |
| **RustFS** | Lưu trữ lakehouse tương thích S3 | 29100-29101 | - |
| **ClickHouse** | Tăng tốc truy vấn OLAP | 28123 | `analytics` |
| **Mage.ai** | Điều phối & pipeline ETL | 26789 | `dlh_mage` |
| **NocoDB** | UI cơ sở dữ liệu không code | 28082 | `dlh_nocodb` |
| **Superset** | Biểu đồ phân tích & bảng điều khiển | 28088 | `dlh_superset` |
| **Grafana** | Giám sát & cảnh báo | 23001 | `dlh_grafana` |

---

## 🔐 Các biến môi trường

### PostgreSQL

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `POSTGRES_USER` | `dlh_admin` | Superuser của cluster |
| `POSTGRES_PASSWORD` | `change-me` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |
| `POSTGRES_INITDB_ARGS` | (preset) | Đối số khởi tạo |

### RustFS (Lưu trữ tương thích S3)

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `RUSTFS_ACCESS_KEY` | `minioadmin` | Khóa truy cập S3 |
| `RUSTFS_SECRET_KEY` | `minioadmin` | Khóa bí mật S3 |
| `RUSTFS_VOLUMES` | `/data` | Đường dẫn mount dữ liệu trong container |
| `CSV_UPLOAD_BUCKET` | `bronze` | Bucket cho upload CSV |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Tiền tố mặc định cho file CSV |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | Chấp nhận CSV ở root bucket |

### ClickHouse

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `CLICKHOUSE_DB` | `analytics` | Cơ sở dữ liệu mặc định |
| `CLICKHOUSE_USER` | `default` | Người dùng mặc định (không mật khẩu) |
| `CLICKHOUSE_HTTP_URL` | `http://dlh-clickhouse:8123` | Điểm cuối HTTP nội bộ |

### Mage.ai

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `MAGE_DB_NAME` | `dlh_mage` | Cơ sở dữ liệu metadata của Mage |
| `MAGE_DB_USER` | `dlh_mage_user` | Người dùng DB Mage |
| `MAGE_DB_PASSWORD` | `change-me` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |
| `SOURCE_DB_NAME` | `dlh_superset` | DB PostgreSQL nguồn cho ETL |
| `SOURCE_TABLE` | `test_projects` | Bảng nguồn mặc định |
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | Điểm cuối S3 RustFS |

### Superset

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `SUPERSET_DB_NAME` | `dlh_superset` | DB metadata Superset |
| `SUPERSET_DB_USER` | `dlh_superset_user` | Người dùng DB Superset |
| `SUPERSET_DB_PASSWORD` | `change-me` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |
| `SUPERSET_ADMIN_USER` | `admin` | Người dùng admin bảng điều khiển |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |
| `SUPERSET_SECRET_KEY` | (tự động tạo) | Khóa mã hóa phiên |

### Grafana

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `GRAFANA_DB_NAME` | `dlh_grafana` | DB metadata Grafana |
| `GRAFANA_DB_USER` | `dlh_grafana_user` | Người dùng DB Grafana |
| `GRAFANA_DB_PASSWORD` | `change-me` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |
| `GRAFANA_ADMIN_USER` | `admin` | Người dùng admin bảng điều khiển |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | **⚠️ THAY ĐỔI ĐIỀU NÀY** |

### Chung

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `TZ` | `Asia/Ho_Chi_Minh` | Múi giờ cho tất cả services |
| `DLH_BIND_IP` | `127.0.0.1` | Địa chỉ bind cho services |

---

## 📁 Cấu trúc dự án

```
DataLakehouse/
├── docker-compose.yaml          # Điều phối services
├── .env.example                 # Mẫu biến môi trường
├── .gitignore                   # Quy tắc git ignore
│
├── postgres/
│   └── init/
│       ├── 000_create_app_security.sh    # Thiết lập user & DB
│       ├── 001_lakehouse_metadata.sql    # Schema metadata
│       └── 002_sample_data.sql           # Dữ liệu mẫu (100k rows)
│
├── clickhouse/
│   └── init/
│       └── 001_analytics_schema.sql      # Bảng analytics
│
├── mage/                        # Điều phối ETL
│   ├── io_config.yaml           # Cấu hình I/O của Mage
│   ├── metadata.yaml            # Metadata pipeline
│   ├── data_loaders/            # Trích xuất dữ liệu
│   │   ├── extract_postgres.py
│   │   └── extract_csv_from_rustfs.py
│   ├── transformers/            # Chuyển đổi dữ liệu
│   │   ├── transform_silver.py
│   │   ├── transform_gold.py
│   │   └── clean_csv_for_reporting.py
│   ├── data_exporters/          # Tải dữ liệu
│   │   ├── load_to_clickhouse.py
│   │   └── load_csv_reporting_clickhouse.py
│   └── pipelines/               # Định nghĩa pipeline
│       ├── etl_postgres_to_lakehouse/
│       └── etl_csv_upload_to_reporting/
│
├── superset/
│   └── superset_config.py       # Cấu hình Superset
│
├── grafana/
│   └── provisioning/
│       ├── dashboards/          # File JSON bảng điều khiển
│       └── datasources/         # Cấu hình datasource ClickHouse
│
├── scripts/
│   ├── create_superset_demo_dashboard.py  # Tạo dashboard tự động
│   └── demo_to_lakehouse.py     # Script demo thủ công
│
├── docs/
│   ├── ARCHITECTURE_MODERN_STACK.md
│   └── architecture.md
│
└── README.md                    # Tệp này
```

---

## 📊 Cách sử dụng

### 1. Upload CSV (Người dùng không kỹ thuật)

**Thông qua RustFS Web Console:**

1. Mở **http://localhost:29101**
2. Đăng nhập với `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` từ `.env`
3. Điều hướng đến bucket `bronze`
4. Upload CSV vào thư mục `csv_upload/` (hoặc bất cứ nơi nào nếu `CSV_UPLOAD_ALLOW_ANYWHERE=true`)
5. Pipeline Mage (chạy cứ 5 phút) tự động:
   - Phát hiện CSV mới
   - Làm sạch dữ liệu (trim, dedup, chuẩn hóa header)
   - Tải vào `analytics.csv_quality_metrics` trong ClickHouse
   - Tạo báo cáo chất lượng trong bảng điều khiển Superset

### 2. Giám sát nhập CSV

**Bảng điều khiển Superset:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/

Biểu đồ khả dụng:
- **CSV Data Overview:** 10 file được nhập gần nhất
- **CSV Quality Metrics:** 50 file gần nhất với số dòng
- **CSV Upload Events:** Nhật ký thành công/lỗi
- **CSV Row Processing Comparison:** Biểu đồ thời gian series so sánh dòng làm sạch vs bị loại bỏ

### 3. ETL PostgreSQL

**Tự động (cứ 6 giờ):**
1. Mage trích xuất từ `dlh_superset.test_projects` (100k rows)
2. Ghi vào lớp bronze RustFS
3. Chuyển đổi thành silver/gold trong ClickHouse
4. Cập nhật bảng điều khiển Grafana

**Kích hoạt thủ công:**
```bash
docker compose exec mage mage run etl_postgres_to_lakehouse
```

---

## 📈 Bảng điều khiển

### Superset: Data Lakehouse CSV Demo 100k

**URL:** http://localhost:28088/superset/dashboard/data-lakehouse-csv-demo-100k/

**Biểu đồ:**
1. **CSV Data Overview (Bảng)** - 10 file được nhập gần nhất với metadata
2. **CSV Quality Metrics (Bảng)** - Số liệu ở cấp độ file (raw/cleaned/dropped/duplicates)
3. **CSV Upload Events (Bảng)** - Trạng thái nhập, lỗi, dấu thời gian
4. **CSV Row Processing Comparison (Timeseries)** - Xu hướng dòng làm sạch vs bị loại bỏ

### Grafana: Lakehouse Monitoring

**URL:** http://localhost:23001

**Bảng điều khiển Trung tâm chỉ huy:**
- Trạng thái pipeline ETL
- Số liệu nhập CSV
- Chỉ số chất lượng dữ liệu
- Cảnh báo lỗi

---

## 🔌 Điểm cuối API

### Mage.ai API

```bash
# Liệt kê pipelines
curl http://localhost:26789/api/pipelines

# Kích hoạt ETL
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_uuid": "etl_postgres_to_lakehouse"}'
```

### Superset API

```bash
# Đăng nhập
curl -X POST http://localhost:28088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "db"}'

# Liệt kê bảng điều khiển
curl http://localhost:28088/api/v1/dashboard \
  -H "Authorization: Bearer <TOKEN>"
```

### ClickHouse HTTP

```bash
# Truy vấn trực tiếp
curl http://localhost:28123 \
  -d "SELECT COUNT(*) FROM analytics.csv_quality_metrics"
```

---

## 🐛 Khắc phục sự cố

### Docker Services không khởi động

**Kiểm tra log:**
```bash
docker compose logs -f [service_name]
```

**Đặt lại mọi thứ:**
```bash
docker compose down -v
docker network rm web_network
docker network create web_network
docker compose up -d
```

### Lỗi kết nối ClickHouse

**Xác minh kết nối:**
```bash
docker compose exec clickhouse clickhouse-client --query "SELECT 1"
```

**Kiểm tra cơ sở dữ liệu:**
```bash
docker compose exec clickhouse clickhouse-client \
  --query "SHOW DATABASES"
```

### Pipeline Mage thất bại

**Kiểm tra log:**
```bash
docker compose logs mage | grep ERROR
```

**Chạy lại thủ công:**
```bash
docker compose exec mage mage run [pipeline_name]
```

### Bảng điều khiển Superset trống

**Xác minh dữ liệu ClickHouse:**
```bash
docker compose exec clickhouse clickhouse-client \
  --query "SELECT COUNT(*) FROM analytics.csv_quality_metrics"
```

**Tạo lại bảng điều khiển:**
```bash
docker compose exec -T -e SUPERSET_URL=http://127.0.0.1:8088 superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

---

## 📍 Cổng mặc định

| Service | Cổng | Ghi chú |
|---------|------|--------|
| PostgreSQL | 25432 | Thay đổi để tránh xung đột |
| RustFS API | 29100 | Điểm cuối S3 |
| RustFS Console | 29101 | Web UI |
| ClickHouse HTTP | 28123 | Điểm cuối truy vấn |
| ClickHouse TCP | 29000 | Giao thức gốc |
| Mage | 26789 | UI điều phối |
| NocoDB | 28082 | UI cơ sở dữ liệu |
| Superset | 28088 | Bảng điều khiển phân tích |
| Grafana | 23001 | UI giám sát |

---

## 📝 Ghi chú

- **Lần chạy đầu tiên:** Khởi động lần đầu có thể mất 5-10 phút để khởi tạo service và tải dữ liệu
- **Tính bền vững của Volume:** Tất cả dữ liệu vẫn tồn tại trong Docker volumes. Đặt lại với `docker compose down -v` nếu cần
- **SSL/TLS:** Không được cấu hình theo mặc định. Thêm reverse proxy cho sử dụng production
- **Mở rộng:** Để production, hãy chạy các instance Mage, bản sao ClickHouse tách rời, v.v.
- **Sao lưu:** Sao lưu thường xuyên các volume `clickhouse_data`, `postgres_data`

---

**Tác giả:** DataLakehouse Contributors  
**Cập nhật:** April 18, 2026  
**Giấy phép:** MIT

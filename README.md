# DataLakehouse – Modern Data Stack

Hướng dẫn triển khai Modern Data Stack (MDS) cho Data Lakehouse trên Docker.

**Kiến trúc**: PostgreSQL + RustFS + ClickHouse + Mage.ai + dbt + Great Expectations + Metabase + Superset + Grafana + Nginx Proxy Manager (10+ services)

## 1. Kiến trúc tổng quan

Xem chi tiết tại [docs/ARCHITECTURE_MODERN_STACK.md](docs/ARCHITECTURE_MODERN_STACK.md).

5 tầng:
- **INGEST**: Upload/API/Manual tools
- **STORAGE**: PostgreSQL (OLTP) + RustFS (Data Lake) + ClickHouse (OLAP)
- **PROCESS**: Mage.ai (ETL) + dbt (Transform) + Great Expectations (QA)
- **SERVING**: Adminer + NocoDB + Metabase (+ Nginx Proxy Manager)
- **REPORT**: Apache Superset + Grafana

## 2. Chuẩn bị môi trường

### 2.1 Yêu cầu hệ thống

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM tối thiểu (8GB khuyến nghị)
- 20GB disk space

### 2.2 Tạo file .env

Copy .env.example và cập nhật:

```bash
cp .env.example .env
```

Các biến quan trọng:
- `POSTGRES_PASSWORD`: Mật khẩu PostgreSQL
- `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY`: Credentials S3
- `SUPERSET_SECRET_KEY`: Secret key Superset (đổi lại!)
- `GRAFANA_ADMIN_PASSWORD`: Admin password Grafana

Chi tiết xem trong [.env.example](.env.example)

### 2.3 Cấu trúc thư mục

```
DataLakehouse/
├── docker-compose.yaml          # Main stack config
├── .env.example                 # Mẫu biến môi trường
├── .env                         # Biến thực tế (gitignore)
├── postgres/
│   └── init/
│       └── 001_lakehouse_metadata.sql
├── dbt/                         # dbt project (tạo sau)
├── mage/                        # Mage pipelines (tạo sau)
└── docs/
    ├── ARCHITECTURE_MODERN_STACK.md
    └── architecture.md
```

## 3. Khởi động hệ thống

### 3.1 Start stack

```bash
docker compose up -d
```

Các service sẽ khởi động theo thứ tự dependency.

### 3.2 Kiểm tra trạng thái

```bash
docker compose ps
```

Chờ tất cả service có status `Up`.

### 3.3 Xem log

```bash
docker compose logs -f
docker compose logs -f postgres
docker compose logs -f mage
```

### 3.4 Stop stack

```bash
docker compose down
```

Xóa toàn bộ volume (dữ liệu):

```bash
docker compose down -v
```

## 4. Truy cập các dịch vụ

| Service | URL | Mục đích |
|---------|-----|---------|
| PostgreSQL | localhost:55432 | OLTP, metadata |
| RustFS Console | http://localhost:19001 | Quản lý Bronze/Silver/Gold |
| RustFS S3 API | http://localhost:19000 | S3-API endpoint |
| ClickHouse | http://localhost:8123 | Query interface |
| Mage.ai | http://localhost:6789 | ETL pipeline builder |
| Adminer | http://localhost:8080 | Database admin |
| NocoDB | http://localhost:8081 | Database UI + API |
| Metabase | http://localhost:3000 | Internal BI |
| Superset | http://localhost:8088 | Advanced dashboards |
| Grafana | http://localhost:3001 | Monitoring |
| Nginx Proxy Mgr | http://localhost:81 | Proxy config |

### 4.1 Credentials mặc định

```
PostgreSQL:
  user: postgres
  password: postgres (change in .env!)

RustFS:
  access_key: rustfsadmin
  secret_key: rustfsadmin

Metabase / Superset / Grafana:
  user: admin
  password: admin
```

## 5. Quy trình làm việc điển hình

### 5.1 Ingest dữ liệu

1. Upload file vào NocoDB hoặc RustFS console
2. File đặt vào bucket `bronze/<domain>/<dataset>/dt=YYYY-MM-DD/`

### 5.2 Build pipeline

1. Mở Mage.ai tại http://localhost:6789
2. Tạo pipeline để load từ Bronze
3. Trigger transformation, trigger Great Expectations checks
4. Output sang Silver bucket qua S3 API

### 5.3 Transform (dbt)

1. Tạo dbt project trong thư mục `dbt/`
2. Define model cho Silver → Gold transformation
3. Chạy `docker exec dbt dbt run --profiles-dir /root/.dbt`

### 5.4 Phân tích & Dashboard

1. Kết nối Metabase/Superset tới PostgreSQL hoặc ClickHouse
2. Tạo question/chart từ tầng Gold
3. Publish dashboard để team xem

## 6. Kiểm tra sau startup

### 6.1 PostgreSQL + metadata

```bash
docker exec -it postgres psql -U postgres -d datalakehouse -c "\dt lakehouse.*"
```

### 6.2 RustFS buckets

```bash
docker compose logs rustfs-init | tail -20
```

### 6.3 ClickHouse

```bash
docker exec -it clickhouse clickhouse-client -q "SELECT version()"
```

## 7. Xử lý sự cố

### 7.1 Port bị chiếm

```bash
METABASE_PORT=3010 docker compose up -d
```

### 7.2 Chạy một service riêng

```bash
docker compose up -d postgres
docker compose up -d rustfs
```

### 7.3 Reset toàn bộ

```bash
docker compose down -v
docker system prune -f a
docker compose up -d
```

### 7.4 Out of memory

Disable một số service:

```bash
docker compose stop superset grafana
```

## 8. Tiếp theo

1. Tạo dbt project cho transformation logic
2. Thiết lập Mage pipelines  
3. Kết nối data sources vào Bronze
4. Xây dựng BI models trên Gold
5. Setup data quality rules
6. Configure data lineage & governance

Chi tiết xem [docs/ARCHITECTURE_MODERN_STACK.md](docs/ARCHITECTURE_MODERN_STACK.md).

# 📖 Tham chiếu Biến môi trường – DataLakehouse

Tài liệu này mô tả chi tiết **mọi biến môi trường** trong file `.env` của dự án DataLakehouse.

> **Cách sử dụng:**
> 1. Sao chép `.env.example` → `.env`
> 2. Chỉnh sửa các biến theo môi trường của bạn
> 3. Các biến có ký hiệu ⚠️ **BẮT BUỘC** phải thay đổi trước production

---

## Mục lục

1. [Cài đặt toàn cục](#1-cài-đặt-toàn-cục)
2. [Phiên bản Docker Image](#2-phiên-bản-docker-image)
3. [PostgreSQL – Admin](#3-postgresql--admin)
4. [PostgreSQL – Custom Workspace](#4-postgresql--custom-workspace)
5. [RustFS – Object Storage](#5-rustfs--object-storage)
6. [ClickHouse – OLAP Engine](#6-clickhouse--olap-engine)
7. [Mage.ai – ETL Orchestration](#7-mageai--etl-orchestration)
8. [NocoDB – No-code DB UI](#8-nocodb--no-code-db-ui)
9. [Apache Superset – Analytics](#9-apache-superset--analytics)
10. [Grafana – Monitoring](#10-grafana--monitoring)
11. [Nginx Proxy Manager (Tùy chọn)](#11-nginx-proxy-manager-tùy-chọn)
12. [Bảng tóm tắt nhanh](#12-bảng-tóm-tắt-nhanh)

---

## 1. Cài đặt toàn cục

### `TZ`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `Asia/Ho_Chi_Minh` |
| **Bắt buộc** | ✅ |
| **Ảnh hưởng đến** | Tất cả containers |

**Mô tả:** Múi giờ áp dụng đồng nhất cho toàn bộ stack. Ảnh hưởng đến:
- Timestamp trong log của tất cả services
- Lịch biểu chạy pipeline Mage.ai (cron schedule)
- Hiển thị thời gian trên Grafana/Superset
- `PGTZ` trong PostgreSQL (timezone cho datetime queries)

**Giá trị hợp lệ:** Tên timezone IANA tiêu chuẩn

```bash
# Ví dụ các múi giờ phổ biến
TZ=Asia/Ho_Chi_Minh   # Việt Nam (UTC+7)
TZ=UTC                # Coordinated Universal Time
TZ=America/New_York   # Eastern Time
TZ=Europe/London      # GMT/BST
TZ=Asia/Singapore     # Singapore (UTC+8)
```

---

### `DLH_BIND_IP`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `127.0.0.1` |
| **Bắt buộc** | ✅ |
| **Ảnh hưởng đến** | Tất cả `ports:` trong docker-compose.yaml |

**Mô tả:** Địa chỉ IP trên máy host mà các cổng dịch vụ được bind (lắng nghe). Đây là biện pháp bảo mật quan trọng nhất trong cấu hình mạng.

**Cách hoạt động:** Trong `docker-compose.yaml`, các cổng được định nghĩa là:
```yaml
ports:
  - "${DLH_BIND_IP}:${DLH_MAGE_PORT}:6789"
```
Docker sẽ dịch thành: `127.0.0.1:26789:6789` – nghĩa là chỉ kết nối từ `127.0.0.1` (localhost) mới có thể vào cổng 26789.

**Các tùy chọn:**

| Giá trị | Ai có thể truy cập | Trường hợp sử dụng |
|---------|------------------|-------------------|
| `127.0.0.1` | Chỉ máy đang chạy Docker | Development local, an toàn nhất |
| `192.168.1.x` | Các máy trong cùng mạng LAN | Team development, demo nội bộ |
| `0.0.0.0` | Tất cả mọi nơi | **Chỉ dùng khi có firewall + reverse proxy!** |

```bash
# Tìm địa chỉ IP LAN của bạn
ip addr show        # Linux
ifconfig            # macOS
ipconfig            # Windows
```

---

### `POSTGRES_HOST`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh-postgres` |
| **Bắt buộc** | ✅ |
| **Ảnh hưởng đến** | Mage, Superset, Grafana, NocoDB |

**Mô tả:** Hostname của PostgreSQL server **bên trong Docker network**. Khi các containers liên lạc với nhau, họ dùng tên container làm hostname.

**Khi nào cần thay đổi:**
- Dùng PostgreSQL bên ngoài Docker (managed DB service, VPS riêng)
- Ví dụ: `POSTGRES_HOST=db.example.com` hoặc `POSTGRES_HOST=10.0.0.5`

> ⚠️ Nếu thay đổi `POSTGRES_HOST`, cũng cần cập nhật `mage/io_config.yaml` để đảm bảo Mage dùng đúng host.

---

## 2. Phiên bản Docker Image

Các biến này control phiên bản image Docker được pull. Được định nghĩa ở một chỗ để dễ nâng cấp toàn stack.

| Biến | Mặc định | Service |
|------|---------|---------|
| `POSTGRES_IMAGE_VERSION` | `17-alpine` | PostgreSQL |
| `RUSTFS_IMAGE_VERSION` | `latest` | RustFS |
| `MINIO_MC_IMAGE_VERSION` | `latest` | MinIO mc (dùng bởi rustfs-init) |
| `CLICKHOUSE_IMAGE_VERSION` | `latest` | ClickHouse |
| `MAGE_IMAGE_VERSION` | `latest` | Mage.ai |
| `NOCODB_IMAGE_VERSION` | `latest` | NocoDB |
| `SUPERSET_IMAGE_VERSION` | `latest` | Apache Superset |
| `GRAFANA_IMAGE_VERSION` | `latest` | Grafana |

**Khuyến nghị Production:**

```bash
# Ghim version cụ thể để đảm bảo tính ổn định và có thể rollback
POSTGRES_IMAGE_VERSION=17.2-alpine
CLICKHOUSE_IMAGE_VERSION=24.3.3.102
MAGE_IMAGE_VERSION=0.9.73
GRAFANA_IMAGE_VERSION=10.4.2
SUPERSET_IMAGE_VERSION=3.1.3
```

**Cách xem version hiện tại đang dùng:**
```bash
docker compose images
```

---

## 3. PostgreSQL – Admin

### `POSTGRES_DB`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `datalakehouse` |
| **Bắt buộc** | ✅ |

**Mô tả:** Tên database admin được tạo khi PostgreSQL khởi động lần đầu. Database này là "home" của superuser `POSTGRES_USER`. Nó cũng chứa dữ liệu mẫu Demo (100k dòng) được tạo bởi `002_sample_data.sql`.

**Liên quan đến:** `SOURCE_DB_NAME` – ETL pipeline trích xuất từ database này (nếu `SOURCE_DB_NAME` không được đặt riêng).

---

### `POSTGRES_USER`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh_admin` |
| **Bắt buộc** | ✅ |

**Mô tả:** Tên superuser PostgreSQL được tạo khi container khởi tạo. User này có quyền `SUPERUSER`, `CREATEDB`, `CREATEROLE`. Script bootstrap (`000_create_app_security.sh`) dùng user này để tạo các user và database khác cho Mage, Superset, Grafana, NocoDB.

---

### `POSTGRES_PASSWORD`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `change-this-admin-password` |
| **Bắt buộc** | ✅ ⚠️ **THAY ĐỔI NGAY** |

**Mô tả:** Mật khẩu của superuser PostgreSQL. Biến này được dùng bởi **nhiều services** để kết nối PostgreSQL:
- `postgres-bootstrap` để tạo roles
- `source_db` profile trong Mage
- Grafana datasource

**Yêu cầu mật khẩu mạnh:**
```bash
# Tạo mật khẩu ngẫu nhiên 32 ký tự
openssl rand -base64 24
# Ví dụ output: X9mK2pLqR8vYnJwZ3tHbFcDsAeGu4iNo
```

---

### `DLH_POSTGRES_PORT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `25432` |
| **Bắt buộc** | – |

**Mô tả:** Cổng PostgreSQL được expose ra máy host (cổng bên ngoài). Cổng 5432 là mặc định của PostgreSQL, nên dùng cổng khác (25432) để tránh xung đột nếu bạn đã có PostgreSQL cài trực tiếp trên máy.

**Kết nối từ máy host:**
```bash
psql -h localhost -p 25432 -U dlh_admin -d datalakehouse
```

---

## 4. PostgreSQL – Custom Workspace

Nhóm biến này tạo một workspace database riêng biệt để người dùng lưu dữ liệu nghiệp vụ, tách khỏi metadata hệ thống.

### `CUSTOM_DB_NAME`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh_custom` |
| **Tùy chọn** | Để trống (`CUSTOM_DB_NAME=`) để bỏ qua |

**Mô tả:** Tên database riêng cho workspace nghiệp vụ. Khi biến này có giá trị, script bootstrap sẽ tự động:
1. Tạo database `<CUSTOM_DB_NAME>`
2. Tạo user `<CUSTOM_DB_USER>` với quyền đầy đủ trên database này
3. Tạo schema `<CUSTOM_SCHEMA>` trong database

**Khi nên dùng:** Khi bạn muốn nhập dữ liệu của mình vào một database riêng, không trộn lẫn với `datalakehouse` admin DB.

---

### `CUSTOM_DB_USER`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh_custom_user` |

**Mô tả:** User PostgreSQL riêng cho workspace. Chỉ có quyền trên `CUSTOM_DB_NAME`, không có quyền superuser. Dùng user này trong ứng dụng của bạn thay vì superuser.

---

### `CUSTOM_DB_PASSWORD`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `change-this-custom-password` |
| **⚠️ Thay đổi** | Cần thiết |

---

### `CUSTOM_SCHEMA`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `custom_schema` |

**Mô tả:** Tên schema trong `CUSTOM_DB_NAME`. Tách biệt tables của bạn khỏi schema `public` mặc định. ETL pipeline Mage sẽ dùng schema này khi `CUSTOM_SCHEMA` được đặt.

---

## 5. RustFS – Object Storage

RustFS là S3-compatible object storage viết bằng Rust, dùng làm data lake layer lưu trữ tất cả file Parquet và CSV.

### `RUSTFS_ACCESS_KEY`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `rustfsadmin` |
| **Bắt buộc** | ✅ ⚠️ |

**Mô tả:** Access Key để xác thực với RustFS S3 API. Tương đương với "username" trong hệ thống S3. Dùng bởi:
- Mage.ai pipelines (thông qua boto3)
- `rustfs-init` container (tạo buckets)
- NocoDB (Litestream backup)
- Bạn khi truy cập từ CLI hoặc code

**Yêu cầu:** 3-20 ký tự, chỉ chứa chữ cái, số, dấu gạch dưới, dấu gạch ngang.

---

### `RUSTFS_SECRET_KEY`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `rustfsadmin` |
| **Bắt buộc** | ✅ ⚠️ |

**Mô tả:** Secret Key tương đương "mật khẩu" trong S3. Phải dài tối thiểu 8 ký tự. **Không bao giờ commit giá trị thật vào git.**

```bash
# Tạo secret key ngẫu nhiên
openssl rand -hex 16
```

---

### `DLH_RUSTFS_API_PORT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `29100` |

**Mô tả:** Cổng S3 API của RustFS trên máy host. Dùng để kết nối từ bên ngoài Docker (CLI, scripts Python chạy trên host).

**Kết nối từ host bằng AWS CLI / mc:**
```bash
# MinIO mc client
mc alias set local http://localhost:29100 rustfsadmin rustfsadmin
mc ls local/

# AWS CLI (với endpoint override)
aws --endpoint-url http://localhost:29100 s3 ls s3://bronze/
```

---

### `DLH_RUSTFS_CONSOLE_PORT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `29101` |

**Mô tả:** Cổng Web Console của RustFS. Mở http://localhost:29101 để upload file, quản lý buckets qua giao diện web.

---

### `RUSTFS_VOLUMES`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `/data` |

**Mô tả:** Đường dẫn **bên trong container** nơi RustFS lưu trữ file vật lý. Được mount từ Docker volume `rustfs_data`. Thường không cần thay đổi.

---

### `RUSTFS_ADDRESS` / `RUSTFS_CONSOLE_ADDRESS`

| Biến | Mặc định |
|------|---------|
| `RUSTFS_ADDRESS` | `0.0.0.0:9000` |
| `RUSTFS_CONSOLE_ADDRESS` | `0.0.0.0:9001` |

**Mô tả:** Địa chỉ bind **bên trong container**. `0.0.0.0` = lắng nghe trên tất cả interface của container (cần thiết để Docker có thể forward port). **Không thay đổi.**

---

### `RUSTFS_ENDPOINT_URL`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `http://dlh-rustfs:9000` |

**Mô tả:** URL S3 endpoint mà **các containers khác** dùng để kết nối RustFS. Dùng tên container `dlh-rustfs` làm hostname (DNS resolution tự động trong Docker network).

**Khi nào thay đổi:** Nếu RustFS chạy trên máy/mạng khác.

---

### `RUSTFS_BRONZE_BUCKET` / `RUSTFS_SILVER_BUCKET` / `RUSTFS_GOLD_BUCKET`

| Biến | Mặc định | Ý nghĩa |
|------|---------|---------|
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Dữ liệu thô (raw), chưa xử lý |
| `RUSTFS_SILVER_BUCKET` | `silver` | Dữ liệu đã làm sạch và validate |
| `RUSTFS_GOLD_BUCKET` | `gold` | Dữ liệu đã tổng hợp (aggregated) |

**Mô tả:** Tên các buckets trong kiến trúc Medallion. Các buckets này được tạo tự động bởi container `rustfs-init` khi stack khởi động lần đầu.

**Cấu trúc file trong bucket:**
```
bronze/
  raw_<run_id>_<timestamp>.parquet

silver/
  silver_<run_id>_<timestamp>.parquet
  csv_silver/
    <run_id>/
      cleaned_<run_id>.parquet

gold/
  gold_daily_<run_id>_<timestamp>.parquet
  gold_region_<run_id>_<timestamp>.parquet
  gold_category_<run_id>_<timestamp>.parquet
```

---

### `RUSTFS_CORS_ALLOWED_ORIGINS` / `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS`

| Biến | Mặc định |
|------|---------|
| `RUSTFS_CORS_ALLOWED_ORIGINS` | `http://localhost:29100` |
| `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS` | `http://localhost:29101` |

**Mô tả:** Danh sách origins được phép trong CORS headers. Cần thiết khi frontend JavaScript gọi S3 API trực tiếp từ browser.

**Khi triển khai trên server:**
```bash
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=https://storage-console.yourdomain.com
```

---

### `LITESTREAM_S3_ENDPOINT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `http://dlh-rustfs:9000` |

**Mô tả:** Endpoint S3 cho Litestream – công cụ backup realtime SQLite của NocoDB. Litestream stream WAL của NocoDB lên RustFS liên tục, đảm bảo không mất dữ liệu khi container restart.

---

## 6. ClickHouse – OLAP Engine

### `CLICKHOUSE_HOST`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh-clickhouse` |

**Mô tả:** Hostname của ClickHouse **trong Docker network**. Dùng bởi Mage pipelines (clickhouse-driver) và Grafana datasource.

---

### `CLICKHOUSE_DB`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `analytics` |

**Mô tả:** Tên database analytics mặc định trong ClickHouse. Tất cả bảng dữ liệu (silver, gold, metrics) được tạo trong database này. Được định nghĩa trong `clickhouse/init/001_analytics_schema.sql`.

**Các bảng trong `analytics`:**

| Bảng | Kích thước dữ liệu | Mô tả |
|------|------------------|-------|
| `silver_demo` | ~100k dòng | Dữ liệu PostgreSQL đã làm sạch |
| `gold_demo_daily` | ~365 dòng/năm | Tổng hợp theo ngày |
| `gold_demo_by_region` | ~10 dòng | Tổng hợp theo vùng địa lý |
| `gold_demo_by_category` | ~10 dòng | Tổng hợp theo danh mục |
| `csv_clean_rows` | Tùy | Dòng CSV đã xử lý (JSON) |
| `csv_quality_metrics` | 1 dòng/file | Chỉ số chất lượng CSV |
| `csv_upload_events` | 1 dòng/lần chạy | Log sự kiện |
| `pipeline_runs` | 1 dòng/lần chạy | Lịch sử ETL |

---

### `CLICKHOUSE_USER`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `default` |

**Mô tả:** Username ClickHouse. `default` là user built-in có quyền đầy đủ. Cho production, khuyến nghị tạo user riêng với quyền hạn chế.

---

### `CLICKHOUSE_PASSWORD`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | *(trống)* |
| **⚠️ Thay đổi cho production** | |

**Mô tả:** Mật khẩu ClickHouse. **Để trống** là hợp lệ cho môi trường local vì ClickHouse trong Docker network không tiếp xúc internet. Tuy nhiên, **luôn đặt mật khẩu cho production**.

```bash
# Tạo mật khẩu và hash SHA256 (ClickHouse dùng SHA256)
echo -n "YourPassword123" | sha256sum
```

---

### `DLH_CLICKHOUSE_HTTP_PORT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `28123` |

**Mô tả:** Cổng HTTP API của ClickHouse trên máy host. Dùng cho:
- Kết nối từ browser (Play UI tại `http://localhost:28123/play`)
- `curl` queries
- Grafana datasource khi kết nối từ host
- DBeaver, DataGrip với ClickHouse JDBC driver

---

### `DLH_CLICKHOUSE_TCP_PORT`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `29000` |

**Mô tả:** Cổng TCP native protocol của ClickHouse. Dùng bởi `clickhouse-driver` Python library (hiệu năng tốt hơn HTTP cho bulk insert).

**Lưu ý:** Cổng mặc định ClickHouse TCP là 9000, nhưng vì RustFS cũng dùng 9000 bên trong container, ta map sang 29000 trên host để tránh nhầm lẫn.

---

## 7. Mage.ai – ETL Orchestration

### Database connection

#### `MAGE_DB_NAME`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `dlh_mage` |

**Mô tả:** Database PostgreSQL lưu trữ metadata nội bộ của Mage: pipeline definitions, block code, run history, secrets, variables. Được tạo tự động bởi bootstrap script.

---

#### `MAGE_DB_USER` / `MAGE_DB_PASSWORD`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `MAGE_DB_USER` | `dlh_mage_user` | User riêng cho Mage |
| `MAGE_DB_PASSWORD` | `change-this-mage-password` | ⚠️ Thay đổi |

**Connection URL được dùng:**
```
postgresql+psycopg2://dlh_mage_user:<password>@dlh-postgres:5432/dlh_mage
```

---

#### `MAGE_CODE_PATH` / `USER_CODE_PATH`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `MAGE_CODE_PATH` | `/home/src` | Mount point của `./mage` |
| `USER_CODE_PATH` | `/home/src` | Alias, dùng cho một số phiên bản Mage |

**Mô tả:** Đường dẫn **bên trong container** nơi Mage đọc code pipeline. Được mount từ thư mục `./mage` trên host. Thay đổi nếu bạn mount code ở đường dẫn khác.

---

### ETL Source – Nguồn dữ liệu

#### `SOURCE_DB_HOST`

| Mặc định | `dlh-postgres` |
|---------|----------------|

**Mô tả:** Host của database nguồn ETL. Mặc định là PostgreSQL trong cùng Docker network. Thay đổi để trỏ đến database ngoài (vd: production DB, read replica).

---

#### `SOURCE_DB_PORT`

| Mặc định | `5432` |
|---------|--------|

**Mô tả:** Cổng PostgreSQL nguồn. Cổng **bên trong** Docker network (không phải cổng host `25432`).

---

#### `SOURCE_DB_NAME`

| Mặc định | `datalakehouse` |
|---------|----------------|

**Mô tả:** Tên database PostgreSQL để extract dữ liệu ETL. Khi bạn tạo `CUSTOM_DB_NAME`, hãy cập nhật `SOURCE_DB_NAME` thành tên đó để pipeline extract từ đúng database.

```bash
# Nếu dùng custom workspace:
CUSTOM_DB_NAME=my_business_db
SOURCE_DB_NAME=my_business_db
SOURCE_DB_USER=${CUSTOM_DB_USER}
SOURCE_DB_PASSWORD=${CUSTOM_DB_PASSWORD}
SOURCE_SCHEMA=${CUSTOM_SCHEMA}
```

---

#### `SOURCE_DB_USER` / `SOURCE_DB_PASSWORD`

**Mô tả:** Credentials để đọc từ database nguồn. Dùng user có quyền `SELECT` trên bảng cần extract.

---

#### `SOURCE_SCHEMA`

| Mặc định | `public` |
|---------|----------|

**Mô tả:** Schema PostgreSQL chứa bảng cần extract. Khi dùng `CUSTOM_SCHEMA`, đặt giá trị này tương ứng.

---

#### `SOURCE_TABLE`

| Mặc định | *(trống)* |
|---------|-----------|

**Mô tả:** Tên bảng **cụ thể** để extract. Khi **để trống**, pipeline tự động tìm bảng từ `SOURCE_TABLE_CANDIDATES`.

**Logic ưu tiên:**
1. Nếu `SOURCE_TABLE` được đặt → dùng bảng đó (báo lỗi nếu không tồn tại)
2. Nếu trống → thử từng tên trong `SOURCE_TABLE_CANDIDATES` cho đến khi tìm thấy
3. Nếu không tìm thấy bảng nào → raise error với danh sách bảng có sẵn

```bash
# Ví dụ: extract bảng cụ thể
SOURCE_TABLE=orders

# Ví dụ: để trống, tự tìm
SOURCE_TABLE=
SOURCE_TABLE_CANDIDATES=orders,transactions,sales_data
```

---

#### `SOURCE_TABLE_CANDIDATES`

| Mặc định | `Demo,test_projects` |
|---------|----------------------|

**Mô tả:** Danh sách tên bảng ứng viên, phân cách bằng dấu phẩy. Pipeline thử từng tên theo thứ tự, lấy bảng đầu tiên tìm thấy. So sánh **không phân biệt hoa/thường**.

```bash
# Thêm bảng của bạn vào danh sách
SOURCE_TABLE_CANDIDATES=Demo,test_projects,my_table,orders
```

---

### CSV Upload Pipeline

#### `CSV_UPLOAD_BUCKET`

| Mặc định | `bronze` |
|---------|----------|

**Mô tả:** Tên bucket RustFS mà pipeline `etl_csv_upload_to_reporting` quét để tìm file CSV mới. Thông thường là `bronze` (lớp raw).

---

#### `CSV_UPLOAD_PREFIX`

| Mặc định | `csv_upload/` |
|---------|--------------|

**Mô tả:** Tiền tố (virtual folder) trong bucket để upload CSV. Pipeline ưu tiên xử lý file trong prefix này trước. Người dùng nên upload vào `bronze/csv_upload/` để đảm bảo thứ tự xử lý.

---

#### `CSV_UPLOAD_ALLOW_ANYWHERE`

| Mặc định | `true` |
|---------|--------|

**Mô tả:** Kiểm soát phạm vi quét CSV trong bucket.

| Giá trị | Hành vi |
|---------|---------|
| `true` | Quét tất cả file `.csv` trong toàn bucket (kể cả ngoài `CSV_UPLOAD_PREFIX`) |
| `false` | Chỉ quét file trong đường dẫn `CSV_UPLOAD_PREFIX` |

**Khuyến nghị:** Giữ `true` cho tiện lợi. Đặt `false` nếu muốn kiểm soát chặt vị trí upload.

---

#### `CSV_UPLOAD_SEPARATOR`

| Mặc định | `,` |
|---------|-----|

**Mô tả:** Ký tự phân cách cột khi đọc file CSV.

| Giá trị | Dùng khi |
|---------|---------|
| `,` | CSV tiêu chuẩn (mặc định) |
| `;` | CSV xuất từ Excel châu Âu |
| `\t` | TSV (Tab-Separated Values) |
| `\|` | Pipe-separated |

---

#### `CSV_UPLOAD_ENCODING`

| Mặc định | `utf-8` |
|---------|---------|

**Mô tả:** Encoding ký tự của file CSV khi đọc bằng `pandas.read_csv()`.

| Giá trị | Dùng khi |
|---------|---------|
| `utf-8` | Mặc định, hầu hết file CSV |
| `utf-8-sig` | CSV từ Excel (có BOM) |
| `latin-1` | CSV cũ từ Windows với ký tự đặc biệt châu Âu |
| `cp1252` | CSV từ Windows tiếng Anh/Tây Âu |

---

#### `CSV_UPLOAD_SCAN_LIMIT`

| Mặc định | `200` |
|---------|-------|

**Mô tả:** Số file tối đa mà pipeline quét trong một lần chạy khi liệt kê bucket. Mỗi lần chạy pipeline chỉ xử lý **1 file** (file đầu tiên chưa được xử lý), nhưng giới hạn này xác định bao nhiêu file được liệt kê để tìm.

**Tăng khi:** Bucket có rất nhiều file đã được xử lý và file mới nằm ở cuối danh sách.

---

## 8. NocoDB – No-code DB UI

### `DLH_NOCODB_PORT`

| Mặc định | `28082` |
|---------|---------|

**Mô tả:** Cổng NocoDB Web UI trên máy host.

---

### `NOCODB_DB_NAME` / `NOCODB_DB_USER` / `NOCODB_DB_PASSWORD`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `NOCODB_DB_NAME` | `dlh_nocodb` | Database metadata NocoDB |
| `NOCODB_DB_USER` | `dlh_nocodb_user` | User riêng |
| `NOCODB_DB_PASSWORD` | `change-this-nocodb-password` | ⚠️ Thay đổi |

**Mô tả:** NocoDB dùng PostgreSQL làm metadata store thay vì SQLite mặc định. Điều này cho phép NocoDB scale tốt hơn và dữ liệu bền vững hơn.

---

### `NOCODB_PUBLIC_URL` / `NOCODB_BACKEND_URL`

| Biến | Mặc định |
|------|---------|
| `NOCODB_PUBLIC_URL` | `http://127.0.0.1:28082` |
| `NOCODB_BACKEND_URL` | `http://127.0.0.1:28082` |

**Mô tả:** URL công khai của NocoDB. Dùng cho:
- Tạo share links đến bảng/view
- SSO callbacks
- Embed trong iframe

**Khi deploy trên server:**
```bash
NOCODB_PUBLIC_URL=https://data.yourdomain.com
NOCODB_BACKEND_URL=https://data.yourdomain.com
```

---

## 9. Apache Superset – Analytics

### `DLH_SUPERSET_PORT`

| Mặc định | `28088` |
|---------|---------|

---

### `SUPERSET_SECRET_KEY`

| Thuộc tính | Giá trị |
|-----------|--------|
| **Mặc định** | `replace-this-secret` |
| **Bắt buộc** | ✅ ⚠️ **BẮT BUỘC THAY ĐỔI** |

**Mô tả:** Secret key Flask dùng để ký và mã hóa:
- Session cookies của người dùng đã đăng nhập
- CSRF tokens
- "Remember me" tokens

**Hậu quả nếu không thay đổi:** Attacker có thể giả mạo session cookie nếu biết default key.

```bash
# Tạo secret key ngẫu nhiên và an toàn
python3 -c "import secrets; print(secrets.token_hex(32))"
# hoặc
openssl rand -hex 32
```

---

### `SUPERSET_DB_NAME` / `SUPERSET_DB_USER` / `SUPERSET_DB_PASSWORD`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `SUPERSET_DB_NAME` | `dlh_superset` | Lưu: dashboards, charts, datasets, users |
| `SUPERSET_DB_USER` | `dlh_superset_user` | User riêng cho Superset |
| `SUPERSET_DB_PASSWORD` | `change-this-superset-db-password` | ⚠️ Thay đổi |

---

### `SUPERSET_ADMIN_USER` / `SUPERSET_ADMIN_PASSWORD` / `SUPERSET_ADMIN_EMAIL`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `SUPERSET_ADMIN_USER` | `admin` | Tên đăng nhập |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | ⚠️ **Thay đổi ngay!** |
| `SUPERSET_ADMIN_EMAIL` | `admin@superset.local` | Email (dùng để reset mật khẩu) |

**Lưu ý:** Admin account được tạo lần đầu khi container khởi động với lệnh `superset fab create-admin`. Nếu account đã tồn tại, lệnh được bỏ qua (`|| true`).

---

### `SUPERSET_CONFIG_PATH`

| Mặc định | `/app/pythonpath/superset_config.py` |
|---------|--------------------------------------|

**Mô tả:** Đường dẫn **bên trong container** đến file config Python của Superset. File này được mount từ `./superset/superset_config.py` trên host. Chứa cài đặt database, cache, feature flags.

---

### `SUPERSET_LOAD_EXAMPLES`

| Mặc định | `no` |
|---------|------|

**Mô tả:** Kiểm soát việc tải dữ liệu mẫu của Superset.

| Giá trị | Hành vi |
|---------|---------|
| `no` | Không tải (nhanh hơn, khuyến nghị) |
| `yes` | Tải ~20 dashboard mẫu từ Superset (tốn 2-3 phút thêm) |

---

## 10. Grafana – Monitoring

### `DLH_GRAFANA_PORT`

| Mặc định | `23001` |
|---------|---------|

---

### `GRAFANA_DB_NAME` / `GRAFANA_DB_USER` / `GRAFANA_DB_PASSWORD`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `GRAFANA_DB_NAME` | `dlh_grafana` | Lưu: dashboards, users, alerts |
| `GRAFANA_DB_USER` | `dlh_grafana_user` | User riêng |
| `GRAFANA_DB_PASSWORD` | `change-this-grafana-db-password` | ⚠️ Thay đổi |

---

### `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `GRAFANA_ADMIN_USER` | `admin` | Tài khoản admin đầu tiên |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | ⚠️ **Thay đổi cho production!** |

---

### `GF_DATABASE_HOST`

| Mặc định | `dlh-postgres:5432` |
|---------|---------------------|

**Mô tả:** Địa chỉ PostgreSQL cho Grafana theo format đặc biệt `<host>:<port>`. Grafana dùng biến này trực tiếp (không phải `POSTGRES_HOST:5432`). Đảm bảo giá trị này nhất quán với `POSTGRES_HOST`.

---

### `GF_INSTALL_PLUGINS`

| Mặc định | `grafana-piechart-panel,grafana-clickhouse-datasource` |
|---------|-------------------------------------------------------|

**Mô tả:** Danh sách plugin Grafana cài tự động khi container khởi động (phân cách bằng dấu phẩy). Plugins quan trọng:
- `grafana-clickhouse-datasource`: Kết nối ClickHouse từ Grafana
- `grafana-piechart-panel`: Biểu đồ tròn

**Thêm plugins:**
```bash
GF_INSTALL_PLUGINS=grafana-piechart-panel,grafana-clickhouse-datasource,grafana-worldmap-panel
```

---

## 11. Nginx Proxy Manager (Tùy chọn)

Chỉ dùng khi bỏ comment block `nginx-proxy-manager` trong `docker-compose.yaml`.

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `DLH_NPM_HTTP_PORT` | `28080` | Cổng HTTP (proxy cho các services) |
| `DLH_NPM_HTTPS_PORT` | `28443` | Cổng HTTPS với SSL termination |
| `DLH_NPM_ADMIN_PORT` | `28081` | Cổng Admin UI của Nginx Proxy Manager |

**Khi nào dùng:** Khi muốn đặt reverse proxy trước các services với SSL/TLS, custom domain, authentication.

---

## 12. Bảng tóm tắt nhanh

### ⚠️ Biến BẮT BUỘC thay đổi trước production

| Biến | Lý do |
|------|-------|
| `POSTGRES_PASSWORD` | Bảo vệ database admin |
| `RUSTFS_ACCESS_KEY` | Xác thực S3 |
| `RUSTFS_SECRET_KEY` | Xác thực S3 |
| `SUPERSET_SECRET_KEY` | Bảo vệ session Superset |
| `SUPERSET_ADMIN_PASSWORD` | Tài khoản admin dashboard |
| `GRAFANA_ADMIN_PASSWORD` | Tài khoản admin monitoring |
| `MAGE_DB_PASSWORD` | Bảo vệ DB metadata ETL |
| `NOCODB_DB_PASSWORD` | Bảo vệ DB metadata NocoDB |
| `SUPERSET_DB_PASSWORD` | Bảo vệ DB metadata Superset |
| `GRAFANA_DB_PASSWORD` | Bảo vệ DB metadata Grafana |
| `CUSTOM_DB_PASSWORD` | Nếu dùng custom workspace |
| `CLICKHOUSE_PASSWORD` | Nếu deploy production |

### Script tạo mật khẩu ngẫu nhiên

```bash
# Tạo tất cả mật khẩu mạnh cùng lúc
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)"
echo "RUSTFS_ACCESS_KEY=rustfs$(openssl rand -hex 7)"
echo "RUSTFS_SECRET_KEY=$(openssl rand -base64 24)"
echo "SUPERSET_SECRET_KEY=$(openssl rand -hex 32)"
echo "SUPERSET_ADMIN_PASSWORD=$(openssl rand -base64 16)"
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)"
echo "MAGE_DB_PASSWORD=$(openssl rand -base64 16)"
echo "CLICKHOUSE_PASSWORD=$(openssl rand -base64 16)"
```

### Biến thường thay đổi

| Biến | Lý do thay đổi |
|------|---------------|
| `TZ` | Điều chỉnh múi giờ |
| `DLH_BIND_IP` | Truy cập từ LAN/internet |
| `SOURCE_TABLE` | Chỉ định bảng ETL cụ thể |
| `SOURCE_DB_NAME` | Trỏ đến database nguồn thực |
| `CUSTOM_DB_NAME` | Tạo workspace riêng |
| `CSV_UPLOAD_SEPARATOR` | Khi CSV dùng `;` thay vì `,` |
| `CSV_UPLOAD_ENCODING` | Khi CSV từ Excel (utf-8-sig) |

---

*Tài liệu cập nhật: 2026. Xem README.md để biết thêm.*

# 🏗️ DataLakehouse – Modern Data Stack

> **Ngăn xếp Data Lakehouse hiện đại** – Tích hợp đầy đủ từ lưu trữ, xử lý ETL, đến bảng điều khiển phân tích, triển khai dễ dàng bằng Docker Compose.

**[Tiếng Việt](#-datalakehouse--ngăn-xếp-dữ-liệu-hiện-đại) | [English](#-quick-start)**

> 📚 **Tài liệu đầy đủ:**
> - [Hướng dẫn Triển khai chi tiết](docs/DEPLOYMENT_GUIDE.md)
> - [Tham chiếu Biến môi trường](docs/VARIABLES_REFERENCE.md)
> - [Hướng dẫn ETL Pipeline](docs/PIPELINE_GUIDE.md)
> - [Kiến trúc Lakehouse](docs/LAKEHOUSE_ARCHITECTURE.md)

---

## 📋 Mục lục / Table of Contents

| Tiếng Việt | English |
|---|---|
| [Bắt đầu nhanh](#-bắt-đầu-nhanh) | [Quick Start](#-quick-start) |
| [Kiến trúc hệ thống](#-kiến-trúc-hệ-thống) | [Architecture](#-architecture) |
| [Thành phần](#-thành-phần) | [Components](#-components) |
| [Biến môi trường](#-biến-môi-trường-chi-tiết) | [Environment Variables](#-environment-variables-reference) |
| [Cấu trúc dự án](#-cấu-trúc-dự-án) | [Project Structure](#-project-structure) |
| [Cách sử dụng](#-cách-sử-dụng) | [Usage](#-usage) |
| [Bảng điều khiển](#-bảng-điều-khiển) | [Dashboards](#-dashboards) |
| [API](#-api) | [API](#-api) |
| [Khắc phục sự cố](#-khắc-phục-sự-cố) | [Troubleshooting](#-troubleshooting) |

---

# 🚀 Quick Start

## Prerequisites / Yêu cầu

| Yêu cầu | Phiên bản tối thiểu | Ghi chú |
|---------|-------------------|---------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| RAM khả dụng | 4 GB | 8 GB khuyến nghị |
| Dung lượng đĩa | 10 GB | Cho data volumes |
| Cổng trống | Xem bảng bên dưới | Kiểm tra trước khi chạy |

### Kiểm tra cổng trống

```bash
# Kiểm tra tất cả cổng DataLakehouse có đang bị chiếm không
for port in 25432 29100 29101 28123 29000 26789 28082 28088 23001; do
  ss -tlnp | grep -q ":$port " && echo "⚠ Port $port is IN USE" || echo "✓ Port $port is free"
done
```

---

## Bước 1 – Clone & Cấu hình

```bash
# Clone repo
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse

# Sao chép file cấu hình mẫu
cp .env.example .env
```

> 💡 **Khuyến nghị:** Dùng script tương tác để cấu hình tự động:
> ```bash
> bash scripts/setup.sh
> ```
> Script sẽ hỏi từng biến, ghi `.env`, tạo network và khởi động stack.

**Hoặc** chỉnh sửa `.env` thủ công – xem [Biến môi trường chi tiết](#-biến-môi-trường-chi-tiết).

---

## Bước 2 – Tạo Docker Network

```bash
docker network create web_network
```

> ⚠️ Bước này chỉ cần làm **một lần**. Nếu đã tồn tại, Docker sẽ báo lỗi nhưng không ảnh hưởng gì.

---

## Bước 3 – Khởi động Stack

```bash
# Khởi động tất cả services ở chế độ nền
docker compose up -d

# Kiểm tra trạng thái (chờ tất cả "healthy")
docker compose ps

# Xem log tổng hợp
docker compose logs -f
```

> ⏳ **Lần đầu chạy:** Mất 5–15 phút để tải image và khởi tạo dữ liệu mẫu 100k dòng.

---

## Bước 4 – Truy cập Giao diện

| Dịch vụ | URL | Tài khoản |
|---------|-----|-----------|
| 🗄 **RustFS Console** (Object Storage) | http://localhost:29101 | Xem `RUSTFS_ACCESS_KEY` trong `.env` |
| 📊 **Superset** (Analytics Dashboard) | http://localhost:28088 | `admin` / `admin` |
| 📈 **Grafana** (Monitoring) | http://localhost:23001 | `admin` / `admin` |
| ⚙️ **Mage.ai** (ETL Orchestration) | http://localhost:26789 | Không cần đăng nhập |
| 🗃 **NocoDB** (No-code DB UI) | http://localhost:28082 | Tạo tài khoản lần đầu |

> 🔐 **Bảo mật:** Thay đổi tất cả mật khẩu mặc định trong `.env` trước khi triển khai production!

---

# 🏛️ Architecture

## Sơ đồ luồng dữ liệu

```
┌──────────────────────────────────────────────────────────────────┐
│                        NGUỒN DỮ LIỆU                             │
│          PostgreSQL  ·  Upload CSV  ·  APIs  ·  Streaming        │
└───────────────────────────┬──────────────────────────────────────┘
                            │  Extract
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    LAYER 3 – XỬ LÝ (Mage.ai)                    │
│                                                                  │
│  Pipeline 1: etl_postgres_to_lakehouse  (mỗi 6 giờ)            │
│    extract_postgres → transform_silver → transform_gold          │
│    → bronze_to_rustfs → silver_to_rustfs → gold_to_rustfs        │
│    → load_to_clickhouse                                          │
│                                                                  │
│  Pipeline 2: etl_csv_upload_to_reporting  (mỗi 5 phút)          │
│    extract_csv_from_rustfs → clean_csv_for_reporting             │
│    → csv_to_rustfs_silver → load_csv_reporting_clickhouse        │
└──────┬────────────────────────────────────────────────┬──────────┘
       │ Write                                          │ Write
       ▼                                                ▼
┌─────────────────────┐              ┌──────────────────────────────┐
│   LAYER 2 – LƯU TRỮ │              │  LAYER 2 – METADATA          │
│   RustFS (S3-compat) │              │  PostgreSQL 17               │
│                      │              │                              │
│  bronze/  ← raw data │              │  dlh_mage     (Mage meta)   │
│  silver/  ← cleaned  │              │  dlh_superset (Superset meta)│
│  gold/    ← aggregated│              │  dlh_grafana  (Grafana meta) │
│  csv_upload/← CSVs   │              │  dlh_nocodb   (NocoDB meta)  │
└──────────┬───────────┘              │  dlh_custom   (Workspace)    │
           │ Read (lakehouse)          └──────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                  LAYER 4 – PHỤC VỤ (ClickHouse)                  │
│                                                                  │
│  analytics.silver_demo          (dữ liệu đã làm sạch)           │
│  analytics.gold_demo_daily      (tổng hợp theo ngày)            │
│  analytics.gold_demo_by_region  (tổng hợp theo vùng)            │
│  analytics.gold_demo_by_category(tổng hợp theo danh mục)        │
│  analytics.csv_clean_rows       (dòng CSV đã xử lý)             │
│  analytics.csv_quality_metrics  (chất lượng CSV)                 │
│  analytics.csv_upload_events    (sự kiện upload)                 │
│  analytics.pipeline_runs        (lịch sử pipeline)              │
└──────────────────────┬───────────────────────────────────────────┘
                       │ Query
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐      ┌──────────────────────────┐
│  LAYER 5 – BÁO CÁO│      │  LAYER 5 – GIÁM SÁT      │
│  Apache Superset  │      │  Grafana                  │
│  (Analytics UI)   │      │  (Monitoring & Alerts)    │
└──────────────────┘      └──────────────────────────┘
          │                         │
          ▼                         ▼
┌──────────────────────────────────────────────────────┐
│                  NGƯỜI DÙNG CUỐI                      │
│   Business Analysts · Data Scientists · Developers   │
└──────────────────────────────────────────────────────┘
```

## Nguyên tắc thiết kế

| Nguyên tắc | Mô tả |
|-----------|-------|
| **Tách biệt mối quan tâm** | Metadata (PostgreSQL), Lake Storage (RustFS), Analytics (ClickHouse) |
| **Kiến trúc Medallion** | Bronze (raw) → Silver (clean) → Gold (aggregated) |
| **Immutability** | Dữ liệu trong RustFS không thay đổi, ClickHouse đọc từ lake |
| **Khả năng phục hồi** | Toàn bộ dữ liệu có thể tái tạo từ RustFS |
| **UX phi kỹ thuật** | Upload CSV qua web → tự động nhập → dashboard ngay lập tức |
| **Không phụ thuộc bên ngoài** | Không dbt, không GX, không dịch vụ xác thực ngoài |

---

# 🔧 Components

| Thành phần | Vai trò | Cổng host | Cơ sở dữ liệu | Image |
|-----------|---------|-----------|--------------|-------|
| **PostgreSQL 17** | Metadata/config trung tâm cho tất cả services | `25432` | `datalakehouse` | `postgres:17-alpine` |
| **RustFS** | Object storage tương thích S3 (Bronze/Silver/Gold) | `29100` (API), `29101` (Console) | – | `rustfs/rustfs` |
| **ClickHouse** | OLAP engine cho phân tích nhanh | `28123` (HTTP), `29000` (TCP) | `analytics` | `clickhouse/clickhouse-server` |
| **Mage.ai** | Điều phối ETL pipelines có lịch biểu | `26789` | `dlh_mage` | `mageai/mageai` |
| **NocoDB** | Giao diện no-code để xem/chỉnh sửa PostgreSQL | `28082` | `dlh_nocodb` | `nocodb/nocodb` |
| **Apache Superset** | Dashboard phân tích & biểu đồ | `28088` | `dlh_superset` | `apache/superset` |
| **Grafana** | Giám sát, cảnh báo, metrics | `23001` | `dlh_grafana` | `grafana/grafana` |

---

# 🔐 Environment Variables Reference

> 📖 Xem tài liệu đầy đủ: [docs/VARIABLES_REFERENCE.md](docs/VARIABLES_REFERENCE.md)

## Cài đặt toàn cục

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `TZ` | `Asia/Ho_Chi_Minh` | Múi giờ áp dụng cho **tất cả** containers. Ảnh hưởng đến timestamp log, lịch biểu pipeline, biểu đồ Grafana. Sử dụng tên TZ chuẩn IANA (vd: `UTC`, `America/New_York`). |
| `DLH_BIND_IP` | `127.0.0.1` | Địa chỉ IP mà các cổng dịch vụ được publish. `127.0.0.1` = chỉ truy cập từ máy local. Đặt thành IP LAN (vd: `192.168.1.10`) để cho phép truy cập từ mạng nội bộ. **Không đặt `0.0.0.0` trên máy chủ công khai nếu chưa có firewall.** |
| `POSTGRES_HOST` | `dlh-postgres` | Tên hostname của PostgreSQL **bên trong** Docker network. Thay đổi nếu dùng PostgreSQL ngoài Docker (vd: `db.example.com`). |

## Docker Image Versions

| Biến | Giá trị mặc định | Mô tả |
|------|-----------------|-------|
| `POSTGRES_IMAGE_VERSION` | `17-alpine` | Tag image PostgreSQL. `17-alpine` = nhỏ gọn, bảo mật tốt. |
| `RUSTFS_IMAGE_VERSION` | `latest` | Tag image RustFS. Ghim tag cụ thể cho production (vd: `v1.2.3`). |
| `MINIO_MC_IMAGE_VERSION` | `latest` | Tag MinIO Client dùng bởi `rustfs-init` để tạo buckets. |
| `CLICKHOUSE_IMAGE_VERSION` | `latest` | Tag ClickHouse. Khuyến nghị ghim version cụ thể. |
| `MAGE_IMAGE_VERSION` | `latest` | Tag Mage.ai. |
| `NOCODB_IMAGE_VERSION` | `latest` | Tag NocoDB. |
| `SUPERSET_IMAGE_VERSION` | `latest` | Tag Apache Superset. |
| `GRAFANA_IMAGE_VERSION` | `latest` | Tag Grafana. |

> ⚠️ **Production:** Luôn ghim version cụ thể thay vì `latest` để đảm bảo tính ổn định.

## PostgreSQL – Cơ sở dữ liệu trung tâm

| Biến | Giá trị mặc định | Bắt buộc | Mô tả chi tiết |
|------|-----------------|----------|----------------|
| `POSTGRES_DB` | `datalakehouse` | ✅ | Tên database admin chính. Chứa metadata chung và dữ liệu khởi tạo. |
| `POSTGRES_USER` | `dlh_admin` | ✅ | Superuser PostgreSQL. Có đủ quyền để tạo database, user, schema. |
| `POSTGRES_PASSWORD` | `change-this-admin-password` | ✅ ⚠️ | Mật khẩu superuser. **PHẢI thay đổi trước khi deploy!** |
| `DLH_POSTGRES_PORT` | `25432` | – | Cổng PostgreSQL expose ra host. Dùng cổng lạ để tránh xung đột với PostgreSQL mặc định (5432). |

## Custom Workspace (PostgreSQL)

Tạo database/schema/user riêng biệt cho dữ liệu nghiệp vụ, tách khỏi metadata hệ thống.

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `CUSTOM_DB_NAME` | `dlh_custom` | Tên database workspace riêng. **Để trống** nếu không cần (`CUSTOM_DB_NAME=`). Khi được đặt, bootstrap script sẽ tự tạo. |
| `CUSTOM_DB_USER` | `dlh_custom_user` | User riêng cho workspace này. Không có quyền superuser. |
| `CUSTOM_DB_PASSWORD` | `change-this-custom-password` | ⚠️ Cần thay đổi. |
| `CUSTOM_SCHEMA` | `custom_schema` | Schema riêng trong `CUSTOM_DB_NAME`. ETL pipeline ưu tiên schema này khi được đặt. |

## RustFS – Object Storage

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | ⚠️ S3 Access Key (tương đương username). **Thay đổi cho production.** Dùng chữ cái, số, độ dài 3-20 ký tự. |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | ⚠️ S3 Secret Key (tương đương mật khẩu). **Thay đổi cho production.** Tối thiểu 8 ký tự. |
| `DLH_RUSTFS_API_PORT` | `29100` | Cổng S3 API endpoint (cho boto3, mc client). |
| `DLH_RUSTFS_CONSOLE_PORT` | `29101` | Cổng Web Console của RustFS (giao diện upload file). |
| `RUSTFS_VOLUMES` | `/data` | Đường dẫn lưu trữ dữ liệu **bên trong** container. Thường không cần thay đổi. |
| `RUSTFS_ADDRESS` | `0.0.0.0:9000` | Địa chỉ bind S3 API **bên trong** container. Không thay đổi trừ khi biết mình đang làm gì. |
| `RUSTFS_CONSOLE_ADDRESS` | `0.0.0.0:9001` | Địa chỉ bind Web Console **bên trong** container. |
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | URL S3 endpoint **giữa các containers** trong Docker network. Dùng trong Mage pipeline. |
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Tên bucket lưu dữ liệu thô (raw). Tạo tự động bởi `rustfs-init`. |
| `RUSTFS_SILVER_BUCKET` | `silver` | Tên bucket lưu dữ liệu đã làm sạch. |
| `RUSTFS_GOLD_BUCKET` | `gold` | Tên bucket lưu dữ liệu tổng hợp (aggregated). |
| `RUSTFS_BUCKET` | `nocodb` | Bucket dùng cho Litestream backup của NocoDB. |
| `RUSTFS_CORS_ALLOWED_ORIGINS` | `http://localhost:29100` | CORS origins được phép truy cập S3 API. |
| `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS` | `http://localhost:29101` | CORS origins cho Web Console. |
| `LITESTREAM_S3_ENDPOINT` | `http://dlh-rustfs:9000` | Endpoint cho NocoDB Litestream backup tới RustFS. |

## ClickHouse – OLAP Engine

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | Hostname ClickHouse **trong Docker network**. Dùng bởi Mage và Grafana. |
| `CLICKHOUSE_DB` | `analytics` | Tên database analytics mặc định. Chứa tất cả bảng gold, silver, metrics. |
| `CLICKHOUSE_USER` | `default` | Username ClickHouse. `default` là user built-in. |
| `CLICKHOUSE_PASSWORD` | *(trống)* | Mật khẩu ClickHouse. Để trống cho môi trường local. ⚠️ Đặt mật khẩu cho production. |
| `DLH_CLICKHOUSE_HTTP_PORT` | `28123` | Cổng HTTP API của ClickHouse (dùng cho curl, HTTP client). |
| `DLH_CLICKHOUSE_TCP_PORT` | `29000` | Cổng TCP native protocol (dùng cho `clickhouse-driver` Python). |

## Mage.ai – ETL Orchestration

### Database connection

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `MAGE_DB_NAME` | `dlh_mage` | Database PostgreSQL lưu trữ metadata nội bộ của Mage (pipeline definitions, run history). |
| `MAGE_DB_USER` | `dlh_mage_user` | User PostgreSQL riêng cho Mage. Được tạo tự động bởi bootstrap. |
| `MAGE_DB_PASSWORD` | `change-this-mage-password` | ⚠️ Mật khẩu cần thay đổi. |
| `MAGE_CODE_PATH` | `/home/src` | Đường dẫn thư mục code **bên trong** container (mount từ `./mage`). |
| `USER_CODE_PATH` | `/home/src` | Alias cho `MAGE_CODE_PATH`, một số phiên bản Mage dùng biến này. |

### ETL Source – Nguồn dữ liệu PostgreSQL

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `SOURCE_DB_HOST` | `dlh-postgres` | Host của database nguồn ETL. |
| `SOURCE_DB_PORT` | `5432` | Cổng PostgreSQL nguồn. |
| `SOURCE_DB_NAME` | `datalakehouse` | Tên database nguồn để extract dữ liệu. Khi `CUSTOM_DB_NAME` được đặt, nên dùng giá trị đó. |
| `SOURCE_DB_USER` | `dlh_admin` | User PostgreSQL để đọc dữ liệu nguồn. |
| `SOURCE_DB_PASSWORD` | *(theo POSTGRES_PASSWORD)* | Mật khẩu user nguồn. |
| `SOURCE_SCHEMA` | `public` | Schema PostgreSQL chứa bảng nguồn. |
| `SOURCE_TABLE` | *(trống)* | Tên bảng cụ thể để extract. **Để trống** = tự động tìm từ `SOURCE_TABLE_CANDIDATES`. |
| `SOURCE_TABLE_CANDIDATES` | `Demo,test_projects` | Danh sách tên bảng ứng viên (phân cách bằng dấu phẩy). Pipeline thử từng tên cho đến khi tìm thấy. |

### CSV Upload Pipeline

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `CSV_UPLOAD_BUCKET` | `bronze` | Bucket RustFS để quét tìm file CSV mới. |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Tiền tố (thư mục ảo) ưu tiên quét CSV. Files ở đây được xử lý trước. |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | `true` = chấp nhận CSV ở bất cứ đâu trong bucket (không chỉ trong `CSV_UPLOAD_PREFIX`). |
| `CSV_UPLOAD_SEPARATOR` | `,` | Ký tự phân cách cột trong file CSV. Dùng `;` cho CSV kiểu châu Âu, `\t` cho TSV. |
| `CSV_UPLOAD_ENCODING` | `utf-8` | Encoding của file CSV. Dùng `utf-8-sig` nếu file có BOM (từ Excel). |
| `CSV_UPLOAD_SCAN_LIMIT` | `200` | Số file tối đa quét trong một lần chạy pipeline. Tăng nếu bucket có nhiều file. |

## NocoDB – No-code Database UI

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `DLH_NOCODB_PORT` | `28082` | Cổng Web UI của NocoDB expose ra host. |
| `NOCODB_DB_NAME` | `dlh_nocodb` | Database PostgreSQL lưu metadata của NocoDB. |
| `NOCODB_DB_USER` | `dlh_nocodb_user` | User PostgreSQL riêng cho NocoDB. |
| `NOCODB_DB_PASSWORD` | `change-this-nocodb-password` | ⚠️ Cần thay đổi. |
| `NOCODB_PUBLIC_URL` | `http://127.0.0.1:28082` | URL công khai của NocoDB (dùng cho redirect, SSO callbacks). Thay đổi khi deploy trên server với domain thực. |
| `NOCODB_BACKEND_URL` | `http://127.0.0.1:28082` | URL backend API của NocoDB. |

## Apache Superset – Analytics Dashboard

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `DLH_SUPERSET_PORT` | `28088` | Cổng Superset Web UI. |
| `SUPERSET_SECRET_KEY` | `replace-this-secret` | ⚠️ **BẮT BUỘC thay đổi!** Khóa mã hóa session Flask. Dùng `openssl rand -hex 32` để tạo khóa ngẫu nhiên. |
| `SUPERSET_DB_NAME` | `dlh_superset` | Database PostgreSQL lưu metadata Superset (dashboards, charts, users). |
| `SUPERSET_DB_USER` | `dlh_superset_user` | User PostgreSQL riêng cho Superset. |
| `SUPERSET_DB_PASSWORD` | `change-this-superset-db-password` | ⚠️ Cần thay đổi. |
| `SUPERSET_ADMIN_USER` | `admin` | Tên đăng nhập của admin Superset. |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | ⚠️ **PHẢI thay đổi cho production!** |
| `SUPERSET_ADMIN_EMAIL` | `admin@superset.local` | Email admin Superset. |
| `SUPERSET_CONFIG_PATH` | `/app/pythonpath/superset_config.py` | Đường dẫn file config Superset **bên trong** container. |
| `SUPERSET_LOAD_EXAMPLES` | `no` | `yes` = tải dữ liệu mẫu của Superset (tốn thêm 2-3 phút). |

## Grafana – Monitoring & Alerting

| Biến | Giá trị mặc định | Mô tả chi tiết |
|------|-----------------|----------------|
| `DLH_GRAFANA_PORT` | `23001` | Cổng Grafana Web UI. |
| `GRAFANA_DB_NAME` | `dlh_grafana` | Database PostgreSQL lưu metadata Grafana (dashboards, users, config). |
| `GRAFANA_DB_USER` | `dlh_grafana_user` | User PostgreSQL riêng cho Grafana. |
| `GRAFANA_DB_PASSWORD` | `change-this-grafana-db-password` | ⚠️ Cần thay đổi. |
| `GRAFANA_ADMIN_USER` | `admin` | Tên đăng nhập admin Grafana. |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | ⚠️ **PHẢI thay đổi cho production!** |
| `GF_DATABASE_HOST` | `dlh-postgres:5432` | Host:port PostgreSQL cho Grafana (format đặc biệt của Grafana). |
| `GF_INSTALL_PLUGINS` | `grafana-piechart-panel,grafana-clickhouse-datasource` | Danh sách plugin Grafana cài tự động khi khởi động. |

## Nginx Proxy Manager (Tùy chọn)

| Biến | Giá trị mặc định | Mô tả |
|------|-----------------|-------|
| `DLH_NPM_HTTP_PORT` | `28080` | Cổng HTTP của Nginx Proxy Manager. |
| `DLH_NPM_HTTPS_PORT` | `28443` | Cổng HTTPS (SSL termination). |
| `DLH_NPM_ADMIN_PORT` | `28081` | Cổng Admin UI của Nginx Proxy Manager. |

> 💡 Để kích hoạt Nginx Proxy Manager, bỏ comment phần `nginx-proxy-manager` trong `docker-compose.yaml`.

---

# 📁 Project Structure

```
DataLakehouse/
│
├── 📄 docker-compose.yaml          # Định nghĩa tất cả services và volumes
├── 📄 .env.example                 # Mẫu biến môi trường (copy thành .env)
├── 📄 .gitignore                   # Loại trừ .env và data volumes
├── 📄 io_config.yaml               # Cấu hình I/O ở cấp dự án (legacy)
│
├── 📂 postgres/
│   └── init/
│       ├── 000_create_app_security.sh   # Tạo users, databases, schemas cho tất cả apps
│       ├── 001_lakehouse_metadata.sql   # Schema bảng metadata lakehouse
│       └── 002_sample_data.sql          # Dữ liệu mẫu 100.000 dòng (Demo table)
│
├── 📂 clickhouse/
│   └── init/
│       └── 001_analytics_schema.sql     # DDL tạo tất cả bảng analytics
│
├── 📂 mage/                         # Code ETL và cấu hình Mage.ai
│   ├── io_config.yaml               # Profiles kết nối (default, source_db, custom_db, clickhouse)
│   ├── requirements.txt             # Python packages cần thiết
│   │
│   ├── 📂 data_loaders/             # Bước EXTRACT – đọc dữ liệu nguồn
│   │   ├── extract_postgres.py      # Đọc từ bảng PostgreSQL
│   │   └── extract_csv_from_rustfs.py  # Lấy CSV mới từ RustFS bronze
│   │
│   ├── 📂 transformers/             # Bước TRANSFORM – làm sạch và tổng hợp
│   │   ├── transform_silver.py      # Làm sạch: dedup, trim, validate, cast types
│   │   ├── transform_gold.py        # Tổng hợp: daily/region/category metrics
│   │   └── clean_csv_for_reporting.py  # Làm sạch CSV upload cho báo cáo
│   │
│   ├── 📂 data_exporters/           # Bước LOAD – ghi dữ liệu đích
│   │   ├── bronze_to_rustfs.py      # Ghi raw data vào RustFS bronze/
│   │   ├── silver_to_rustfs.py      # Ghi silver data vào RustFS silver/
│   │   ├── gold_to_rustfs.py        # Ghi gold data vào RustFS gold/
│   │   ├── csv_to_rustfs_silver.py  # Ghi CSV đã làm sạch vào RustFS
│   │   ├── load_to_clickhouse.py    # Đọc từ RustFS và nạp vào ClickHouse (ETL pipeline)
│   │   └── load_csv_reporting_clickhouse.py  # Nạp CSV metrics vào ClickHouse
│   │
│   ├── 📂 pipelines/                # Định nghĩa pipeline (thứ tự các block)
│   │   ├── etl_postgres_to_lakehouse/   # Pipeline ETL PostgreSQL → Lakehouse
│   │   └── etl_csv_upload_to_reporting/ # Pipeline CSV upload → Dashboard
│   │
│   └── 📂 utils/
│       └── rustfs_layer_reader.py   # Helper đọc Parquet từ RustFS layers
│
├── 📂 superset/
│   └── superset_config.py           # Cấu hình Flask/Superset (DB URI, cache, security)
│
├── 📂 grafana/
│   └── provisioning/
│       ├── dashboards/              # JSON files định nghĩa Grafana dashboards
│       └── datasources/             # Cấu hình datasource ClickHouse & PostgreSQL
│
├── 📂 scripts/
│   ├── setup.sh                             # Wizard cài đặt tương tác
│   ├── run_etl_and_dashboard.py             # Chạy ETL + tạo dashboard demo
│   ├── create_superset_demo_dashboard.py    # Tạo Superset demo dashboard
│   ├── demo_to_lakehouse.py                 # Chạy demo ETL thủ công
│   └── verify_lakehouse_architecture.py     # Kiểm tra toàn bộ stack
│
└── 📂 docs/
    ├── DEPLOYMENT_GUIDE.md                  # Hướng dẫn triển khai chi tiết
    ├── VARIABLES_REFERENCE.md               # Tham chiếu biến môi trường đầy đủ
    ├── PIPELINE_GUIDE.md                    # Hướng dẫn ETL pipeline
    ├── LAKEHOUSE_ARCHITECTURE.md            # Kiến trúc lakehouse chi tiết
    ├── ARCHITECTURE_MODERN_STACK.md         # Tổng quan Modern Data Stack
    └── architecture.md                      # Sơ đồ kiến trúc
```

---

# 📊 Usage

## 1. Upload CSV (Người dùng không kỹ thuật)

```
Người dùng → RustFS Console → bronze bucket → csv_upload/
                                                    ↓
                                         Mage quét mỗi 5 phút
                                                    ↓
                                    extract → clean → write silver → load ClickHouse
                                                    ↓
                                         Superset Dashboard cập nhật
```

**Các bước thực hiện:**

1. Mở **http://localhost:29101** (RustFS Console)
2. Đăng nhập bằng `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` từ `.env`
3. Điều hướng đến bucket **`bronze`**
4. Tạo thư mục `csv_upload/` (nếu chưa có)
5. Upload file CSV (định dạng: cột header ở dòng đầu, encoding UTF-8)
6. Chờ pipeline Mage chạy (tối đa 5 phút)
7. Xem kết quả tại **http://localhost:28088**

**Yêu cầu định dạng CSV:**
- Dòng đầu tiên là tên cột (header)
- Encoding: UTF-8 (mặc định) hoặc `UTF-8-BOM` (từ Excel)
- Separator: `,` (mặc định) – cấu hình qua `CSV_UPLOAD_SEPARATOR`
- Không giới hạn số cột, không giới hạn số dòng

## 2. Chạy ETL PostgreSQL → Lakehouse

### Tự động (theo lịch – mỗi 6 giờ):
1. Mage extract bảng từ PostgreSQL (`SOURCE_TABLE` hoặc tự động từ `SOURCE_TABLE_CANDIDATES`)
2. Ghi raw Parquet vào RustFS `bronze/`
3. Transformer làm sạch dữ liệu → ghi vào `silver/`
4. Transformer tổng hợp → ghi vào `gold/`
5. Exporter đọc từ RustFS và nạp vào ClickHouse
6. Grafana dashboard cập nhật

### Kích hoạt thủ công:

```bash
# Qua Mage CLI (bên trong container)
docker compose exec mage mage run etl_postgres_to_lakehouse

# Qua Mage Web UI
# Mở http://localhost:26789 → Pipelines → etl_postgres_to_lakehouse → Run

# Qua Mage API
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_run": {"pipeline_uuid": "etl_postgres_to_lakehouse"}}'
```

## 3. Theo dõi & Giám sát

```bash
# Xem log tất cả services
docker compose logs -f

# Xem log service cụ thể
docker compose logs -f mage
docker compose logs -f clickhouse

# Kiểm tra trạng thái services
docker compose ps

# Kiểm tra dữ liệu ClickHouse
docker compose exec clickhouse clickhouse-client \
  --query "SELECT pipeline_name, status, rows_silver, rows_gold_daily, started_at FROM analytics.pipeline_runs ORDER BY started_at DESC LIMIT 10"

# Kiểm tra số lượng dữ liệu
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.gold_demo_daily"
```

## 4. Quản lý dữ liệu qua NocoDB

1. Mở **http://localhost:28082**
2. Tạo tài khoản admin lần đầu
3. Kết nối tới PostgreSQL qua: `postgresql://dlh_admin:<password>@dlh-postgres:5432/datalakehouse`
4. Xem/chỉnh sửa dữ liệu không cần viết SQL

---

# 📈 Dashboards

## Superset – Analytics

**URL:** http://localhost:28088

**Dashboard: Data Lakehouse CSV Demo**

| Biểu đồ | Nguồn dữ liệu | Mô tả |
|---------|--------------|-------|
| CSV Data Overview | `csv_quality_metrics` | 10 file CSV được xử lý gần nhất |
| CSV Quality Metrics | `csv_quality_metrics` | Tỷ lệ raw/cleaned/dropped/duplicated per file |
| CSV Upload Events | `csv_upload_events` | Log trạng thái, lỗi, thời gian xử lý |
| CSV Row Comparison | `csv_quality_metrics` | Timeseries: cleaned vs dropped rows theo thời gian |

**Tạo lại dashboard:**
```bash
docker compose exec -T \
  -e SUPERSET_URL=http://127.0.0.1:8088 \
  superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

## Grafana – Monitoring

**URL:** http://localhost:23001

**Dashboard: Lakehouse Command Center**

| Panel | Mô tả |
|-------|-------|
| Pipeline Status | Trạng thái các lần chạy ETL gần nhất |
| Rows Processed | Số dòng extracted/silver/gold theo thời gian |
| CSV Ingestion Rate | Tốc độ nhập CSV (dòng/phút) |
| Data Quality Score | Tỷ lệ cleaned vs dropped |
| Error Alerts | Cảnh báo khi pipeline thất bại |

---

# 🔌 API

## Mage.ai API

```bash
# Liệt kê tất cả pipelines
curl http://localhost:26789/api/pipelines

# Kích hoạt pipeline
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_run": {"pipeline_uuid": "etl_postgres_to_lakehouse"}}'

# Lấy trạng thái run
curl http://localhost:26789/api/pipeline_runs/<run_id>
```

## ClickHouse HTTP API

```bash
# Query đơn giản
curl "http://localhost:28123/?query=SELECT+count()+FROM+analytics.pipeline_runs"

# Query phức tạp (multiline)
curl http://localhost:28123 \
  -u "default:" \
  -d "SELECT pipeline_name, status, rows_silver FROM analytics.pipeline_runs ORDER BY started_at DESC LIMIT 5 FORMAT Pretty"

# Tổng hợp daily revenue
curl http://localhost:28123 \
  -d "SELECT order_date, total_revenue, order_count FROM analytics.gold_demo_daily ORDER BY order_date DESC LIMIT 10 FORMAT JSONEachRow"
```

## Superset REST API

```bash
# Đăng nhập lấy token
TOKEN=$(curl -s -X POST http://localhost:28088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "db"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Liệt kê dashboards
curl http://localhost:28088/api/v1/dashboard \
  -H "Authorization: Bearer $TOKEN"

# Liệt kê datasources
curl http://localhost:28088/api/v1/database \
  -H "Authorization: Bearer $TOKEN"
```

---

# 🐛 Troubleshooting

## Service không khởi động

```bash
# Xem log của service cụ thể
docker compose logs -f mage
docker compose logs -f clickhouse
docker compose logs -f dlh-postgres

# Kiểm tra xem service có healthy không
docker compose ps

# Khởi động lại service đơn lẻ
docker compose restart mage
```

## Lỗi: "Cannot connect to Docker daemon"

```bash
sudo systemctl start docker
# hoặc trên macOS: khởi động Docker Desktop
```

## Lỗi: "Port already in use"

```bash
# Tìm tiến trình đang dùng cổng (vd: 28123)
sudo lsof -i :28123
# Hoặc
sudo ss -tlnp | grep 28123

# Đổi cổng trong .env
DLH_CLICKHOUSE_HTTP_PORT=38123
```

## ClickHouse không phản hồi

```bash
# Kiểm tra health
docker compose exec clickhouse wget -qO- http://127.0.0.1:8123/ping

# Vào shell ClickHouse
docker compose exec clickhouse clickhouse-client

# Kiểm tra databases
docker compose exec clickhouse clickhouse-client --query "SHOW DATABASES"

# Kiểm tra tables trong analytics
docker compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
```

## Mage pipeline thất bại

```bash
# Xem log lỗi
docker compose logs mage | grep -i error | tail -20

# Kiểm tra biến môi trường trong container
docker compose exec mage env | grep -E "SOURCE|RUSTFS|CLICKHOUSE"

# Chạy lại pipeline thủ công với output chi tiết
docker compose exec mage mage run etl_postgres_to_lakehouse
```

## RustFS không thể truy cập

```bash
# Kiểm tra health
docker compose exec rustfs sh -c "curl -s http://127.0.0.1:9000/health"

# Xem log RustFS
docker compose logs rustfs | tail -30

# Tạo lại buckets
docker compose run --rm rustfs-init
```

## Superset dashboard trống / không có dữ liệu

```bash
# Kiểm tra dữ liệu có trong ClickHouse không
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.csv_quality_metrics"

# Nếu 0, chạy pipeline ETL trước:
docker compose exec mage mage run etl_postgres_to_lakehouse

# Tạo lại Superset dashboard
docker compose exec -T -e SUPERSET_URL=http://127.0.0.1:8088 superset \
  /app/.venv/bin/python - < scripts/create_superset_demo_dashboard.py
```

## Reset toàn bộ stack

```bash
# ⚠️ Cảnh báo: Xóa TẤT CẢ dữ liệu trong volumes!
docker compose down -v
docker network rm web_network

# Khởi động lại từ đầu
docker network create web_network
docker compose up -d
```

## Kiểm tra toàn bộ hệ thống

```bash
# Script kiểm tra tự động
python3 scripts/verify_lakehouse_architecture.py
```

---

# 📍 Default Ports

| Dịch vụ | Cổng host | Cổng container | Ghi chú |
|---------|-----------|---------------|---------|
| PostgreSQL | `25432` | `5432` | Dùng cổng lạ tránh xung đột |
| RustFS S3 API | `29100` | `9000` | boto3, mc client |
| RustFS Console | `29101` | `9001` | Web upload UI |
| ClickHouse HTTP | `28123` | `8123` | REST/curl queries |
| ClickHouse TCP | `29000` | `9000` | Python clickhouse-driver |
| Mage.ai | `26789` | `6789` | ETL UI & API |
| NocoDB | `28082` | `8080` | No-code DB UI |
| Superset | `28088` | `8088` | Analytics dashboards |
| Grafana | `23001` | `3000` | Monitoring UI |

---

# 📝 Ghi chú quan trọng

| Chủ đề | Ghi chú |
|--------|---------|
| **Lần chạy đầu tiên** | Mất 5–15 phút để tải image và khởi tạo dữ liệu 100k dòng. Kiểm tra `docker compose ps` và đợi tất cả `healthy`. |
| **Tính bền vững dữ liệu** | Dữ liệu lưu trong Docker named volumes. `docker compose down` không xóa data. `docker compose down -v` mới xóa. |
| **Bảo mật production** | Thay đổi tất cả mật khẩu mặc định. Đặt `DLH_BIND_IP` phù hợp. Thêm reverse proxy với SSL/TLS. |
| **Backup** | Backup thường xuyên volumes `postgres_data`, `clickhouse_data`, `rustfs_data`. |
| **Mở rộng** | Cho production: tách Mage ra server riêng, cấu hình ClickHouse replication, dùng managed PostgreSQL. |
| **Timezone** | Thay `TZ=Asia/Ho_Chi_Minh` bằng múi giờ phù hợp. Ảnh hưởng đến lịch biểu pipeline và timestamp log. |

---

**Tác giả:** HoangThinh2024  
**Giấy phép:** MIT  
**Tài liệu:** [docs/](docs/)

---

---

# 🏗️ DataLakehouse – Ngăn xếp Dữ liệu Hiện đại

> **Modern Data Lakehouse Stack** – Tích hợp đầy đủ từ lưu trữ dữ liệu thô đến dashboard phân tích real-time, chạy hoàn toàn bằng Docker Compose.

---

## 🚀 Bắt đầu nhanh

### Yêu cầu hệ thống

| Yêu cầu | Tối thiểu | Khuyến nghị |
|---------|-----------|-------------|
| Docker Engine | 24+ | Mới nhất |
| Docker Compose | v2 (plugin) | v2.20+ |
| RAM | 4 GB | 8 GB |
| Ổ đĩa trống | 10 GB | 20 GB |
| CPU | 2 nhân | 4 nhân |

### Cài đặt nhanh (1 lệnh)

```bash
# Cách 1: Script wizard (khuyến nghị cho lần đầu)
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
bash scripts/setup.sh
```

```bash
# Cách 2: Thủ công
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
cp .env.example .env
# Chỉnh sửa .env theo nhu cầu
docker network create web_network
docker compose up -d
```

### Kiểm tra trạng thái

```bash
# Đợi tất cả services "healthy" (có thể mất 5-10 phút)
docker compose ps

# Xem log
docker compose logs -f --tail=50
```

### Truy cập dịch vụ

| Dịch vụ | Địa chỉ | Tài khoản mặc định |
|---------|---------|-------------------|
| 📦 RustFS Console | http://localhost:29101 | rustfsadmin / rustfsadmin |
| 📊 Superset | http://localhost:28088 | admin / admin |
| 📈 Grafana | http://localhost:23001 | admin / admin |
| ⚙️ Mage.ai | http://localhost:26789 | – |
| 🗃 NocoDB | http://localhost:28082 | Đăng ký lần đầu |

---

## 🏛️ Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────────┐
│                      NGUỒN DỮ LIỆU                              │
│       PostgreSQL · Upload CSV · APIs · Files · Streaming         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Extract
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                LAYER 3 – XỬ LÝ (Mage.ai :26789)                │
│                                                                 │
│  ► etl_postgres_to_lakehouse   (tự động mỗi 6 giờ)             │
│    [extract] → [silver transform] → [gold aggregate]            │
│    → [write bronze/silver/gold to RustFS] → [load ClickHouse]  │
│                                                                 │
│  ► etl_csv_upload_to_reporting  (tự động mỗi 5 phút)           │
│    [scan bronze bucket] → [clean CSV] → [write silver]          │
│    → [load metrics to ClickHouse]                               │
└──────────┬──────────────────────────────────────────────────────┘
           │                                │
     Ghi Parquet                     Ghi metadata
           ▼                                ▼
┌─────────────────────┐     ┌──────────────────────────────────┐
│  RustFS :29100      │     │  PostgreSQL :25432               │
│  (S3-compatible)    │     │                                  │
│                     │     │  dlh_mage      ← Mage metadata  │
│  bronze/ ← raw      │     │  dlh_superset  ← Superset meta  │
│  silver/ ← cleaned  │     │  dlh_grafana   ← Grafana meta   │
│  gold/   ← aggregated│     │  dlh_nocodb    ← NocoDB meta   │
└──────────┬──────────┘     │  dlh_custom    ← Workspace DB   │
           │                └──────────────────────────────────┘
     Đọc Parquet
           ▼
┌─────────────────────────────────────────────────────────────────┐
│             LAYER 4 – SERVING (ClickHouse :28123)               │
│                                                                 │
│  analytics.silver_demo           analytics.gold_demo_daily      │
│  analytics.gold_demo_by_region   analytics.gold_demo_by_category│
│  analytics.csv_clean_rows        analytics.csv_quality_metrics  │
│  analytics.csv_upload_events     analytics.pipeline_runs        │
└──────────────────────┬──────────────────────────────────────────┘
                       │ SQL Queries
          ┌────────────┴─────────────┐
          ▼                          ▼
┌──────────────────┐      ┌───────────────────────────┐
│ Superset :28088  │      │ Grafana :23001             │
│ Analytics Charts │      │ Monitoring & Alerts        │
│ & Dashboards     │      │ ETL Pipeline Status        │
└──────────────────┘      └───────────────────────────┘
```

---

## 🔧 Thành phần chi tiết

### PostgreSQL – Cơ sở dữ liệu Metadata

**Vai trò:** Lưu trữ metadata và cấu hình của tất cả services trong stack.

**Databases được tạo tự động:**

| Database | Service sử dụng | Mục đích |
|----------|----------------|---------|
| `datalakehouse` | Admin | Database admin, chứa dữ liệu mẫu |
| `dlh_mage` | Mage.ai | Pipeline definitions, run history, secrets |
| `dlh_superset` | Superset | Dashboards, charts, users, datasources |
| `dlh_grafana` | Grafana | Dashboards, alerts, users |
| `dlh_nocodb` | NocoDB | Tables, views, APIs, automation |
| `dlh_custom` | Workspace | Database nghiệp vụ người dùng |

### RustFS – Object Storage (S3-compatible)

**Vai trò:** Lưu trữ tất cả dữ liệu dạng file theo kiến trúc Medallion.

**Cấu trúc bucket:**

```
bronze/
  ├── raw_<pipeline_run_id>_<timestamp>.parquet   ← dữ liệu thô từ PostgreSQL
  └── csv_upload/                                 ← file CSV của người dùng upload
        └── <filename>.csv

silver/
  └── silver_<pipeline_run_id>_<timestamp>.parquet  ← dữ liệu đã làm sạch

gold/
  ├── gold_daily_<pipeline_run_id>_<timestamp>.parquet
  ├── gold_region_<pipeline_run_id>_<timestamp>.parquet
  └── gold_category_<pipeline_run_id>_<timestamp>.parquet
```

### ClickHouse – OLAP Analytics Engine

**Vai trò:** Query engine nhanh cho phân tích dữ liệu lớn.

**Schema `analytics`:**

| Bảng | Mô tả | Engine |
|------|-------|--------|
| `silver_demo` | Dữ liệu PostgreSQL đã làm sạch | MergeTree |
| `gold_demo_daily` | Tổng hợp theo ngày | MergeTree |
| `gold_demo_by_region` | Tổng hợp theo vùng | MergeTree |
| `gold_demo_by_category` | Tổng hợp theo danh mục | MergeTree |
| `csv_clean_rows` | Dòng CSV đã xử lý (JSON) | MergeTree |
| `csv_quality_metrics` | Chỉ số chất lượng CSV | MergeTree |
| `csv_upload_events` | Log sự kiện upload | MergeTree |
| `pipeline_runs` | Lịch sử chạy ETL | MergeTree |

### Mage.ai – ETL Orchestration

**Vai trò:** Điều phối và lên lịch các ETL pipelines.

**Hai pipelines chính:**

**1. `etl_postgres_to_lakehouse`** – Chạy mỗi 6 giờ

```
extract_postgres
    ↓
transform_silver      ← Làm sạch: dedup, validate, cast types
    ↓
transform_gold        ← Tổng hợp: daily/region/category
    ↓
bronze_to_rustfs      ← Ghi raw Parquet vào bronze/
silver_to_rustfs      ← Ghi cleaned Parquet vào silver/
gold_to_rustfs        ← Ghi aggregated Parquet vào gold/
    ↓
load_to_clickhouse    ← Đọc từ RustFS → nạp vào ClickHouse
```

**2. `etl_csv_upload_to_reporting`** – Chạy mỗi 5 phút

```
extract_csv_from_rustfs    ← Quét bronze bucket, lấy CSV mới chưa xử lý
    ↓
clean_csv_for_reporting    ← Làm sạch CSV (trim, dedup, validate)
    ↓
csv_to_rustfs_silver       ← Ghi cleaned CSV vào silver/
    ↓
load_csv_reporting_clickhouse ← Nạp metrics và events vào ClickHouse
```

---

## 🔐 Biến môi trường chi tiết

> 💡 File `.env.example` chứa tất cả biến với giá trị mặc định.
> Xem thêm tại [docs/VARIABLES_REFERENCE.md](docs/VARIABLES_REFERENCE.md)

### ⚠️ Các biến BẮT BUỘC thay đổi trước production

```bash
# Tạo secret key ngẫu nhiên cho Superset
openssl rand -hex 32

# Trong .env:
POSTGRES_PASSWORD=<mật-khẩu-mạnh>
RUSTFS_ACCESS_KEY=<access-key-mới>
RUSTFS_SECRET_KEY=<secret-key-mới>
SUPERSET_SECRET_KEY=<output-của-openssl>
SUPERSET_ADMIN_PASSWORD=<mật-khẩu-mạnh>
GRAFANA_ADMIN_PASSWORD=<mật-khẩu-mạnh>
MAGE_DB_PASSWORD=<mật-khẩu-mạnh>
CLICKHOUSE_PASSWORD=<mật-khẩu-mạnh>
```

### Cài đặt mạng

```bash
# Chỉ cho phép truy cập local (mặc định, an toàn nhất)
DLH_BIND_IP=127.0.0.1

# Cho phép truy cập từ LAN (vd: máy trong cùng mạng)
DLH_BIND_IP=192.168.1.100

# Cho phép từ mọi nơi (chỉ dùng khi có firewall/reverse proxy bảo vệ)
DLH_BIND_IP=0.0.0.0
```

---

## 📁 Cấu trúc dự án

```
DataLakehouse/
├── docker-compose.yaml          ← Cấu hình Docker services
├── .env.example                 ← Mẫu biến môi trường
├── postgres/init/               ← Script khởi tạo PostgreSQL
├── clickhouse/init/             ← Script khởi tạo ClickHouse
├── mage/                        ← Code ETL pipelines
├── superset/                    ← Config Superset
├── grafana/provisioning/        ← Dashboard & datasource Grafana
├── scripts/                     ← Scripts tiện ích
└── docs/                        ← Tài liệu chi tiết
```

---

## 📊 Cách sử dụng

### Upload CSV

1. Mở http://localhost:29101 (RustFS)
2. Đăng nhập bằng `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`
3. Vào bucket `bronze` → thư mục `csv_upload/`
4. Upload file CSV
5. Đợi tối đa 5 phút → xem kết quả tại http://localhost:28088

### Chạy ETL thủ công

```bash
docker compose exec mage mage run etl_postgres_to_lakehouse
docker compose exec mage mage run etl_csv_upload_to_reporting
```

### Kiểm tra dữ liệu

```bash
# Số dòng đã xử lý
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.silver_demo"

# Lịch sử pipeline runs
docker compose exec clickhouse clickhouse-client \
  --query "SELECT pipeline_name, status, rows_silver, started_at FROM analytics.pipeline_runs ORDER BY started_at DESC LIMIT 5"
```

---

## 📈 Bảng điều khiển

### Superset (http://localhost:28088)

| Dashboard | URL |
|-----------|-----|
| CSV Demo | `/superset/dashboard/data-lakehouse-csv-demo-100k/` |

### Grafana (http://localhost:23001)

- **Lakehouse Command Center** – Giám sát ETL pipelines
- **Data Quality** – Chỉ số chất lượng dữ liệu CSV

---

## 🔌 API

```bash
# Mage – kích hoạt pipeline
curl -X POST http://localhost:26789/api/pipeline_runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_run": {"pipeline_uuid": "etl_postgres_to_lakehouse"}}'

# ClickHouse – query trực tiếp
curl "http://localhost:28123/?query=SELECT+count()+FROM+analytics.pipeline_runs"

# Superset – lấy danh sách dashboards (cần đăng nhập trước)
curl http://localhost:28088/api/v1/dashboard \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 🐛 Khắc phục sự cố

```bash
# Service không khởi động
docker compose logs -f <service_name>

# Reset toàn bộ (⚠️ xóa dữ liệu)
docker compose down -v
docker network rm web_network
docker network create web_network
docker compose up -d

# Kiểm tra hệ thống
python3 scripts/verify_lakehouse_architecture.py
```

> 📖 Xem [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) để biết thêm về khắc phục sự cố chi tiết.

---

## 📍 Cổng mặc định

| Dịch vụ | Cổng |
|---------|------|
| PostgreSQL | `25432` |
| RustFS API | `29100` |
| RustFS Console | `29101` |
| ClickHouse HTTP | `28123` |
| ClickHouse TCP | `29000` |
| Mage.ai | `26789` |
| NocoDB | `28082` |
| Superset | `28088` |
| Grafana | `23001` |

---

**Tác giả:** HoangThinh2024 | **Giấy phép:** MIT | **Tài liệu:** [docs/](docs/)
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
**🧪 To validate the stack from the host machine, run `./.venv/bin/python scripts/verify_lakehouse_architecture.py`**

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

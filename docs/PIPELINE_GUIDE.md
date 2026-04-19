# ⚙️ Hướng dẫn ETL Pipeline – DataLakehouse

Tài liệu này mô tả chi tiết hai ETL pipelines trong DataLakehouse, bao gồm từng block, biến sử dụng, và cách tùy chỉnh.

---

## Mục lục

1. [Tổng quan kiến trúc Pipeline](#1-tổng-quan-kiến-trúc-pipeline)
2. [Pipeline 1: etl_postgres_to_lakehouse](#2-pipeline-1-etl_postgres_to_lakehouse)
3. [Pipeline 2: etl_csv_upload_to_reporting](#3-pipeline-2-etl_csv_upload_to_reporting)
4. [Cấu hình I/O (io_config.yaml)](#4-cấu-hình-io-io_configyaml)
5. [Thêm bảng nguồn mới](#5-thêm-bảng-nguồn-mới)
6. [Tùy chỉnh pipeline](#6-tùy-chỉnh-pipeline)
7. [Xử lý lỗi và logging](#7-xử-lý-lỗi-và-logging)
8. [Schema ClickHouse](#8-schema-clickhouse)

---

## 1. Tổng quan kiến trúc Pipeline

### Triết lý thiết kế

DataLakehouse tuân theo **Lakehouse Architecture** nghiêm ngặt:

1. **Immutability:** Dữ liệu trong RustFS không bao giờ bị xóa hoặc overwrite
2. **RustFS là Source of Truth:** ClickHouse chỉ là serving layer, đọc từ RustFS
3. **Traceability:** Mỗi lần chạy pipeline có `run_id` UUID duy nhất
4. **Recovery:** Có thể rebuild hoàn toàn ClickHouse từ RustFS bất kỳ lúc nào

### Luồng dữ liệu tổng quát

```
Source (PostgreSQL / CSV)
    │
    ▼ EXTRACT
[Data Loader]
    │ DataFrame + metadata columns
    ▼ TRANSFORM
[Transformer 1: Silver]  ← Làm sạch: dedup, validate, cast
    │ Silver DataFrame
    ▼ TRANSFORM  
[Transformer 2: Gold]    ← Tổng hợp: daily/region/category
    │ Dict{silver, gold_daily, gold_region, gold_category}
    ▼ EXPORT (song song)
[bronze_to_rustfs]       ← Parquet vào bronze/
[silver_to_rustfs]       ← Parquet vào silver/
[gold_to_rustfs]         ← Parquet vào gold/
    │ (hoàn thành)
    ▼ EXPORT
[load_to_clickhouse]     ← Đọc từ RustFS → INSERT vào ClickHouse
```

---

## 2. Pipeline 1: etl_postgres_to_lakehouse

**File:** `mage/pipelines/etl_postgres_to_lakehouse/`  
**Lịch chạy:** Mỗi 6 giờ (cron: `0 */6 * * *`)  
**Nguồn:** PostgreSQL  
**Đích:** RustFS (Bronze/Silver/Gold) + ClickHouse  

---

### Block 1: `extract_postgres.py` (Data Loader)

**File:** `mage/data_loaders/extract_postgres.py`

**Mô tả:** Kết nối PostgreSQL, tìm bảng nguồn, đọc toàn bộ dữ liệu vào DataFrame.

**Biến môi trường sử dụng:**

| Biến | Mặc định container | Mô tả |
|------|-------------------|-------|
| `SOURCE_DB_HOST` | `dlh-postgres` | Host PostgreSQL nguồn |
| `SOURCE_DB_PORT` | `5432` | Cổng PostgreSQL nguồn |
| `SOURCE_DB_NAME` | `datalakehouse` | Database chứa bảng nguồn |
| `SOURCE_DB_USER` | `dlh_admin` | User đọc dữ liệu |
| `SOURCE_DB_PASSWORD` | *(theo .env)* | Mật khẩu user |
| `SOURCE_SCHEMA` | `public` | Schema PostgreSQL |
| `SOURCE_TABLE` | *(trống)* | Tên bảng cụ thể (nếu đặt) |
| `SOURCE_TABLE_CANDIDATES` | `Demo,test_projects` | Danh sách bảng ứng viên |
| `SOURCE_DB_CONNECT_TIMEOUT` | `15` | Timeout kết nối (giây) |

**Logic chọn bảng:**

```python
# Priority 1: SOURCE_TABLE được đặt cụ thể
if SOURCE_TABLE:
    → Tìm bảng này trong information_schema.tables
    → Nếu không tìm thấy: raise ValueError với danh sách bảng có sẵn

# Priority 2: Tự động từ SOURCE_TABLE_CANDIDATES
else:
    → Thử từng tên trong SOURCE_TABLE_CANDIDATES (case-insensitive)
    → Lấy bảng đầu tiên tìm thấy
    → Nếu không tìm thấy bảng nào: raise ValueError
```

**Metadata columns thêm vào DataFrame:**

| Column | Kiểu | Mô tả |
|--------|------|-------|
| `_pipeline_run_id` | `str (UUID)` | ID duy nhất của lần chạy pipeline này |
| `_source_table` | `str` | Tên bảng đã được extract |
| `_extracted_at` | `str (ISO 8601 UTC)` | Thời điểm extract |

**Output:** `pd.DataFrame` với tất cả cột từ bảng nguồn + 3 metadata columns.

---

### Block 2: `transform_silver.py` (Transformer)

**File:** `mage/transformers/transform_silver.py`

**Mô tả:** Làm sạch và validate dữ liệu raw từ PostgreSQL. Input là DataFrame thô, output là DataFrame đã validate.

**Không có biến môi trường** – logic hardcoded theo schema của bảng Demo.

**Các bước xử lý:**

| Bước | Xử lý | Cột áp dụng |
|------|-------|-------------|
| 1 | Xóa dòng duplicate | Tất cả cột |
| 2 | Trim whitespace | `name`, `notes` |
| 3 | Title-case | `category`, `region` |
| 4 | Lowercase | `status` |
| 5 | Validate email | `customer_email` |
| 6 | Validate số không âm | `value`, `quantity` |
| 7 | Cast kiểu | `id` → Int64, `quantity` → Int64, `value` → Float64 |
| 8 | Parse date | `order_date` → `date`, `created_at` → `datetime[UTC]` |
| 9 | Thêm metadata | `_silver_processed_at` |

**Metadata column thêm:**

| Column | Kiểu | Mô tả |
|--------|------|-------|
| `_silver_processed_at` | `str (ISO 8601 UTC)` | Thời điểm transform silver |

**Schema cột bảng Demo được xử lý:**

```
id             Int64       (nullable)
name           str         (trimmed, nullable)
category       str         (title-case, nullable)
value          Float64     (>= 0, nullable)
quantity       Int64       (>= 0, nullable)
order_date     date        (nullable)
region         str         (title-case, nullable)
status         str         (lowercase, nullable)
customer_email str         (validated, nullable)
notes          str         (trimmed, nullable)
created_at     datetime64  (UTC, nullable)
```

**Output:** `pd.DataFrame` đã làm sạch.

---

### Block 3: `transform_gold.py` (Transformer)

**File:** `mage/transformers/transform_gold.py`

**Mô tả:** Tổng hợp Silver data thành 3 Gold tables theo các chiều phân tích.

**Input:** DataFrame từ `transform_silver`

**Output:** `dict` với 4 keys:

```python
{
    'silver': pd.DataFrame,          # Silver data (truyền qua cho exporters)
    'gold_daily': pd.DataFrame,      # Tổng hợp theo ngày
    'gold_region': pd.DataFrame,     # Tổng hợp theo vùng
    'gold_category': pd.DataFrame,   # Tổng hợp theo danh mục
}
```

**Schema các Gold DataFrames:**

**`gold_daily` – Tổng hợp theo ngày:**
```
order_date          date
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
unique_customers    int64
unique_regions      int64
unique_categories   int64
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_region` – Tổng hợp theo vùng địa lý:**
```
region              str
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
report_date         date
_pipeline_run_id    str
_gold_processed_at  str
```

**`gold_category` – Tổng hợp theo danh mục:**
```
category            str
order_count         int64
total_revenue       float64
avg_order_value     float64
total_quantity      int64
report_date         date
_pipeline_run_id    str
_gold_processed_at  str
```

**Logic fallback cho bảng không có `order_date`:**

```python
# Nếu bảng nguồn không có order_date:
# 1. Thử dùng created_at (extract date phần)
# 2. Nếu cũng không có: dùng ngày hiện tại
```

---

### Block 4: `bronze_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/bronze_to_rustfs.py`

**Mô tả:** Ghi DataFrame thô (từ extract_postgres) vào RustFS bucket bronze dưới dạng Parquet.

**Biến môi trường:**

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | S3 endpoint |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | S3 credentials |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | S3 credentials |
| `RUSTFS_BRONZE_BUCKET` | `bronze` | Tên bucket |
| `RUSTFS_REGION` | `us-east-1` | AWS region (dummy cho RustFS) |

**File naming convention:**
```
bronze/raw_<run_id>_<YYYYMMDD_HHMMSS>.parquet
```

---

### Block 5: `silver_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/silver_to_rustfs.py`

**Mô tả:** Ghi Silver DataFrame vào RustFS bucket silver.

**Biến môi trường:** Tương tự `bronze_to_rustfs.py` nhưng dùng `RUSTFS_SILVER_BUCKET`.

**File naming convention:**
```
silver/silver_<run_id>_<YYYYMMDD_HHMMSS>.parquet
```

---

### Block 6: `gold_to_rustfs.py` (Data Exporter)

**File:** `mage/data_exporters/gold_to_rustfs.py`

**Mô tả:** Ghi 3 Gold DataFrames vào RustFS bucket gold (3 file riêng biệt).

**File naming convention:**
```
gold/gold_daily_<run_id>_<timestamp>.parquet
gold/gold_region_<run_id>_<timestamp>.parquet
gold/gold_category_<run_id>_<timestamp>.parquet
```

---

### Block 7: `load_to_clickhouse.py` (Data Exporter)

**File:** `mage/data_exporters/load_to_clickhouse.py`

**Mô tả:** Đọc dữ liệu từ RustFS (silver + gold) và INSERT vào ClickHouse. **KHÔNG dùng in-memory data từ pipeline** – đây là điểm khác biệt quan trọng của kiến trúc lakehouse.

**Biến môi trường:**

| Biến | Mặc định container | Mô tả |
|------|-------------------|-------|
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | ClickHouse hostname |
| `CLICKHOUSE_TCP_PORT` | `9000` | ClickHouse TCP port (bên trong network) |
| `CLICKHOUSE_DB` | `analytics` | Target database |
| `CLICKHOUSE_USER` | `default` | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | *(trống)* | ClickHouse password |

**Quy trình:**

```
1. Kết nối ClickHouse
2. Tạo tables nếu chưa tồn tại (idempotent DDL)
3. Đọc silver Parquet mới nhất từ RustFS
4. INSERT vào analytics.silver_demo
5. Đọc 3 gold Parquet mới nhất từ RustFS
6. INSERT vào analytics.gold_demo_daily/by_region/by_category
7. INSERT vào analytics.pipeline_runs (run metadata)
```

**Lưu ý xử lý kiểu dữ liệu:**
- Datetime columns → Python `datetime` objects (ClickHouse yêu cầu)
- Date columns → Python `date` objects
- Object columns → `str`, với `None/nan/NaT` → `None`
- Numpy scalars → Python native types (`.item()`)

**Output:** `{}` (empty dict) – không truyền dữ liệu downstream theo design.

---

## 3. Pipeline 2: etl_csv_upload_to_reporting

**File:** `mage/pipelines/etl_csv_upload_to_reporting/`  
**Lịch chạy:** Mỗi 5 phút (cron: `*/5 * * * *`)  
**Nguồn:** File CSV trên RustFS bucket bronze  
**Đích:** RustFS silver + ClickHouse (metrics, events, clean rows)  

---

### Block 1: `extract_csv_from_rustfs.py` (Data Loader)

**File:** `mage/data_loaders/extract_csv_from_rustfs.py`

**Mô tả:** Quét bucket bronze tìm file CSV chưa được xử lý (không có record trong `csv_upload_events` với `status='success'`).

**Biến môi trường:**

| Biến | Mặc định | Mô tả |
|------|---------|-------|
| `RUSTFS_ENDPOINT_URL` | `http://dlh-rustfs:9000` | S3 endpoint |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | Credentials |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | Credentials |
| `RUSTFS_REGION` | `us-east-1` | Region |
| `CSV_UPLOAD_BUCKET` | `bronze` | Bucket để quét |
| `CSV_UPLOAD_PREFIX` | `csv_upload/` | Prefix ưu tiên |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | `true` | Quét toàn bucket |
| `CSV_UPLOAD_SEPARATOR` | `,` | CSV delimiter |
| `CSV_UPLOAD_ENCODING` | `utf-8` | File encoding |
| `CSV_UPLOAD_SCAN_LIMIT` | `200` | Max files to scan |
| `CLICKHOUSE_HOST` | `dlh-clickhouse` | Dùng để check đã xử lý chưa |

**Logic "đã xử lý":** Query ClickHouse `csv_upload_events` – nếu có record với `source_key + etag + status='success'` thì file đó đã được xử lý, bỏ qua.

**Logic ưu tiên file:**
1. Files trong `CSV_UPLOAD_PREFIX` (ưu tiên cao)
2. Files ngoài prefix (nếu `CSV_UPLOAD_ALLOW_ANYWHERE=true`)
3. Sắp xếp theo `LastModified` (file cũ nhất trước)
4. Chỉ lấy **1 file** mỗi lần chạy

**Output khi có file mới:**
```python
{
    'skip': False,
    'dataframe': pd.DataFrame,           # Dữ liệu CSV đã đọc
    'bucket': 'bronze',
    'source_key': 'csv_upload/data.csv', # Đường dẫn trong bucket
    'source_etag': 'abc123...',          # ETag của file
    'source_size': 12345,                # Kích thước bytes
    'source_last_modified': '2024-01-01T00:00:00Z',
    'pipeline_run_id': 'uuid-...',
    'raw_rows': 1000,
}
```

**Output khi không có file mới:**
```python
{'skip': True, 'message': 'no new csv'}
```

**Metadata columns thêm vào DataFrame:**

| Column | Mô tả |
|--------|-------|
| `_pipeline_run_id` | UUID của lần chạy |
| `_source_table` | Luôn là `'csv_upload'` |
| `_source_file_key` | Đường dẫn S3 (`csv_upload/file.csv`) |
| `_source_file_etag` | ETag file để dedup |
| `_extracted_at` | Timestamp UTC |

---

### Block 2: `clean_csv_for_reporting.py` (Transformer)

**File:** `mage/transformers/clean_csv_for_reporting.py`

**Mô tả:** Làm sạch dữ liệu CSV upload theo quy tắc linh hoạt (không cần biết schema trước).

**Không có biến môi trường.**

**Các bước xử lý:**

| Bước | Xử lý | Mô tả |
|------|-------|-------|
| 1 | Skip check | Nếu `data.get('skip')` là True, trả về data không đổi |
| 2 | Normalize headers | Lowercase, strip whitespace, thay khoảng trắng bằng `_` |
| 3 | Drop empty rows | Xóa dòng toàn `NaN` |
| 4 | Strip string columns | Trim whitespace tất cả cột string |
| 5 | Drop duplicates | Xóa dòng trùng hoàn toàn |
| 6 | Add metadata | `_row_number` (1-indexed) |
| 7 | Calculate metrics | `raw_rows`, `cleaned_rows`, `dropped_rows`, `duplicate_rows`, `null_cells` |

**Output:** Dict với dữ liệu gốc + thêm `quality_metrics`:
```python
{
    **data_from_extractor,    # Tất cả fields từ extractor
    'dataframe': cleaned_df,  # DataFrame đã làm sạch
    'quality_metrics': {
        'raw_rows': int,
        'cleaned_rows': int,
        'dropped_rows': int,
        'duplicate_rows': int,
        'null_cells': int,
        'processed_at': 'ISO timestamp',
    }
}
```

---

### Block 3: `csv_to_rustfs_silver.py` (Data Exporter)

**File:** `mage/data_exporters/csv_to_rustfs_silver.py`

**Mô tả:** Ghi cleaned CSV DataFrame vào RustFS silver layer dưới dạng Parquet.

**Biến môi trường:** Tương tự `silver_to_rustfs.py`.

**File naming convention:**
```
silver/csv_silver/<run_id>/cleaned_<run_id>.parquet
```

---

### Block 4: `load_csv_reporting_clickhouse.py` (Data Exporter)

**File:** `mage/data_exporters/load_csv_reporting_clickhouse.py`

**Mô tả:** Đọc cleaned CSV từ RustFS silver và nạp vào 4 ClickHouse tables.

**Biến môi trường:** Tương tự `load_to_clickhouse.py`.

**Tables được cập nhật:**

| Table | Dữ liệu | Mô tả |
|-------|---------|-------|
| `analytics.csv_clean_rows` | 1 dòng/row CSV | JSON của từng dòng đã làm sạch |
| `analytics.csv_quality_metrics` | 1 dòng/file | Số liệu chất lượng |
| `analytics.csv_upload_events` | 1 dòng/lần chạy | Trạng thái xử lý (success/failed) |
| `analytics.pipeline_runs` | 1 dòng/lần chạy | Lịch sử run |

**Lưu ý:** Nếu insert vào ClickHouse thất bại, vẫn ghi `status='failed'` vào `csv_upload_events` để không bị skip mãi mãi.

---

## 4. Cấu hình I/O (io_config.yaml)

**File:** `mage/io_config.yaml`

File này định nghĩa các "profiles" kết nối cho Mage. Mỗi profile là một set credentials có thể được chọn trong Data Loader/Exporter.

```yaml
version: 0.1.1

# Profile mặc định: metadata DB của Mage
default:
  POSTGRES_DBNAME: "{{ env_var('MAGE_DB_NAME') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('MAGE_DB_PASSWORD') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: public
  POSTGRES_USER: "{{ env_var('MAGE_DB_USER') }}"
  POSTGRES_CONNECTION_METHOD: direct

# Profile nguồn dữ liệu ETL
source_db:
  POSTGRES_DBNAME: "{{ env_var('POSTGRES_DB') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('POSTGRES_PASSWORD') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: public
  POSTGRES_USER: "{{ env_var('POSTGRES_USER') }}"
  POSTGRES_CONNECTION_METHOD: direct

# Profile workspace riêng của người dùng
custom_db:
  POSTGRES_DBNAME: "{{ env_var('CUSTOM_DB_NAME', '') }}"
  POSTGRES_HOST: dlh-postgres
  POSTGRES_PASSWORD: "{{ env_var('CUSTOM_DB_PASSWORD', '') }}"
  POSTGRES_PORT: 5432
  POSTGRES_SCHEMA: "{{ env_var('CUSTOM_SCHEMA', 'public') }}"
  POSTGRES_USER: "{{ env_var('CUSTOM_DB_USER', '') }}"
  POSTGRES_CONNECTION_METHOD: direct

# Profile ClickHouse
clickhouse:
  CLICKHOUSE_DATABASE: "{{ env_var('CLICKHOUSE_DB') }}"
  CLICKHOUSE_HOST: dlh-clickhouse
  CLICKHOUSE_HTTP_PORT: 8123
  CLICKHOUSE_PASSWORD: "{{ env_var('CLICKHOUSE_PASSWORD') }}"
  CLICKHOUSE_TCP_PORT: 9000
  CLICKHOUSE_USERNAME: "{{ env_var('CLICKHOUSE_USER') }}"
```

**Cách dùng profile trong Mage UI:**
- Khi tạo Data Loader PostgreSQL: chọn profile `source_db` hoặc `custom_db`
- Khi tạo Data Exporter ClickHouse: chọn profile `clickhouse`

---

## 5. Thêm bảng nguồn mới

### Cách 1: Dùng biến `SOURCE_TABLE` (đơn giản nhất)

```bash
# Trong .env
SOURCE_TABLE=my_orders_table
SOURCE_DB_NAME=my_business_db
SOURCE_DB_USER=my_db_user
SOURCE_DB_PASSWORD=my_password
SOURCE_SCHEMA=sales
```

Pipeline sẽ extract toàn bộ bảng `sales.my_orders_table`.

### Cách 2: Thêm vào `SOURCE_TABLE_CANDIDATES`

```bash
# Trong .env – pipeline sẽ tự tìm bảng đầu tiên tồn tại
SOURCE_TABLE_CANDIDATES=Demo,test_projects,my_orders,transactions
```

### Cách 3: Tùy chỉnh `extract_postgres.py`

Nếu cần query phức tạp hơn (filter, join, custom columns), chỉnh sửa file:

```python
# mage/data_loaders/extract_postgres.py
# Thay đổi query:
query = sql.SQL(
    'SELECT id, name, value, created_at FROM {}.{} WHERE status = %s'
).format(
    sql.Identifier(schema),
    sql.Identifier(resolved_table),
)
df = pd.read_sql(query.as_string(conn), conn, params=['active'])
```

### Cách 4: Tùy chỉnh `transform_silver.py` cho schema mới

Nếu bảng nguồn có cột khác với bảng Demo, cập nhật transformer:

```python
# Thêm xử lý cho cột mới
if 'phone_number' in df.columns:
    # Normalize phone numbers
    df['phone_number'] = df['phone_number'].str.replace(r'[^\d+]', '', regex=True)

if 'order_amount' in df.columns:
    df['order_amount'] = pd.to_numeric(df['order_amount'], errors='coerce')
    df.loc[df['order_amount'] < 0, 'order_amount'] = None
```

---

## 6. Tùy chỉnh pipeline

### Thêm bước transform mới

1. Tạo file mới trong `mage/transformers/`:

```python
# mage/transformers/enrich_with_geo.py
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer

@transformer
def enrich_with_geo(df: pd.DataFrame, *args, **kwargs):
    """Thêm thông tin địa lý từ region code."""
    region_map = {
        'hn': 'Hà Nội', 
        'hcm': 'TP. Hồ Chí Minh',
        'dn': 'Đà Nẵng',
    }
    if 'region_code' in df.columns:
        df['region_name'] = df['region_code'].map(region_map)
    return df
```

2. Mở Mage UI (http://localhost:26789)
3. Vào pipeline `etl_postgres_to_lakehouse`
4. Click "Add block" → chọn file transformer mới
5. Kéo thả để sắp xếp thứ tự

### Thay đổi lịch chạy

```yaml
# Trong mage/pipelines/etl_postgres_to_lakehouse/metadata.yaml
# Tìm schedule và thay đổi cron expression
schedule:
  - cron: "0 */6 * * *"   # Mỗi 6 giờ → đổi thành:
  # - cron: "0 2 * * *"   # Mỗi ngày lúc 2:00 AM
  # - cron: "0 */1 * * *" # Mỗi 1 giờ
  # - cron: "*/30 * * * *"# Mỗi 30 phút
```

Hoặc qua Mage UI: Pipelines → Triggers → chỉnh Schedule.

### Thêm notification khi pipeline thất bại

Trong Mage UI: Settings → Alerts → thêm webhook Slack/Teams/Email.

---

## 7. Xử lý lỗi và logging

### Cấu trúc log

Tất cả blocks dùng format log nhất quán:

```python
print(f"[block_name] key=value key=value ...")
```

Ví dụ:
```
[extract_postgres] run_id=abc123  rows=100000  table=public.Demo
[transform_silver] Duplicates removed: 123
[transform_silver] Silver rows ready: 99877
[transform_gold] daily=365 rows  by_region=8 rows  by_category=12 rows
[load_to_clickhouse] From RustFS Silver → silver_demo: 99877 rows
[load_to_clickhouse] COMPLETE: run_id=abc123  status=success  silver=99877  daily=365
```

### Xem log pipeline

```bash
# Xem log Mage real-time
docker compose logs -f mage

# Lọc log của pipeline cụ thể
docker compose logs mage | grep "\[extract_postgres\]"
docker compose logs mage | grep "ERROR"

# Xem run history trong ClickHouse
docker compose exec clickhouse clickhouse-client --query "
SELECT
    run_id,
    pipeline_name,
    status,
    rows_silver,
    rows_gold_daily,
    started_at,
    dateDiff('second', started_at, ended_at) AS duration_seconds,
    error_message
FROM analytics.pipeline_runs
ORDER BY started_at DESC
LIMIT 10
FORMAT Pretty"
```

### Xử lý pipeline thất bại

```bash
# Xem lý do thất bại
docker compose exec clickhouse clickhouse-client --query "
SELECT error_message, started_at
FROM analytics.pipeline_runs
WHERE status = 'failed'
ORDER BY started_at DESC
LIMIT 5
FORMAT Pretty"

# Chạy lại pipeline
docker compose exec mage mage run etl_postgres_to_lakehouse

# Nếu ClickHouse tables bị corrupt: rebuild từ RustFS
docker compose exec clickhouse clickhouse-client --query "TRUNCATE TABLE analytics.silver_demo"
docker compose exec mage mage run etl_postgres_to_lakehouse
# load_to_clickhouse sẽ đọc lại từ RustFS
```

### Xử lý CSV bị stuck (không được xử lý mãi)

Nếu pipeline ghi `status='failed'` vào `csv_upload_events`, file đó sẽ không bị bỏ qua và sẽ được thử lại lần sau. Nhưng nếu file bị corrupt hoặc format sai:

```bash
# Xem danh sách CSV failed
docker compose exec clickhouse clickhouse-client --query "
SELECT source_key, status, error_message, processed_at
FROM analytics.csv_upload_events
WHERE status = 'failed'
ORDER BY processed_at DESC
FORMAT Pretty"

# Đánh dấu file là 'ignored' để bỏ qua
# Hoặc xóa file đó khỏi RustFS qua Web Console
```

---

## 8. Schema ClickHouse

### analytics.silver_demo

Dữ liệu từ bảng Demo PostgreSQL sau khi làm sạch.

```sql
CREATE TABLE analytics.silver_demo
(
    id Nullable(Int64),
    name Nullable(String),
    category Nullable(String),
    value Nullable(Float64),
    quantity Nullable(Int32),
    order_date Nullable(Date),
    region Nullable(String),
    status Nullable(String),
    customer_email Nullable(String),
    notes Nullable(String),
    created_at Nullable(DateTime64(3)),
    _pipeline_run_id String DEFAULT '',
    _source_table String DEFAULT 'Demo',
    _silver_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(toDateTime(_silver_processed_at))
ORDER BY (_silver_processed_at, _pipeline_run_id);
```

### analytics.gold_demo_daily

```sql
CREATE TABLE analytics.gold_demo_daily
(
    order_date Date,
    order_count Int64,
    total_revenue Float64,
    avg_order_value Float64,
    total_quantity Int64,
    unique_customers Int64,
    unique_regions Int64,
    unique_categories Int64,
    _pipeline_run_id String DEFAULT '',
    _gold_processed_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (order_date, _pipeline_run_id);
```

### analytics.csv_quality_metrics

```sql
CREATE TABLE analytics.csv_quality_metrics
(
    pipeline_run_id String,
    source_key String,          -- Đường dẫn S3
    source_etag String,         -- ETag file (fingerprint)
    raw_rows Int64,             -- Số dòng trước khi làm sạch
    cleaned_rows Int64,         -- Số dòng sau khi làm sạch
    dropped_rows Int64,         -- Số dòng bị loại (raw - cleaned)
    duplicate_rows Int64,       -- Số dòng duplicate bị xóa
    null_cells Int64,           -- Tổng số ô null trong DataFrame
    processed_at DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(processed_at)
ORDER BY (processed_at, source_key);
```

### analytics.pipeline_runs

```sql
CREATE TABLE analytics.pipeline_runs
(
    run_id String,
    pipeline_name String,
    status String,              -- 'success' hoặc 'failed'
    started_at DateTime64(3),
    ended_at Nullable(DateTime64(3)),
    rows_extracted Int64 DEFAULT 0,
    rows_silver Int64 DEFAULT 0,
    rows_gold_daily Int64 DEFAULT 0,
    rows_gold_region Int64 DEFAULT 0,
    rows_gold_category Int64 DEFAULT 0,
    error_message Nullable(String),
    _created_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY started_at;
```

### Queries hữu ích

```sql
-- Tổng hợp revenue theo ngày (7 ngày gần nhất)
SELECT order_date, total_revenue, order_count
FROM analytics.gold_demo_daily
WHERE order_date >= today() - 7
ORDER BY order_date;

-- Top categories theo revenue
SELECT category, sum(total_revenue) AS revenue
FROM analytics.gold_demo_by_category
GROUP BY category
ORDER BY revenue DESC;

-- CSV quality summary
SELECT 
    source_key,
    raw_rows,
    cleaned_rows,
    round(cleaned_rows * 100.0 / raw_rows, 1) AS quality_pct,
    duplicate_rows,
    processed_at
FROM analytics.csv_quality_metrics
ORDER BY processed_at DESC
LIMIT 20;

-- Pipeline success rate (7 ngày)
SELECT
    pipeline_name,
    countIf(status = 'success') AS success,
    countIf(status = 'failed') AS failed,
    round(countIf(status='success') * 100.0 / count(), 1) AS success_rate
FROM analytics.pipeline_runs
WHERE started_at >= now() - INTERVAL 7 DAY
GROUP BY pipeline_name;
```

---

*Xem thêm: [README.md](../README.md) | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md)*

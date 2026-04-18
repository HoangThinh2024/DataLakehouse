# DataLakehouse – Modern Data Stack Architecture

Kiến trúc hiện đại cho Data Lakehouse với 5 tầng xử lý dữ liệu đầy đủ chạy trên Docker.

## Sơ đồ kiến trúc

```
INGEST (Layer 1)
  ↓
STORAGE (Layer 2):  PostgreSQL 17 ← → RustFS (S3) ← → ClickHouse
  ↓
PROCESS (Layer 3):  Mage.ai (ETL) ← → dbt Core (Transform) ← → Great Expectations (QA)
  ↓
SERVING (Layer 4):  Adminer ← → NocoDB ← → Metabase
  ↓ (via Nginx Proxy Manager)
REPORT (Layer 5):   Apache Superset ← → Grafana
  ↓
INFRASTRUCTURE:     Docker Engine (WSL2)
```

## Các tầng chi tiết

### Layer 1: INGEST (Thêm)
- **Web Upload**: Upload CSV, XLSX via Web UI
- **API/Connectors**: Airbyte hoặc connector tùy chỉnh
- **Manual/IT tools**: DBeaver, pgAdmin

### Layer 2: STORAGE (Lưu trữ)
- **PostgreSQL 17**: OLTP database, metadata store, lưu thông tin dataset/pipeline
- **RustFS**: S3-compatible object storage, lưu dữ liệu theo Bronze/Silver/Gold
- **ClickHouse**: OLAP analytics engine, lưu dữ liệu đã xử lý nhằm phục vụ truy vấn nhanh

### Layer 3: PROCESS (Xử lý)
- **Mage.ai**: ETL pipeline orchestration, data cleaning, scheduling
- **dbt Core**: Transformation và data modeling trên tầng Silver/Gold
- **Great Expectations**: Data quality validation, profiling

### Layer 4: SERVING (Phục vụ)
- **Adminer**: Database admin panel (IT only)
- **NocoDB**: Web database UI, CRUD interface cho data management
- **Metabase**: Internal BI, data exploration, dashboards
- **Nginx Proxy Manager**: Reverse proxy, SSL, routing, load balancing

### Layer 5: REPORT (Báo cáo)
- **Apache Superset**: Modern open-source BI, advanced dashboards
- **Grafana**: Operational metrics, monitoring dashboards
- **Power BI Desktop**: (Local, connect via DirectQuery)

## Data Flow

1. **Ingest**: Dữ liệu mới upload/import vào Bronze
2. **Validate**: Great Expectations kiểm tra chất lượng
3. **Transform**: Mage.ai + dbt clean, standardize sang Silver
4. **Aggregate**: dbt model, aggregate sang Gold cho BI
5. **Serve**: NocoDB/Metabase/Superset truy vấn từ PostgreSQL hoặc ClickHouse
6. **Monitor**: Grafana giám sát system health

## Storage Layering (RustFS + ClickHouse)

- **Bronze** (RustFS): Raw immutable data từ nguồn
- **Silver** (RustFS): Cleaned, standardized, conformed data
- **Gold** (RustFS): Business-level aggregates cho BI
- **ClickHouse**: Denormalized tables cho fast analytics queries

## Metadata Model

PostgreSQL lưu:
- `lakehouse.dataset`: Danh mục dataset
- `lakehouse.data_object`: Metadata object (bucket, key, format, size, partition)
- `lakehouse.pipeline_run`: ETL run history, lineage, status

## Quy ước Naming

RustFS:
```
bronze/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet
silver/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet
gold/<domain>/<data_mart>/dt=YYYY-MM-DD/file.parquet
```

ClickHouse:
```
<domain>_<dataset>_bronze     (raw materialized view)
<domain>_<dataset>_silver     (cleaned table)
<domain>_<data_mart>_gold     (aggregated table)
```

## Deployment Notes

- **Local Dev**: Chạy toàn bộ 11 services (1-2GB memory tùy từng service)
- **WSL2**: Recommended cho Windows development
- **Production**: Tăng replicas, add HA, implement monitoring alerts

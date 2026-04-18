# DataLakehouse – Architecture (Updated)

## 1. Layers

1. INGEST
- Web upload / API / manual tools

2. STORAGE
- PostgreSQL: central metadata/config
- RustFS: object storage cho Bronze/Silver/Gold
- ClickHouse: OLAP serving engine

3. PROCESS
- Mage.ai: orchestration + data processing

4. SERVING
- NocoDB
- Nginx Proxy Manager

5. REPORT
- Superset
- Grafana

## 2. Data Flow

1. Ingest data vào RustFS Bronze.
2. Mage xử lý và ghi Silver/Gold.
3. ClickHouse đọc dữ liệu để phục vụ truy vấn analytics.
4. BI tools (Superset/Grafana) lấy dữ liệu từ ClickHouse/PostgreSQL.

## 3. ClickHouse "Lake Ready" áp dụng trong stack này

- RustFS (S3-compatible) là lớp data lake chính.
- ClickHouse dùng cho analytical serving, không thay thế data lake.
- Thiết kế tách storage và compute giúp scale tốt hơn cho workload BI/OLAP.

## 4. Operational Notes

- Tên container đã prefixed `dlh-` để tránh đụng môi trường khác.
- Port map dùng dải riêng để giảm xung đột local.
- Metadata/config tập trung vào PostgreSQL cho vận hành dễ hơn.

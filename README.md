# DataLakehouse

Hướng dẫn triển khai mô hình Data Lakehouse tối giản với:
- PostgreSQL: lưu metadata và thông tin chạy pipeline
- RustFS (S3-compatible): lưu dữ liệu theo các tầng Bronze, Silver, Gold

Tài liệu này giúp bạn hiểu kiến trúc và chạy hệ thống từ đầu đến cuối trên môi trường local.

## 1. Data Lakehouse là gì?

Data Lakehouse là kiến trúc kết hợp:
- Data Lake: lưu dữ liệu thô, đa định dạng, mở rộng tốt trên object storage
- Data Warehouse: quản trị schema, chất lượng dữ liệu và phục vụ phân tích

Trong dự án này:
- RustFS đóng vai trò Data Lake (S3 API)
- PostgreSQL đóng vai trò metadata store

## 2. Kiến trúc tổng quan

Ba tầng dữ liệu chính:
- Bronze: dữ liệu raw mới ingest từ nguồn
- Silver: dữ liệu đã làm sạch, chuẩn hóa
- Gold: dữ liệu đã tổng hợp để phục vụ BI và báo cáo

Luồng xử lý điển hình:
1. Đẩy dữ liệu thô vào bucket Bronze
2. Biến đổi và chuẩn hóa sang Silver
3. Tổng hợp theo nghiệp vụ sang Gold
4. Ghi metadata đối tượng và lịch sử pipeline vào PostgreSQL

Xem thêm mô tả kiến trúc tại [docs/architecture.md](docs/architecture.md).

## 3. Cấu trúc thư mục

- [docker-compose.yaml](docker-compose.yaml): cấu hình các service
- [postgres/init/001_lakehouse_metadata.sql](postgres/init/001_lakehouse_metadata.sql): script khởi tạo schema metadata
- [docs/architecture.md](docs/architecture.md): mô tả logic Bronze/Silver/Gold

## 4. Thành phần hệ thống

### 4.1 PostgreSQL

PostgreSQL lưu metadata Lakehouse với các bảng chính:
- lakehouse.dataset: danh mục dataset
- lakehouse.data_object: metadata từng object trong RustFS
- lakehouse.pipeline_run: trạng thái và lịch sử chạy pipeline

Script khởi tạo nằm ở [postgres/init/001_lakehouse_metadata.sql](postgres/init/001_lakehouse_metadata.sql) và được chạy tự động khi PostgreSQL khởi tạo lần đầu.

### 4.2 RustFS

RustFS là object storage tương thích S3.

Service rustfs-init trong [docker-compose.yaml](docker-compose.yaml) sẽ tự tạo ba bucket:
- bronze
- silver
- gold

Mẫu tổ chức object key khuyến nghị:
- bronze/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet
- silver/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet
- gold/<domain>/<data_mart>/dt=YYYY-MM-DD/file.parquet

## 5. Chuẩn bị môi trường

Copy file `.env.example` để tạo file `.env` cá nhân:

```bash
cp .env.example .env
```

Mở file `.env` và cập nhật giá trị theo nhu cầu của bạn:

```env
POSTGRES_DB=datalakehouse
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_PORT=55432

RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin
RUSTFS_API_PORT=19000
RUSTFS_CONSOLE_PORT=19001
RUSTFS_CORS_ALLOWED_ORIGINS=http://localhost:19000
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=http://localhost:19001
```

**Lưu ý bảo mật:**
- File `.env` được gitignore và sẽ không được commit lên GitHub.
- Chỉ `.env.example` được commit làm mẫu.
- Nên đổi mật khẩu và key trong môi trường production.
- Không bao giờ commit file `.env` thực tế chứa thông tin nhạy cảm.

## 6. Khởi động hệ thống

Chạy các lệnh sau trong thư mục dự án:

```bash
docker compose up -d
docker compose ps
docker compose logs -f
```

Dừng hệ thống:

```bash
docker compose down
```

Nếu cần khởi tạo lại dữ liệu từ đầu (bao gồm chạy lại script init của PostgreSQL):

```bash
docker compose down -v
docker compose up -d
```

## 7. Kiểm tra sau khi chạy

Các endpoint mặc định:
- PostgreSQL: localhost:55432
- RustFS S3 API: http://localhost:19000
- RustFS Console: http://localhost:19001

Các bước kiểm tra nhanh:
1. Mở RustFS Console và xác nhận có bucket bronze, silver, gold.
2. Kết nối PostgreSQL và kiểm tra schema lakehouse.
3. Kiểm tra ba bảng dataset, data_object, pipeline_run đã được tạo.

## 8. Cách dùng trong pipeline thực tế

Quy ước tối thiểu khi ingest/transform:
1. Khi ghi file mới vào RustFS, chèn metadata tương ứng vào lakehouse.data_object.
2. Mỗi job ETL/ELT tạo một bản ghi trong lakehouse.pipeline_run.
3. Dataset mới cần được đăng ký trong lakehouse.dataset trước khi đưa vào production.

Gợi ý mở rộng:
- Dùng Airflow hoặc Prefect để orchestration.
- Dùng Spark hoặc Trino để xử lý và truy vấn trực tiếp trên RustFS.
- Bổ sung data quality checks cho Silver và Gold.

## 9. Xử lý sự cố thường gặp

1. PostgreSQL không chạy sau khi sửa script init
- Nguyên nhân: volume cũ đã tồn tại, script init không chạy lại.
- Cách xử lý: chạy docker compose down -v rồi up lại.

2. Không thấy bucket bronze/silver/gold
- Kiểm tra service rustfs-init có chạy xong chưa.
- Xem log bằng docker compose logs rustfs-init.

3. Không truy cập được RustFS Console
- Kiểm tra cổng 19001 có bị chiếm không.
- Đối chiếu biến RUSTFS_CONSOLE_PORT trong .env.

## 10. Lộ trình phát triển tiếp theo

1. Bổ sung data catalog và phân quyền truy cập theo domain.
2. Chuẩn hóa naming convention cho bucket, prefix và partition.
3. Tích hợp dbt hoặc framework transform cho tầng Gold.
4. Thiết lập monitoring, alert và lineage đầy đủ.

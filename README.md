# DataLakehouse – Modern Data Stack

Stack Data Lakehouse theo hướng gọn, tránh xung đột port, tập trung quản lý metadata/config qua PostgreSQL.

## Thành phần hiện tại

- PostgreSQL 17: metadata/config trung tâm
- RustFS: data lake S3-compatible (Bronze/Silver/Gold)
- ClickHouse: lớp OLAP tăng tốc truy vấn trên dữ liệu lake
- Mage.ai: orchestration/processing
- NocoDB, Superset, Grafana: serving và reporting
- Nginx Proxy Manager: reverse proxy (optional, đang để comment)

Đã loại bỏ theo yêu cầu:
- dbt Core
- Great Expectations
- Adminer
- Auth/RBAC service riêng

## Điểm tham chiếu ClickHouse

Theo hướng “data lake ready” của ClickHouse:
- Object storage (S3) là lớp lưu trữ chính cho dữ liệu lake.
- ClickHouse đóng vai trò query acceleration/serving cho analytics.
- Tách lớp lưu trữ (RustFS) và lớp phân tích (ClickHouse) để scale linh hoạt.

## Chuẩn bị nhanh

1. Tạo `.env` từ mẫu:

```bash
cp .env.example .env
```

2. Khởi động stack:

```bash
docker compose up -d
```

`rustfs-init` được cấu hình ở profile `bootstrap` (optional), nên sẽ không chạy mặc định.
Khi mạng ổn định và muốn tự động tạo bucket Bronze/Silver/Gold:

```bash
docker compose --profile bootstrap up -d rustfs-init
```

3. Kiểm tra trạng thái:

```bash
docker compose ps
```

4. Dừng stack:

```bash
docker compose down
```

## Network dùng chung: `web_network`

Project cấu hình dùng network ngoài (`external`) tên `web_network` cho toàn bộ service.

Tạo network một lần trước khi chạy stack:

```bash
docker network create web_network
```

Kiểm tra network:

```bash
docker network ls | grep web_network
```

Nếu đã tồn tại, Docker sẽ báo lỗi "already exists" và bạn có thể bỏ qua.

## Timezone toàn dự án

Toàn bộ service dùng chung timezone qua biến môi trường:

```env
TZ=Asia/Ho_Chi_Minh
```

Lưu ý: bạn ghi "Asisa/Ho_Chi_Minh" trong yêu cầu, nhưng timezone chuẩn là `Asia/Ho_Chi_Minh`.

## Cổng mặc định (đã đổi để hạn chế xung đột)

- PostgreSQL: `25432`
- RustFS API: `29100`
- RustFS Console: `29101`
- ClickHouse HTTP: `28123`
- ClickHouse TCP: `29000`
- Mage: `26789`
- NocoDB: `28082`
- Superset: `28088`
- Grafana: `23001`
- Nginx PM HTTP/HTTPS/Admin: `28080` / `28443` / `28081` (optional)

## Cách quản lý "đều vào PostgreSQL"

Các service đã cấu hình dùng PostgreSQL làm backend metadata/config:
- Mage.ai
- NocoDB
- Superset
- Grafana

PostgreSQL có 1 user admin toàn hệ thống:
- `POSTGRES_USER` (mặc định trong mẫu: `dlh_admin`)
- Dùng để quản trị tổng thể và xem toàn bộ database/app

Host nội bộ của PostgreSQL trong stack này là `dlh-postgres`, không phải `postgres`, để tránh đụng với các container/stack khác đang dùng mạng Docker chung.

Lưu ý: nếu bạn đổi `POSTGRES_PASSWORD` sau khi volume PostgreSQL đã được khởi tạo, hãy reset volume trước khi chạy lại stack bằng `docker compose down -v && docker compose up -d`. Nếu không, `postgres-bootstrap` sẽ báo lỗi xác thực vì volume cũ vẫn giữ mật khẩu cũ.

Mỗi service dùng một database riêng trong cùng PostgreSQL server:
- `dlh_mage`
- `dlh_nocodb`
- `dlh_superset`
- `dlh_grafana`

Mỗi service dùng user riêng với quyền tối thiểu trên database của chính nó:
- `dlh_mage_user` -> `dlh_mage`
- `dlh_nocodb_user` -> `dlh_nocodb`
- `dlh_superset_user` -> `dlh_superset`
- `dlh_grafana_user` -> `dlh_grafana`

Bootstrap bảo mật được tạo tự động bởi script [postgres/init/000_create_app_security.sh](postgres/init/000_create_app_security.sh) khi khởi tạo volume PostgreSQL lần đầu.
Script sẽ:
- Tạo role cho từng app (không có quyền superuser/createdb/createrole)
- Tạo database riêng cho từng app và gán owner tương ứng
- Thu hồi quyền public mặc định và chỉ cấp quyền cần thiết cho app user

Lưu ý:
- Nginx Proxy Manager đang được comment trong [docker-compose.yaml](docker-compose.yaml). Nếu cần, bỏ comment block `nginx-proxy-manager` để bật.
- Nginx Proxy Manager image mặc định dùng SQLite/MySQL (không hỗ trợ PostgreSQL trực tiếp trong cấu hình hiện tại), nên vẫn để SQLite nội bộ.

## Tài liệu kiến trúc

- [docs/ARCHITECTURE_MODERN_STACK.md](docs/ARCHITECTURE_MODERN_STACK.md)

## Demo Pipeline Script

Script mẫu cho quy trình `Postgres -> RustFS bronze -> ClickHouse` nằm ở [scripts/demo_to_lakehouse.py](scripts/demo_to_lakehouse.py).

Chạy từ host:

```bash
pip install -r scripts/requirements.txt
SOURCE_DB_HOST=127.0.0.1 RUSTFS_ENDPOINT_URL=http://127.0.0.1:29100 CLICKHOUSE_HTTP_URL=http://127.0.0.1:28123 \
	python scripts/demo_to_lakehouse.py
```

Nếu chạy trong Docker network của stack, bạn có thể để mặc định:
- `SOURCE_DB_HOST=dlh-postgres`
- `RUSTFS_ENDPOINT_URL=http://dlh-rustfs:9000`
- `CLICKHOUSE_HTTP_URL=http://dlh-clickhouse:8123`

Biến có thể đổi:
- `SOURCE_SCHEMA` (mặc định `public`)
- `SOURCE_TABLE` (mặc định `Demo`)
- `SOURCE_QUERY` nếu muốn tự viết SQL thay vì đọc toàn bộ table `Demo`
- `RUSTFS_BRONZE_BUCKET` (mặc định `bronze`)
- `RUSTFS_PREFIX` (mặc định `demo`)
- `CLICKHOUSE_DB` (mặc định `analytics`)
- `CLICKHOUSE_TABLE` (mặc định `demo_raw`)

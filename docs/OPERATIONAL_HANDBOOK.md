# Cẩm nang Vận hành Hệ thống DataLakehouse Toàn diện
*Dành cho Người dùng và Quản lý Hệ thống*

Tài liệu này được thiết kế để giúp bạn hiểu từ cái nhìn tổng quan nhất đến cách thực hiện từng thao tác nhỏ trong hệ thống. Chúng ta sẽ cùng nhau vận hành một "Nhà máy Sản xuất Thông tin" hiện đại.

---

## PHẦN 1: TỔNG QUAN VỀ "NHÀ MÁY" CỦA CHÚNG TÔI

Hãy tưởng tượng hệ thống này là một dây chuyền sản xuất tự động:

1.  **Cổng tiếp nhận (NocoDB/Postgres):** Nơi bạn nhập nguyên liệu thô (đơn hàng).
2.  **Xe vận chuyển (Mage.ai):** Robot tự động đi gom hàng mang về kho.
3.  **Kho tổng khổng lồ (RustFS):** Nơi chứa hàng triệu tấn hàng hóa an toàn với chi phí rẻ.
4.  **Xưởng chế biến (Mage.ai - Transform):** Nơi rửa sạch hàng bẩn, đóng gói hàng đẹp.
5.  **Showroom siêu tốc (ClickHouse):** Nơi trưng bày hàng hóa sao cho khách hàng (biểu đồ) tìm thấy nhanh nhất.
6.  **Bảng điện tử (Superset/Grafana):** Màn hình hiển thị kết quả kinh doanh cho sếp.

---

## PHẦN 2: HƯỚNG DẪN CHI TIẾT (TUTORIAL)

Dưới đây là quy trình thực tế để đưa một đơn hàng vào hệ thống:

### Bước 1: Nhập đơn hàng mới
*   **Công cụ:** **NocoDB**
*   **Địa chỉ:** `http://localhost:28082`
*   **Thao tác:**
    1. Đăng nhập vào giao diện (giống Excel).
    2. Chọn bảng **"Demo"** hoặc **"Orders"**.
    3. Nhấn **"Add New Row"** (Thêm dòng mới).
    4. Nhập các thông tin: Tên khách hàng, Sản phẩm, Giá tiền, Ngày đặt hàng.
    5. Nhấn **Save**.
*   **Tại sao:** NocoDB giúp bạn làm việc với cơ sở dữ liệu chuyên nghiệp mà chỉ cần kỹ năng dùng Excel cơ bản.

### Bước 2: Kích hoạt Robot xử lý
*   **Công cụ:** **Mage.ai**
*   **Địa chỉ:** `http://localhost:26789`
*   **Thao tác:**
    1. Thông thường, Robot sẽ tự chạy mỗi 6 tiếng.
    2. Nếu bạn muốn thấy kết quả ngay, hãy chọn Pipeline `etl_postgres_to_lakehouse`.
    3. Nhấn nút **"Run Pipeline Now"**.
*   **Điều gì xảy ra:** Mage sẽ thực hiện 3 việc:
    - **Extract:** Lấy đơn hàng bạn vừa nhập từ NocoDB.
    - **Transform:** Rửa sạch dữ liệu (sửa lỗi chính tả, tính toán doanh thu).
    - **Load:** Đẩy dữ liệu vào Kho (RustFS) và Showroom (ClickHouse).

### Bước 3: Kiểm tra hàng trong kho (Tùy chọn)
*   **Công cụ:** **RustFS Console**
*   **Địa chỉ:** `http://localhost:29101`
*   **Thao tác:**
    1. Vào mục **Buckets**.
    2. Bạn sẽ thấy 3 ngăn: `bronze` (hàng thô), `silver` (hàng sạch), `gold` (hàng đóng gói).
    3. Mở ngăn `gold` để thấy các tệp tin dữ liệu đã được tính toán xong.
*   **Tại sao:** RustFS giúp lưu trữ dữ liệu vĩnh viễn với dung lượng cực lớn mà không làm chậm hệ thống.

### Bước 4: Xem báo cáo kinh doanh
*   **Công cụ:** **Apache Superset**
*   **Địa chỉ:** `http://localhost:28088`
*   **Thao tác:**
    1. Đăng nhập và vào mục **Dashboards**.
    2. Chọn biểu đồ **"Sales Overview"**.
    3. Bạn sẽ thấy đơn hàng mình vừa nhập đã được cộng dồn vào tổng doanh thu của ngày/tháng đó.
*   **Tại sao:** ClickHouse đứng sau Superset giúp các biểu đồ này hiện ra ngay lập tức dù bạn có hàng tỷ đơn hàng.

### Bước 5: Theo dõi sức khỏe hệ thống
*   **Công cụ:** **Grafana**
*   **Địa chỉ:** `http://localhost:23001`
*   **Thao tác:**
    1. Xem các biểu đồ kỹ thuật. 
    2. Nếu thấy các đường kẻ xanh mướt là hệ thống đang khỏe.
    3. Nếu thấy màu đỏ, nghĩa là Robot Mage đang bị kẹt ở bước nào đó.
*   **Tại sao:** Đảm bảo hệ thống luôn hoạt động 24/7 mà không cần người trực liên tục.

---

## PHẦN 3: TỔNG KẾT VAI TRÒ VÀ GIÁ TRỊ

| Giai đoạn | Công cụ | Vai trò | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **ĐẦU VÀO** | **NocoDB** | Người tiếp tân | Đơn giản hóa việc nhập liệu cho mọi nhân viên. |
| **LƯU TRỮ** | **PostgreSQL** | Hầm bảo mật | Giữ dữ liệu gốc an toàn tuyệt đối. |
| **ĐIỀU PHỐI**| **Mage.ai** | Quản đốc nhà máy | Tự động hóa mọi công việc chân tay (rửa, lọc dữ liệu). |
| **DỮ LIỆU LỚN**| **RustFS** | Kho tổng | Khả năng mở rộng không giới hạn (Data Lake). |
| **TỐI ƯU** | **ClickHouse** | Động cơ phản lực | Giúp truy vấn báo cáo nhanh gấp 100 lần thông thường. |
| **ĐẦU RA** | **Superset** | Bộ não phân tích | Biến con số vô hồn thành chiến lược kinh doanh. |
| **GIÁM SÁT** | **Grafana** | Bác sĩ hệ thống | Cảnh báo sớm mọi sự cố kỹ thuật. |

---

## PHẦN 5: BẢO TRÌ VÀ KHÔI PHỤC DỮ LIỆU (MAINTENANCE & RECOVERY)

Hệ thống của chúng ta tích hợp sẵn cơ chế bảo trì tự động để đảm bảo dữ liệu luôn an toàn và bộ nhớ luôn tinh gọn.

### 1. Cơ chế Sao lưu (Backup)
*   **Công cụ:** Script `scripts/maintenance_tasks.py` (chạy bên trong container Mage).
*   **Hoạt động:** Sử dụng lệnh `BACKUP` gốc của ClickHouse để nén toàn bộ database `analytics`.
*   **Vị trí lưu trữ:** `s3://backups/clickhouse/YYYY-MM-DD/` (Nằm trong RustFS).
*   **Cách chạy thủ công:**
    ```bash
    docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py
    ```

### 2. Cơ chế Dọn dẹp (Cleanup)
*   **Nguyên tắc:** Giữ lại dữ liệu trong **30 ngày**.
*   **Đối tượng dọn dẹp:**
    - Các file Parquet cũ trong lớp `silver` và `gold`.
    - Các bản sao lưu (Backup) cũ hơn 30 ngày.
*   **Lợi ích:** Đảm bảo ổ cứng của bạn không bị đầy theo thời gian do các file phiên bản cũ.

### 3. Quy trình Khôi phục Dữ liệu (Restore Guide)
Trong trường hợp dữ liệu bị hỏng hoặc mất, hãy thực hiện các bước sau để khôi phục từ bản sao lưu gần nhất:

1.  **Xác định bản sao lưu:** Truy cập RustFS Console (`http://localhost:29101`), vào bucket `backups` để tìm ngày bạn muốn khôi phục.
2.  **Thực hiện lệnh Restore:** Chạy lệnh sau bên trong Clickhouse (sử dụng user `doe` hoặc `default` có quyền admin):
    ```sql
    -- 1. Xóa database cũ (Cẩn thận!)
    DROP DATABASE IF EXISTS analytics;

    -- 2. Khôi phục từ S3 (Thay YYYY-MM-DD bằng ngày bạn chọn)
    RESTORE DATABASE analytics FROM S3(
        'http://dlh-rustfs:9000/backups/clickhouse/YYYY-MM-DD/', 
        'rustfsadmin', 
        'rustfsadmin'
    );
    ```
3.  **Kiểm tra:** Sau khi chạy xong, toàn bộ bảng và dữ liệu tại thời điểm đó sẽ xuất hiện trở lại.

### 4. Thiết lập Lịch trình Tự động (Cron job)
Để hệ thống tự bảo trì vào **2:00 sáng hằng ngày**, hãy thêm dòng sau vào `crontab` của máy tính (Linux/WSL):
```bash
0 2 * * * docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py >> /home/johndoe/dlh_maintenance.log 2>&1
```

---
**Lưu ý cho AI/Dev sau này:** Mọi thông tin xác thực cho việc backup đều được lấy từ biến môi trường trong file `.env`. Đảm bảo `RUSTFS_ACCESS_KEY` và `RUSTFS_SECRET_KEY` luôn khớp giữa Mage và RustFS.

---

## PHẦN 4: VẬN HÀNH REDIS VÀ AUTHENTIK (BỔ SUNG)

### Vai trò Redis trong hệ thống hiện tại

- Redis là backend dùng chung cho cache và queue.
- Superset dùng Redis cho cache dashboard/query và SQL Lab results backend.
- Authentik dùng Redis cho worker queue và trạng thái phiên.

### Kiểm tra nhanh Redis

```bash
docker compose ps dlh-redis
docker compose logs dlh-redis --tail 100
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping
```

Kết quả mong đợi: lệnh `ping` trả về `PONG`.

### Khi Superset chậm bất thường

1. Kiểm tra Redis có healthy không.
2. Kiểm tra biến `SUPERSET_REDIS_CACHE_DB` và `SUPERSET_REDIS_RESULTS_DB` trong `.env`.
3. Khởi động lại Superset sau khi đổi biến:

```bash
docker compose up -d dlh-redis superset
```

### Khi Authentik không xử lý background task

1. Kiểm tra `dlh-authentik-worker` và `dlh-redis` cùng healthy.
2. Kiểm tra `REDIS_AUTHENTIK_DB` và `REDIS_PASSWORD` có đồng bộ với compose.
3. Xem log:

```bash
docker compose logs dlh-authentik-server --tail 120
docker compose logs dlh-authentik-worker --tail 120
docker compose logs dlh-redis --tail 120
```

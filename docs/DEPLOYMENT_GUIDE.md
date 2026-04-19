# 🚀 Hướng dẫn Triển khai – DataLakehouse

Tài liệu này hướng dẫn chi tiết cách triển khai DataLakehouse trong các môi trường khác nhau: **local development**, **LAN/team**, và **production server**.

---

## Mục lục

1. [Yêu cầu hệ thống](#1-yêu-cầu-hệ-thống)
2. [Triển khai Local (Development)](#2-triển-khai-local-development)
3. [Triển khai LAN / Team](#3-triển-khai-lan--team)
4. [Triển khai Production Server](#4-triển-khai-production-server)
5. [Cấu hình bảo mật](#5-cấu-hình-bảo-mật)
6. [Quản lý dữ liệu & Backup](#6-quản-lý-dữ-liệu--backup)
7. [Cập nhật Stack](#7-cập-nhật-stack)
8. [Giám sát & Khắc phục sự cố](#8-giám-sát--khắc-phục-sự-cố)
9. [Kiểm tra sau triển khai](#9-kiểm-tra-sau-triển-khai)

---

## 1. Yêu cầu hệ thống

### Phần cứng tối thiểu

| Tài nguyên | Tối thiểu | Khuyến nghị | Production |
|-----------|-----------|-------------|-----------|
| RAM | 4 GB | 8 GB | 16 GB+ |
| CPU | 2 nhân | 4 nhân | 8 nhân+ |
| Ổ đĩa | 10 GB | 30 GB | 100 GB+ SSD |
| Mạng | 10 Mbps | 100 Mbps | 1 Gbps |

### Phần mềm cần thiết

```bash
# Kiểm tra Docker
docker --version
# Cần: Docker Engine 24.0+

# Kiểm tra Docker Compose
docker compose version
# Cần: v2.20+

# Kiểm tra curl (dùng để test)
curl --version
```

### Cài đặt Docker (nếu chưa có)

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# CentOS/RHEL
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# macOS – cài Docker Desktop
# https://docs.docker.com/desktop/mac/install/
```

---

## 2. Triển khai Local (Development)

Môi trường local cho phát triển và thử nghiệm. Tất cả services chỉ accessible từ `localhost`.

### Bước 1 – Clone và cấu hình

```bash
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
cp .env.example .env
```

### Bước 2 – Cấu hình tối thiểu cho local

Chỉnh sửa `.env`:

```bash
# Giữ nguyên bind IP cho local
DLH_BIND_IP=127.0.0.1

# Múi giờ
TZ=Asia/Ho_Chi_Minh

# Database admin (có thể giữ default cho local)
POSTGRES_PASSWORD=localdev123

# RustFS (có thể giữ default cho local)
RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin

# Superset (BẮT BUỘC phải set secret key)
SUPERSET_SECRET_KEY=local-dev-secret-key-change-for-prod
SUPERSET_ADMIN_PASSWORD=admin

# Grafana
GRAFANA_ADMIN_PASSWORD=admin

# ClickHouse (để trống OK cho local)
CLICKHOUSE_PASSWORD=
```

### Bước 3 – Tạo network và khởi động

```bash
docker network create web_network
docker compose up -d
```

### Bước 4 – Kiểm tra khởi động

```bash
# Đợi tất cả services healthy
watch docker compose ps

# Hoặc đợi thủ công (khoảng 2-3 phút)
sleep 120
docker compose ps
```

**Trạng thái mong muốn:**
```
NAME                   STATUS
dlh-postgres           healthy
dlh-rustfs             healthy
dlh-clickhouse         healthy
dlh-mage               running
dlh-superset           running
dlh-grafana            running
dlh-nocodb             running
dlh-postgres-bootstrap exited (0)   ← OK, chỉ chạy một lần
dlh-rustfs-init        exited (0)   ← OK, chỉ chạy một lần
```

### Bước 5 – Tạo dashboard demo (tùy chọn)

```bash
# Chạy ETL và tạo Superset dashboard
python3 scripts/run_etl_and_dashboard.py
```

### URL truy cập local

| Service | URL |
|---------|-----|
| Superset | http://localhost:28088 |
| Grafana | http://localhost:23001 |
| Mage.ai | http://localhost:26789 |
| NocoDB | http://localhost:28082 |
| RustFS Console | http://localhost:29101 |

---

## 3. Triển khai LAN / Team

Cho phép các máy tính trong cùng mạng nội bộ (LAN) truy cập. Không cần SSL nhưng cần IP cố định.

### Bước 1 – Tìm địa chỉ IP LAN

```bash
# Linux
ip addr show | grep "inet " | grep -v 127.0.0.1

# macOS
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig | findstr "IPv4"
```

Ví dụ kết quả: `192.168.1.100`

### Bước 2 – Cấu hình .env cho LAN

```bash
# Bind IP là địa chỉ LAN
DLH_BIND_IP=192.168.1.100

# PostgreSQL host (dùng bởi các services nội bộ)
POSTGRES_HOST=dlh-postgres

# NocoDB và Superset URLs
NOCODB_PUBLIC_URL=http://192.168.1.100:28082
NOCODB_BACKEND_URL=http://192.168.1.100:28082

# CORS cho RustFS
RUSTFS_CORS_ALLOWED_ORIGINS=http://192.168.1.100:29100
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=http://192.168.1.100:29101

# Mật khẩu (nên đặt mạnh hơn local)
POSTGRES_PASSWORD=team-dev-password-123
SUPERSET_SECRET_KEY=$(openssl rand -hex 32)
SUPERSET_ADMIN_PASSWORD=TeamAdmin2024!
GRAFANA_ADMIN_PASSWORD=TeamGrafana2024!
```

### Bước 3 – Khởi động

```bash
docker network create web_network
docker compose up -d
```

### Bước 4 – Kiểm tra firewall (nếu cần)

```bash
# Ubuntu/Debian với ufw
sudo ufw allow from 192.168.1.0/24 to any port 23001   # Grafana
sudo ufw allow from 192.168.1.0/24 to any port 26789   # Mage
sudo ufw allow from 192.168.1.0/24 to any port 28082   # NocoDB
sudo ufw allow from 192.168.1.0/24 to any port 28088   # Superset
sudo ufw allow from 192.168.1.0/24 to any port 29101   # RustFS Console

# CentOS/RHEL với firewalld
sudo firewall-cmd --add-port=28088/tcp --permanent
sudo firewall-cmd --reload
```

### URL truy cập từ LAN

Thay `192.168.1.100` bằng IP LAN thực tế:

| Service | URL |
|---------|-----|
| Superset | http://192.168.1.100:28088 |
| Grafana | http://192.168.1.100:23001 |
| Mage.ai | http://192.168.1.100:26789 |
| NocoDB | http://192.168.1.100:28082 |

---

## 4. Triển khai Production Server

Triển khai trên VPS/cloud server với domain thực, SSL/TLS, và bảo mật đầy đủ.

### Kiến trúc production khuyến nghị

```
Internet
    │
    ▼
Nginx / Caddy  (port 80, 443)
    │ HTTPS + SSL termination
    │ Basic Auth / OAuth
    ├── /superset   → localhost:28088
    ├── /grafana    → localhost:23001
    ├── /mage       → localhost:26789 (internal only)
    ├── /nocodb     → localhost:28082
    └── /storage    → localhost:29101
```

### Bước 1 – Chuẩn bị server

```bash
# Cập nhật hệ thống
sudo apt update && sudo apt upgrade -y

# Cài Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Tạo user riêng cho DataLakehouse
sudo useradd -m -s /bin/bash dlh
sudo usermod -aG docker dlh
su - dlh

# Clone repo
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
```

### Bước 2 – Cấu hình .env production

```bash
# Bind local only (Nginx sẽ proxy từ ngoài vào)
DLH_BIND_IP=127.0.0.1

# Múi giờ server
TZ=UTC

# Mật khẩu mạnh cho tất cả services
POSTGRES_PASSWORD=$(openssl rand -base64 32)
CUSTOM_DB_PASSWORD=$(openssl rand -base64 24)

RUSTFS_ACCESS_KEY=prod$(openssl rand -hex 8)
RUSTFS_SECRET_KEY=$(openssl rand -base64 32)

CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)

MAGE_DB_PASSWORD=$(openssl rand -base64 24)
NOCODB_DB_PASSWORD=$(openssl rand -base64 24)
SUPERSET_SECRET_KEY=$(openssl rand -hex 32)
SUPERSET_DB_PASSWORD=$(openssl rand -base64 24)
SUPERSET_ADMIN_PASSWORD=$(openssl rand -base64 16)
GRAFANA_DB_PASSWORD=$(openssl rand -base64 24)
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)

# URLs với domain thực
NOCODB_PUBLIC_URL=https://data.yourdomain.com
NOCODB_BACKEND_URL=https://data.yourdomain.com

# CORS (thay bằng domain thực)
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com

# Ghim image versions (không dùng latest trong production)
POSTGRES_IMAGE_VERSION=17.2-alpine
CLICKHOUSE_IMAGE_VERSION=24.3.3.102
MAGE_IMAGE_VERSION=0.9.73
GRAFANA_IMAGE_VERSION=10.4.2
SUPERSET_IMAGE_VERSION=3.1.3
```

### Bước 3 – Cài đặt Nginx với SSL (Caddy – dễ nhất)

```bash
# Cài Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Tạo Caddyfile
sudo tee /etc/caddy/Caddyfile << 'EOF'
# Analytics Dashboard
superset.yourdomain.com {
    reverse_proxy localhost:28088
}

# Monitoring
grafana.yourdomain.com {
    reverse_proxy localhost:23001
}

# No-code DB
data.yourdomain.com {
    reverse_proxy localhost:28082
}

# Object Storage Console (chỉ cho admin, thêm auth)
storage.yourdomain.com {
    basicauth {
        admin $2a$14$...hashed-password...
    }
    reverse_proxy localhost:29101
}

# ETL (chỉ cho internal, không public)
# mage.yourdomain.com {
#     basicauth { ... }
#     reverse_proxy localhost:26789
# }
EOF

sudo systemctl reload caddy
```

### Bước 4 – Khởi động và verify

```bash
docker network create web_network
docker compose up -d

# Kiểm tra services
docker compose ps

# Kiểm tra logs
docker compose logs --tail=50

# Verify toàn bộ stack
python3 scripts/verify_lakehouse_architecture.py
```

### Bước 5 – Thiết lập systemd service (auto-start)

```bash
# Tạo systemd service
sudo tee /etc/systemd/system/datalakehouse.service << 'EOF'
[Unit]
Description=DataLakehouse Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/dlh/DataLakehouse
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
User=dlh

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable datalakehouse
sudo systemctl start datalakehouse
```

---

## 5. Cấu hình bảo mật

### Bảo mật PostgreSQL

```bash
# Không expose PostgreSQL ra internet (chỉ localhost)
DLH_BIND_IP=127.0.0.1
DLH_POSTGRES_PORT=25432

# Đặt mật khẩu mạnh cho admin
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Mỗi service dùng user riêng (đã được cấu hình trong bootstrap)
# Mage dùng dlh_mage_user
# Superset dùng dlh_superset_user
# Grafana dùng dlh_grafana_user
# NocoDB dùng dlh_nocodb_user
```

### Bảo mật ClickHouse

```bash
# Đặt mật khẩu (production)
CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)

# Chỉ expose ClickHouse cho internal network (không cần expose ra host cho production)
# Trong docker-compose.yaml, có thể comment out ports: của clickhouse
# và để Grafana/Mage kết nối qua Docker network
```

### Bảo mật RustFS

```bash
# Đặt credentials mạnh
RUSTFS_ACCESS_KEY=prod$(openssl rand -hex 8)
RUSTFS_SECRET_KEY=$(openssl rand -base64 32)

# Giới hạn CORS (không dùng wildcard)
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
```

### Bảo mật Superset

```bash
# Secret key quan trọng nhất
SUPERSET_SECRET_KEY=$(openssl rand -hex 32)

# Đổi mật khẩu admin ngay sau khi login lần đầu
# http://yourdomain.com/users/userinfo/
```

### File permissions

```bash
# .env không được commit và chỉ chủ sở hữu đọc được
chmod 600 .env

# Đảm bảo .gitignore có .env
grep ".env" .gitignore  # phải có
```

---

## 6. Quản lý dữ liệu & Backup

### Cấu trúc Docker volumes

```bash
# Xem volumes hiện có
docker volume ls | grep DataLakehouse

# Kiểm tra kích thước
docker system df -v
```

**Volumes quan trọng:**

| Volume | Service | Ý nghĩa | Backup priority |
|--------|---------|---------|-----------------|
| `postgres_data` | PostgreSQL | Metadata của Mage, Superset, Grafana, NocoDB | 🔴 Cao |
| `clickhouse_data` | ClickHouse | Dữ liệu analytics, gold tables | 🔴 Cao |
| `rustfs_data` | RustFS | Lake storage (raw, silver, gold Parquet) | 🔴 Cao |
| `grafana_data` | Grafana | Dashboards (nếu không dùng PostgreSQL backend) | 🟡 Trung bình |
| `superset_data` | Superset | Cache, uploads | 🟢 Thấp |

### Backup PostgreSQL

```bash
# Backup toàn bộ PostgreSQL
docker compose exec -T dlh-postgres pg_dumpall \
  -U dlh_admin \
  > backup/postgres_$(date +%Y%m%d_%H%M%S).sql

# Backup database cụ thể
docker compose exec -T dlh-postgres pg_dump \
  -U dlh_admin \
  -d datalakehouse \
  > backup/datalakehouse_$(date +%Y%m%d_%H%M%S).sql

# Restore
docker compose exec -T dlh-postgres psql \
  -U dlh_admin \
  < backup/postgres_backup.sql
```

### Backup ClickHouse

```bash
# Backup database analytics
docker compose exec clickhouse clickhouse-client \
  --query "BACKUP DATABASE analytics TO Disk('default', 'backup_$(date +%Y%m%d).zip')"

# Hoặc export bảng ra file
docker compose exec clickhouse clickhouse-client \
  --query "SELECT * FROM analytics.gold_demo_daily FORMAT Parquet" \
  > backup/gold_demo_daily_$(date +%Y%m%d).parquet
```

### Backup RustFS

```bash
# Sync toàn bộ RustFS ra ngoài bằng mc (MinIO client)
mc alias set local http://localhost:29100 ${RUSTFS_ACCESS_KEY} ${RUSTFS_SECRET_KEY}
mc mirror local/ backup/rustfs/

# Hoặc backup volume trực tiếp
docker run --rm \
  -v DataLakehouse_rustfs_data:/data:ro \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/rustfs_data_$(date +%Y%m%d).tar.gz /data
```

### Lịch backup tự động (crontab)

```bash
# Chỉnh crontab
crontab -e

# Thêm:
# Backup hàng ngày lúc 2:00 sáng
0 2 * * * /home/dlh/DataLakehouse/scripts/backup.sh >> /var/log/dlh-backup.log 2>&1
```

Tạo file `scripts/backup.sh`:

```bash
#!/bin/bash
cd /home/dlh/DataLakehouse
BACKUP_DIR="backup/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# PostgreSQL
docker compose exec -T dlh-postgres pg_dumpall -U dlh_admin \
  > "$BACKUP_DIR/postgres.sql"

# Xóa backup cũ hơn 7 ngày
find backup/ -type d -mtime +7 -exec rm -rf {} +

echo "Backup completed: $BACKUP_DIR"
```

---

## 7. Cập nhật Stack

### Cập nhật image Docker

```bash
# Pull images mới
docker compose pull

# Restart với images mới
docker compose up -d --force-recreate
```

### Cập nhật cụ thể một service

```bash
# Ví dụ: chỉ cập nhật Mage
docker compose pull mage
docker compose up -d --no-deps --force-recreate mage
```

### Cập nhật code pipeline (không restart)

```bash
# Code Mage nằm trong ./mage/ được mount trực tiếp
# Chỉ cần edit file Python, Mage tự reload khi có thay đổi
```

### Rollback về phiên bản cũ

```bash
# Trong .env, đặt version cụ thể
MAGE_IMAGE_VERSION=0.9.72  # phiên bản cũ

# Restart service
docker compose up -d --no-deps --force-recreate mage
```

---

## 8. Giám sát & Khắc phục sự cố

### Lệnh giám sát thường dùng

```bash
# Trạng thái tất cả services
docker compose ps

# Sử dụng tài nguyên real-time
docker stats

# Log của tất cả services
docker compose logs -f --tail=100

# Log của service cụ thể
docker compose logs -f mage
docker compose logs -f clickhouse

# Xem lỗi trong log
docker compose logs | grep -iE "error|failed|critical"
```

### Kiểm tra kết nối

```bash
# PostgreSQL
docker compose exec dlh-postgres pg_isready -U dlh_admin

# ClickHouse HTTP
curl http://localhost:28123/ping
# Expected: Ok.

# RustFS S3 API
curl http://localhost:29100/health
# Expected: HTTP 200

# Mage API
curl http://localhost:26789/api/status
```

### Khắc phục sự cố thường gặp

#### Service không khởi động sau `up -d`

```bash
# Xem log chi tiết
docker compose logs <service_name>

# Thử khởi động ở chế độ foreground để xem lỗi
docker compose up <service_name>
```

#### PostgreSQL "connection refused"

```bash
# Kiểm tra PostgreSQL đang chạy
docker compose exec dlh-postgres pg_isready

# Xem log PostgreSQL
docker compose logs dlh-postgres | tail -50

# Reset PostgreSQL (mất dữ liệu!)
docker compose stop dlh-postgres
docker volume rm DataLakehouse_postgres_data
docker compose up -d dlh-postgres
```

#### Mage "Database connection error"

```bash
# Kiểm tra DATABASE_CONNECTION_URL
docker compose exec mage env | grep DATABASE_CONNECTION_URL

# Test kết nối PostgreSQL từ container Mage
docker compose exec mage python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://dlh_mage_user:password@dlh-postgres:5432/dlh_mage')
print('Connected!')
"
```

#### ClickHouse "Table does not exist"

```bash
# Chạy lại init scripts
docker compose exec clickhouse clickhouse-client \
  --multiquery < clickhouse/init/001_analytics_schema.sql
```

#### Không có dữ liệu trong Superset

```bash
# 1. Kiểm tra ETL có chạy chưa
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.pipeline_runs WHERE status='success'"

# 2. Chạy ETL thủ công
docker compose exec mage mage run etl_postgres_to_lakehouse

# 3. Kiểm tra lại dữ liệu
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.silver_demo"

# 4. Refresh Superset datasets
# Vào Superset → Datasets → click "Refresh" trên dataset ClickHouse
```

#### Docker network conflict

```bash
# Nếu bị lỗi "network web_network not found"
docker network create web_network

# Nếu bị lỗi "network web_network already exists"
# Không cần làm gì thêm, tiếp tục deploy
```

#### Không đủ RAM

```bash
# Xem RAM đang dùng
docker stats --no-stream

# Tắt service ít dùng
docker compose stop nocodb    # ~200MB RAM
docker compose stop superset  # ~500MB RAM

# Hoặc giới hạn RAM
# Thêm vào docker-compose.yaml:
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

---

## 9. Kiểm tra sau triển khai

Chạy các bước sau để xác nhận stack đã deploy thành công:

```bash
# 1. Kiểm tra tất cả services
docker compose ps
# Kết quả mong muốn: dlh-postgres (healthy), dlh-rustfs (healthy), dlh-clickhouse (healthy)

# 2. Kiểm tra PostgreSQL
docker compose exec dlh-postgres psql -U dlh_admin -c "\l"
# Phải thấy: datalakehouse, dlh_mage, dlh_superset, dlh_grafana, dlh_nocodb

# 3. Kiểm tra RustFS buckets
docker compose exec rustfs sh -c "
  curl -s http://localhost:9000/health && echo ' ← API OK'
  curl -s http://localhost:9001/rustfs/console/health && echo ' ← Console OK'
"

# 4. Kiểm tra ClickHouse databases
docker compose exec clickhouse clickhouse-client --query "SHOW DATABASES"
# Phải thấy: analytics

# 5. Kiểm tra ClickHouse tables
docker compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
# Phải thấy: csv_quality_metrics, csv_upload_events, pipeline_runs, silver_demo, v.v.

# 6. Kiểm tra dữ liệu mẫu PostgreSQL
docker compose exec dlh-postgres psql -U dlh_admin -d datalakehouse \
  -c "SELECT count(*) FROM public.\"Demo\""
# Phải thấy: 100000

# 7. Chạy ETL pipeline
docker compose exec mage mage run etl_postgres_to_lakehouse

# 8. Kiểm tra kết quả ETL
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.silver_demo"
# Phải > 0

# 9. Kiểm tra toàn diện bằng script
python3 scripts/verify_lakehouse_architecture.py

# 10. Truy cập UI
curl -s http://localhost:28088/health  # Superset
curl -s http://localhost:23001/api/health  # Grafana
```

### Checklist triển khai production

- [ ] Tất cả mật khẩu mặc định đã được thay đổi
- [ ] `SUPERSET_SECRET_KEY` đã được đặt giá trị ngẫu nhiên
- [ ] `DLH_BIND_IP=127.0.0.1` (hoặc IP phù hợp)
- [ ] Image versions đã được ghim cụ thể (không dùng `latest`)
- [ ] SSL/TLS đã được cấu hình cho reverse proxy
- [ ] Firewall đã được cấu hình
- [ ] Backup đã được thiết lập và test
- [ ] Monitoring alerts đã được cấu hình trong Grafana
- [ ] Test truy cập từ browser thành công
- [ ] ETL pipeline chạy thành công ít nhất một lần
- [ ] `docker compose ps` hiển thị tất cả services healthy

---

*Xem thêm: [README.md](../README.md) | [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md) | [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md)*

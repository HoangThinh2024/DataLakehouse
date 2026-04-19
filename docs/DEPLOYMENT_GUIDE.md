# 🚀 Deployment Guide – DataLakehouse

This guide covers how to deploy the DataLakehouse stack in different environments: **local development**, **LAN/team**, and **production server**.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Local Deployment (Development)](#2-local-deployment-development)
3. [LAN / Team Deployment](#3-lan--team-deployment)
4. [Production Server Deployment](#4-production-server-deployment)
5. [Security Configuration](#5-security-configuration)
6. [Data Management & Backup](#6-data-management--backup)
7. [Updating the Stack](#7-updating-the-stack)
8. [Monitoring & Troubleshooting](#8-monitoring--troubleshooting)
9. [Post-deployment Verification](#9-post-deployment-verification)

---

## 1. System Requirements

### Minimum Hardware

| Resource | Minimum | Recommended | Production |
|----------|---------|-------------|-----------|
| RAM | 4 GB | 8 GB | 16 GB+ |
| CPU | 2 cores | 4 cores | 8 cores+ |
| Disk | 10 GB | 30 GB | 100 GB+ SSD |
| Network | 10 Mbps | 100 Mbps | 1 Gbps |

### Required Software

```bash
# Check Docker
docker --version
# Required: Docker Engine 24.0+

# Check Docker Compose
docker compose version
# Required: v2.20+

# Check curl (used for testing)
curl --version
```

### Install Docker (if not already installed)

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# CentOS/RHEL
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# macOS – install Docker Desktop
# https://docs.docker.com/desktop/mac/install/
```

---

## 2. Local Deployment (Development)

Local environment for development and testing. All services are only accessible from `localhost`.

### Step 1 – Clone and configure

```bash
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
cp .env.example .env
```

### Step 2 – Minimal local configuration

Edit `.env`:

```bash
# Keep bind IP for local access
DLH_BIND_IP=127.0.0.1

# Timezone
TZ=UTC

# Database admin (can keep defaults for local)
POSTGRES_PASSWORD=localdev123

# RustFS (can keep defaults for local)
RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin

# Superset (REQUIRED: set a secret key)
SUPERSET_SECRET_KEY=local-dev-secret-key-change-for-prod
SUPERSET_ADMIN_PASSWORD=admin

# Grafana
GRAFANA_ADMIN_PASSWORD=admin

# ClickHouse (empty is OK for local)
CLICKHOUSE_PASSWORD=
```

### Step 3 – Create network and start

```bash
docker network create web_network
docker compose up -d
```

### Step 4 – Check startup

```bash
# Wait for all services to be healthy
watch docker compose ps

# Or wait manually (~2-3 minutes)
sleep 120
docker compose ps
```

**Expected state:**
```
NAME                   STATUS
dlh-postgres           healthy
dlh-rustfs             healthy
dlh-clickhouse         healthy
dlh-mage               running
dlh-superset           running
dlh-grafana            running
dlh-nocodb             running
dlh-postgres-bootstrap exited (0)   ← OK, runs once
dlh-rustfs-init        exited (0)   ← OK, runs once
```

### Step 5 – Create demo dashboard (optional)

```bash
# Run ETL and create Superset dashboard
python3 scripts/run_etl_and_dashboard.py
```

### Local access URLs

| Service | URL |
|---------|-----|
| Superset | http://localhost:28088 |
| Grafana | http://localhost:23001 |
| Mage.ai | http://localhost:26789 |
| NocoDB | http://localhost:28082 |
| RustFS Console | http://localhost:29101 |

---

## 3. LAN / Team Deployment

Allows other computers on the same local network to access the stack. No SSL required but you need a fixed IP.

### Step 1 – Find your LAN IP address

```bash
# Linux
ip addr show | grep "inet " | grep -v 127.0.0.1

# macOS
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig | findstr "IPv4"
```

Example result: `192.168.1.100`

### Step 2 – Configure .env for LAN

```bash
# Bind IP is the LAN address
DLH_BIND_IP=192.168.1.100

# PostgreSQL host (used by internal services)
POSTGRES_HOST=dlh-postgres

# NocoDB and Superset URLs
NOCODB_PUBLIC_URL=http://192.168.1.100:28082
NOCODB_BACKEND_URL=http://192.168.1.100:28082

# CORS for RustFS
RUSTFS_CORS_ALLOWED_ORIGINS=http://192.168.1.100:29100
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=http://192.168.1.100:29101

# Passwords (use stronger ones than local)
POSTGRES_PASSWORD=team-dev-password-123
SUPERSET_SECRET_KEY=$(openssl rand -hex 32)
SUPERSET_ADMIN_PASSWORD=TeamAdmin2024!
GRAFANA_ADMIN_PASSWORD=TeamGrafana2024!
```

### Step 3 – Start

```bash
docker network create web_network
docker compose up -d
```

### Step 4 – Configure firewall (if needed)

```bash
# Ubuntu/Debian with ufw
sudo ufw allow from 192.168.1.0/24 to any port 23001   # Grafana
sudo ufw allow from 192.168.1.0/24 to any port 26789   # Mage
sudo ufw allow from 192.168.1.0/24 to any port 28082   # NocoDB
sudo ufw allow from 192.168.1.0/24 to any port 28088   # Superset
sudo ufw allow from 192.168.1.0/24 to any port 29101   # RustFS Console

# CentOS/RHEL with firewalld
sudo firewall-cmd --add-port=28088/tcp --permanent
sudo firewall-cmd --reload
```

### LAN access URLs

Replace `192.168.1.100` with your actual LAN IP:

| Service | URL |
|---------|-----|
| Superset | http://192.168.1.100:28088 |
| Grafana | http://192.168.1.100:23001 |
| Mage.ai | http://192.168.1.100:26789 |
| NocoDB | http://192.168.1.100:28082 |

---

## 4. Production Server Deployment

Deploy on a VPS/cloud server with a real domain, SSL/TLS, and full security.

### Recommended production architecture

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

### Step 1 – Prepare the server

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Create a dedicated user for DataLakehouse
sudo useradd -m -s /bin/bash dlh
sudo usermod -aG docker dlh
su - dlh

# Clone the repo
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
```

### Step 2 – Configure .env for production

```bash
# Bind local only (Nginx will proxy from outside)
DLH_BIND_IP=127.0.0.1

# Server timezone
TZ=UTC

# Strong passwords for all services
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

# URLs with real domain
NOCODB_PUBLIC_URL=https://data.yourdomain.com
NOCODB_BACKEND_URL=https://data.yourdomain.com

# CORS (replace with your real domain)
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com

# Pin image versions (do not use latest in production)
POSTGRES_IMAGE_VERSION=17.2-alpine
CLICKHOUSE_IMAGE_VERSION=24.3.3.102
MAGE_IMAGE_VERSION=0.9.73
GRAFANA_IMAGE_VERSION=10.4.2
SUPERSET_IMAGE_VERSION=3.1.3
```

### Step 3 – Install Nginx with SSL (Caddy – easiest)

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Create Caddyfile
sudo tee /etc/caddy/Caddyfile << 'CADDYEOF'
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

# Object Storage Console (admin only, add authentication)
storage.yourdomain.com {
    basicauth {
        admin $2a$14$...hashed-password...
    }
    reverse_proxy localhost:29101
}

# ETL (internal only, do not expose publicly)
# mage.yourdomain.com {
#     basicauth { ... }
#     reverse_proxy localhost:26789
# }
CADDYEOF

sudo systemctl reload caddy
```

### Step 4 – Start and verify

```bash
docker network create web_network
docker compose up -d

# Check services
docker compose ps

# Check logs
docker compose logs --tail=50

# Validate the full stack
python3 scripts/verify_lakehouse_architecture.py
```

### Step 5 – Set up systemd service (auto-start)

```bash
# Create systemd service
sudo tee /etc/systemd/system/datalakehouse.service << 'SVCEOF'
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
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable datalakehouse
sudo systemctl start datalakehouse
```

---

## 5. Security Configuration

### PostgreSQL security

```bash
# Do not expose PostgreSQL to the internet (localhost only)
DLH_BIND_IP=127.0.0.1
DLH_POSTGRES_PORT=25432

# Set a strong admin password
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Each service uses a dedicated user (configured in bootstrap):
# Mage → dlh_mage_user
# Superset → dlh_superset_user
# Grafana → dlh_grafana_user
# NocoDB → dlh_nocodb_user
```

### ClickHouse security

```bash
# Set a password for production
CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)

# For production, you can comment out the ClickHouse port mappings in docker-compose.yaml
# so that Grafana/Mage connect only via the Docker internal network
```

### RustFS security

```bash
# Set strong credentials
RUSTFS_ACCESS_KEY=prod$(openssl rand -hex 8)
RUSTFS_SECRET_KEY=$(openssl rand -base64 32)

# Restrict CORS (no wildcards)
RUSTFS_CORS_ALLOWED_ORIGINS=https://storage.yourdomain.com
```

### Superset security

```bash
# The most important key
SUPERSET_SECRET_KEY=$(openssl rand -hex 32)

# Change the admin password immediately after first login
# http://yourdomain.com/users/userinfo/
```

### File permissions

```bash
# .env must not be committed and must be readable only by the owner
chmod 600 .env

# Ensure .gitignore includes .env
grep ".env" .gitignore  # must be present
```

---

## 6. Data Management & Backup

### Docker volumes structure

```bash
# List existing volumes
docker volume ls | grep DataLakehouse

# Check sizes
docker system df -v
```

**Important volumes:**

| Volume | Service | Purpose | Backup Priority |
|--------|---------|---------|-----------------|
| `postgres_data` | PostgreSQL | Mage, Superset, Grafana, NocoDB metadata | 🔴 High |
| `clickhouse_data` | ClickHouse | Analytics data, gold tables | 🔴 High |
| `rustfs_data` | RustFS | Lake storage (raw, silver, gold Parquet) | 🔴 High |
| `grafana_data` | Grafana | Dashboards (if not using PostgreSQL backend) | 🟡 Medium |
| `superset_data` | Superset | Cache, uploads | 🟢 Low |

### Backup PostgreSQL

```bash
# Full PostgreSQL backup
docker compose exec -T dlh-postgres pg_dumpall \
  -U dlh_admin \
  > backup/postgres_$(date +%Y%m%d_%H%M%S).sql

# Backup a specific database
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
# Backup the analytics database
docker compose exec clickhouse clickhouse-client \
  --query "BACKUP DATABASE analytics TO Disk('default', 'backup_$(date +%Y%m%d).zip')"

# Or export a table to a file
docker compose exec clickhouse clickhouse-client \
  --query "SELECT * FROM analytics.gold_demo_daily FORMAT Parquet" \
  > backup/gold_demo_daily_$(date +%Y%m%d).parquet
```

### Backup RustFS

```bash
# Sync all of RustFS with mc (MinIO client)
mc alias set local http://localhost:29100 ${RUSTFS_ACCESS_KEY} ${RUSTFS_SECRET_KEY}
mc mirror local/ backup/rustfs/

# Or back up the volume directly
docker run --rm \
  -v DataLakehouse_rustfs_data:/data:ro \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/rustfs_data_$(date +%Y%m%d).tar.gz /data
```

### Automated backup schedule (crontab)

```bash
# Edit crontab
crontab -e

# Add:
# Daily backup at 2:00 AM
0 2 * * * /home/dlh/DataLakehouse/scripts/backup.sh >> /var/log/dlh-backup.log 2>&1
```

Create `scripts/backup.sh`:

```bash
#!/bin/bash
cd /home/dlh/DataLakehouse
BACKUP_DIR="backup/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# PostgreSQL
docker compose exec -T dlh-postgres pg_dumpall -U dlh_admin \
  > "$BACKUP_DIR/postgres.sql"

# Delete backups older than 7 days
find backup/ -type d -mtime +7 -exec rm -rf {} +

echo "Backup completed: $BACKUP_DIR"
```

---

## 7. Updating the Stack

### Update Docker images

```bash
# Pull new images
docker compose pull

# Restart with new images
docker compose up -d --force-recreate
```

### Update a specific service

```bash
# Example: update only Mage
docker compose pull mage
docker compose up -d --no-deps --force-recreate mage
```

### Update pipeline code (no restart needed)

```bash
# Mage code is in ./mage/ which is mounted directly
# Just edit the Python files; Mage reloads on changes
```

### Rollback to an older version

```bash
# In .env, set a specific version
MAGE_IMAGE_VERSION=0.9.72  # older version

# Restart the service
docker compose up -d --no-deps --force-recreate mage
```

---

## 8. Monitoring & Troubleshooting

### Common monitoring commands

```bash
# Status of all services
docker compose ps

# Real-time resource usage
docker stats

# Logs of all services
docker compose logs -f --tail=100

# Logs of a specific service
docker compose logs -f mage
docker compose logs -f clickhouse

# View errors in logs
docker compose logs | grep -iE "error|failed|critical"
```

### Connectivity checks

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

### Common issues

#### Service not starting after `up -d`

```bash
# View detailed logs
docker compose logs <service_name>

# Start in foreground mode to see errors
docker compose up <service_name>
```

#### PostgreSQL "connection refused"

```bash
# Check PostgreSQL is running
docker compose exec dlh-postgres pg_isready

# View PostgreSQL logs
docker compose logs dlh-postgres | tail -50

# Reset PostgreSQL (data loss!)
docker compose stop dlh-postgres
docker volume rm DataLakehouse_postgres_data
docker compose up -d dlh-postgres
```

#### Mage "Database connection error"

```bash
# Check DATABASE_CONNECTION_URL
docker compose exec mage env | grep DATABASE_CONNECTION_URL

# Test PostgreSQL connection from the Mage container
docker compose exec mage python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://dlh_mage_user:password@dlh-postgres:5432/dlh_mage')
print('Connected!')
"
```

#### ClickHouse "Table does not exist"

```bash
# Re-run init scripts
docker compose exec clickhouse clickhouse-client \
  --multiquery < clickhouse/init/001_analytics_schema.sql
```

#### No data in Superset

```bash
# 1. Check if ETL has run
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.pipeline_runs WHERE status='success'"

# 2. Run ETL manually
docker compose exec mage mage run etl_postgres_to_lakehouse

# 3. Re-check data
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.silver_demo"

# 4. Refresh Superset datasets
# Go to Superset → Datasets → click "Refresh" on the ClickHouse dataset
```

#### Docker network conflict

```bash
# If you get "network web_network not found"
docker network create web_network

# If you get "network web_network already exists"
# Nothing to do, proceed with deployment
```

#### Not enough RAM

```bash
# View current RAM usage
docker stats --no-stream

# Stop less-used services
docker compose stop nocodb    # ~200 MB RAM
docker compose stop superset  # ~500 MB RAM

# Or limit RAM in docker-compose.yaml:
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

---

## 9. Post-deployment Verification

Run these steps to confirm the stack is deployed correctly:

```bash
# 1. Check all services
docker compose ps
# Expected: dlh-postgres (healthy), dlh-rustfs (healthy), dlh-clickhouse (healthy)

# 2. Check PostgreSQL
docker compose exec dlh-postgres psql -U dlh_admin -c "\l"
# Should see: datalakehouse, dlh_mage, dlh_superset, dlh_grafana, dlh_nocodb

# 3. Check RustFS buckets
docker compose exec rustfs sh -c "
  curl -s http://localhost:9000/health && echo ' ← API OK'
  curl -s http://localhost:9001/rustfs/console/health && echo ' ← Console OK'
"

# 4. Check ClickHouse databases
docker compose exec clickhouse clickhouse-client --query "SHOW DATABASES"
# Should see: analytics

# 5. Check ClickHouse tables
docker compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
# Should see: csv_quality_metrics, csv_upload_events, pipeline_runs, silver_demo, etc.

# 6. Check sample PostgreSQL data
docker compose exec dlh-postgres psql -U dlh_admin -d datalakehouse \
  -c "SELECT count(*) FROM public.\"Demo\""
# Should see: 100000

# 7. Run the ETL pipeline
docker compose exec mage mage run etl_postgres_to_lakehouse

# 8. Check ETL results
docker compose exec clickhouse clickhouse-client \
  --query "SELECT count() FROM analytics.silver_demo"
# Should be > 0

# 9. Full validation with script
python3 scripts/verify_lakehouse_architecture.py

# 10. Access UIs
curl -s http://localhost:28088/health  # Superset
curl -s http://localhost:23001/api/health  # Grafana
```

### Production deployment checklist

- [ ] All default passwords have been changed
- [ ] `SUPERSET_SECRET_KEY` has been set to a random value
- [ ] `DLH_BIND_IP=127.0.0.1` (or appropriate IP)
- [ ] Image versions have been pinned (no `latest`)
- [ ] SSL/TLS configured for the reverse proxy
- [ ] Firewall configured
- [ ] Backup set up and tested
- [ ] Monitoring alerts configured in Grafana
- [ ] Browser access test passed
- [ ] ETL pipeline ran successfully at least once
- [ ] `docker compose ps` shows all services healthy

---

*See also: [README.md](../README.md) | [VARIABLES_REFERENCE.md](VARIABLES_REFERENCE.md) | [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md)*

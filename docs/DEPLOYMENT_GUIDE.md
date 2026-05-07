# Deployment Guide

Step-by-step guide for deploying and operating the DataLakehouse stack.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-Time Bootstrap](#2-first-time-bootstrap)
3. [Manual Setup (without setup.sh)](#3-manual-setup-without-setupsh)
4. [Day-2 Operations](#4-day-2-operations)
5. [Firewall and LAN Access](#5-firewall-and-lan-access)
6. [Reverse Proxy Setup](#6-reverse-proxy-setup)
7. [ETL and Dashboard Automation](#7-etl-and-dashboard-automation)
8. [Validation](#8-validation)
9. [Common Recovery Procedures](#9-common-recovery-procedures)
10. [Production Notes](#10-production-notes)

---

## 1. Prerequisites

### Required tools

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Docker Engine | 24+ | https://docs.docker.com/engine/install/ |
| Docker Compose plugin | v2 | Bundled with Docker Desktop or `docker-compose-plugin` package |
| `uv` | Latest | `curl -LsSf https://astral.sh/uv/install.sh | sh` |

### Hardware recommendations

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 8 GB+ |
| CPU | 2 cores | 4 cores+ |
| Disk | 20 GB | 50 GB+ |

### Supported host OSes

- Ubuntu 22.04 / 24.04
- Debian 12
- macOS (with Docker Desktop)
- Windows WSL2 (with Docker Desktop)

### Quick checks

```bash
docker --version
docker compose version
uv --version
```

---

## 2. First-Time Bootstrap

### Step 1 – Clone the repository

```bash
git clone https://github.com/vuhuudo/DataLakehouse.git
cd DataLakehouse
uv sync --all-groups
```

### Step 2 – Run guided setup

```bash
bash scripts/setup.sh
```

`setup.sh` is a smart, interactive script that walks through:

1.  **Pre-flight Checks**: Verifies `docker` and `uv` are installed.
2.  **Bind IP settings** — local-only (`127.0.0.1`) vs LAN (`0.0.0.0`).
3.  **Port Assignments** — Checks for port conflicts on the host and suggests
    free ports if the defaults are taken.
4.  **Credentials** — for PostgreSQL, ClickHouse, Redis, Superset, etc.
5.  **Image versions** — override `latest` tags with pinned versions.
6.  Writes a complete, cross-platform-safe `.env` file (handles WSL/Windows CRLF/BOM issues).
7.  Creates `web_network` Docker network.
8.  Runs `docker compose up -d`.
9.  Optionally runs the ETL pipeline and provisions Superset dashboards.

### Step 3 – Verify health

```bash
# Run the primary diagnostic tool first
bash scripts/stackctl.sh diagnose

# If diagnose reports no errors, run a deeper health check
bash scripts/stackctl.sh health
```

All services should reach `healthy` status within 2–3 minutes.
If any service fails, `diagnose` will often point to the root cause in the logs.

---

## 3. Manual Setup (without setup.sh)

If you prefer to configure manually:

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit .env — replace all change-* and replace-* values
#    On Windows/WSL, ensure you save with Unix (LF) line endings and UTF-8 without BOM.
nano .env

# 3. Create external Docker network
docker network create web_network

# 4. Start stack
docker compose up -d

# 5. Check health
bash scripts/stackctl.sh diagnose
```

---

## 4. Day-2 Operations

All lifecycle operations are managed through `scripts/stackctl.sh`.

### Core commands

```bash
bash scripts/stackctl.sh up                    # start all services
bash scripts/stackctl.sh down                  # stop all services
bash scripts/stackctl.sh redeploy              # pull images + recreate containers
bash scripts/stackctl.sh redeploy --safe       # backup volumes before recreating
bash scripts/stackctl.sh redeploy --with-etl   # redeploy + run ETL
```

### Health, logs, and diagnostics

```bash
bash scripts/stackctl.sh diagnose              # check port conflicts and recent errors
bash scripts/stackctl.sh status                # container state (up/down/restarting)
bash scripts/stackctl.sh health                # deep health checks
bash scripts/stackctl.sh logs all              # tail all service logs
bash scripts/stackctl.sh logs dlh-mage         # single service logs
bash scripts/stackctl.sh inspect dlh-postgres  # container config/env
```

### Environment management

```bash
bash scripts/stackctl.sh check-env      # print current .env values
bash scripts/stackctl.sh validate-env   # check for port conflicts and blank required fields
bash scripts/stackctl.sh sync-env       # interactive .env update + write back
```

### Reset commands

```bash
# Soft reset: remove containers, keep data volumes
bash scripts/stackctl.sh reset

# Hard reset: remove containers AND volumes (all data deleted)
bash scripts/stackctl.sh reset --hard
```

---

## 5. Firewall and LAN Access

Configure Docker-aware UFW firewall rules. This script now sources the
centralized `lib_env.sh` for consistent environment loading.

```bash
bash scripts/setup_ufw_docker.sh
```

Key behaviors:
- Uses `ufw-docker` workflow for Docker-published ports.
- **Does not modify SSH rules** — safe to run on remote servers.
- Adds explicit comments to every managed rule for auditing.
- Supports targeted cleanup (`--remove`, `--down`).

### Common scenarios

```bash
# Apply rules for current .env/CIDR
bash scripts/setup_ufw_docker.sh

# Remove managed rules without stopping services
bash scripts/setup_ufw_docker.sh --remove

# Remove managed rules and stop the stack
bash scripts/setup_ufw_docker.sh --down
```

### Recommended `.env` for split-access deployment

```ini
# UI/app ports: local only (behind reverse proxy)
DLH_APP_BIND_IP=127.0.0.1

# Data/DB ports: accessible from LAN for direct client connections
DLH_DATA_BIND_IP=0.0.0.0
UFW_ALLOW_DATA_PORTS=true
DLH_LAN_CIDR=192.168.1.0/24
```

---

## 6. Reverse Proxy Setup

The optional Nginx Proxy Manager (NPM) service is included in `docker-compose.yaml`.
It is already defined — simply ensure it is uncommented and configure proxy hosts via
the NPM admin UI at `http://localhost:28081`.

### Connecting NPM to the stack

If NPM is deployed in a **separate Docker project on the same host**:

1. Attach the NPM container to `web_network`.
2. Use DataLakehouse service names as upstream targets:

| Service | Internal upstream |
|---------|-------------------|
| Mage | `dlh-mage:6789` |
| Superset | `dlh-superset:8088` |
| Grafana | `dlh-grafana:3000` |
| Authentik | `dlh-authentik-server:9000` |
| RustFS Console | `dlh-rustfs:9001` |
| CloudBeaver | `dlh-cloudbeaver:8978` |

### Redis backend setup for Authentik

Authentik uses Redis for worker queue and session cache. Ensure:

```ini
# .env
REDIS_HOST=dlh-redis
REDIS_PASSWORD=<your-password>
REDIS_AUTHENTIK_DB=1
```

These values are automatically picked up by `docker-compose.yaml`.

---

## 7. ETL and Dashboard Automation

### Run ETL interactively

```bash
uv run python scripts/run_etl_and_dashboard.py
```

### Run ETL non-interactively (CI-friendly)

```bash
# Full ETL + dashboard provisioning
uv run python scripts/run_etl_and_dashboard.py --auto

# Force a specific source table
uv run python scripts/run_etl_and_dashboard.py --auto --table sales_orders

# Create sample data first, then run ETL + dashboard
uv run python scripts/run_etl_and_dashboard.py --auto --create-sample-table --table sales_orders

# ETL only (skip dashboard creation)
uv run python scripts/run_etl_and_dashboard.py --auto --skip-dashboard
```

### Include ETL in lifecycle redeploy

```bash
bash scripts/stackctl.sh redeploy --with-etl
```

### Enable realtime processing for file uploads

The watcher script now includes **lock file protection** to prevent race
conditions from multiple simultaneous file uploads.

```bash
# Start in foreground
bash scripts/realtime_watcher.sh

# Or as background daemon
nohup bash scripts/realtime_watcher.sh >> /var/log/dlh-watcher.log 2>&1 &
```

---

## 8. Validation

### Full architecture check

The verification script is now significantly faster and supports JSON output.

```bash
# Human-readable output
bash scripts/stackctl.sh check-system

# JSON output for automation
uv run python scripts/verify_lakehouse_architecture.py --json
```

### Quick connectivity checks

```bash
curl http://localhost:28123/ping          # ClickHouse → expected: Ok.
curl http://localhost:29100/health        # RustFS S3 API
curl http://localhost:29101/rustfs/console/health   # RustFS Console
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping   # Redis → PONG
```

---

## 9. Common Recovery Procedures

See [OPERATIONS.md – Common Recovery Procedures](OPERATIONS.md#11-common-recovery-procedures)
for the full list. Quick reference below.

### Service unhealthy

```bash
bash scripts/stackctl.sh diagnose
bash scripts/stackctl.sh logs <service>
docker compose up -d <service>       # restart a single service
```

### Port conflict

```bash
bash scripts/stackctl.sh diagnose
bash scripts/stackctl.sh sync-env
bash scripts/stackctl.sh redeploy
```

### Full rebuild

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

### WSL / .env Encoding Errors

This issue is **automatically resolved** by the refactored script layer.

All operational scripts (`setup.sh`, `stackctl.sh`, etc.) use a shared
environment library (`scripts/lib_env.sh`) that safely reads `.env` files. It
automatically detects and sanitizes UTF-8 BOM and CRLF line endings common in
Windows environments.

**No manual steps are required.**

---

## 10. Production Notes

Before exposing to production traffic:

- [ ] **Pin all image tags** in `.env` (no `latest`).
- [ ] **Rotate all default passwords** — every `change-*` and `replace-*` value.
- [ ] **Enable TLS** via Nginx Proxy Manager with valid certificates.
- [ ] **Restrict bind IPs** — `DLH_APP_BIND_IP=127.0.0.1` (expose only via proxy).
- [ ] **Configure firewall** — run `setup_ufw_docker.sh` with your trusted CIDR.
- [ ] **Set up automated backups** — cron job for `maintenance_tasks.py`.
- [ ] **Test restore procedure** — verify ClickHouse backup in RustFS + practice RESTORE SQL.
- [ ] **Validate stack** — `bash scripts/stackctl.sh check-system` returns no errors.
- [ ] **Back up Docker volumes** — PostgreSQL, ClickHouse, RustFS, Redis.

Pinned image versions (recommended, from `.env.example`):

```ini
POSTGRES_IMAGE_VERSION=17-alpine
CLICKHOUSE_IMAGE_VERSION=25.4-alpine
MAGE_IMAGE_VERSION=0.9.76
SUPERSET_IMAGE_VERSION=4.1.2
GRAFANA_IMAGE_VERSION=12.0.0
REDIS_STACK_IMAGE_VERSION=7.4.2-v3
AUTHENTIK_IMAGE_VERSION=2026.2.1
MINIO_MC_IMAGE_VERSION=RELEASE.2025-04-16T18-13-26Z
```

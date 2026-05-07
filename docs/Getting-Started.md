# Getting Started

This page walks you through installing and running the DataLakehouse stack for the first time.

---

## Prerequisites

### Required tools

| Tool | Minimum version | Install |
|------|----------------|---------|
| Docker Engine | 24+ | https://docs.docker.com/engine/install/ |
| Docker Compose plugin | v2 | Bundled with Docker Desktop or `docker-compose-plugin` package |
| `uv` | Latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Hardware recommendations

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 8 GB+ |
| CPU | 2 cores | 4 cores+ |
| Disk | 20 GB | 50 GB+ |

### Supported host operating systems

- Ubuntu 22.04 / 24.04
- Debian 12
- macOS (with Docker Desktop)
- Windows WSL2 (with Docker Desktop)

### Quick check

```bash
docker --version
docker compose version
uv --version
```

---

## Option A — Guided Setup (Recommended)

### Step 1 – Clone and install host dependencies

```bash
git clone https://github.com/vuhuudo/DataLakehouse.git
cd DataLakehouse
uv sync --all-groups
```

### Step 2 – Run the interactive setup script

```bash
bash scripts/setup.sh
```

`setup.sh` will:
1. Prompt for all configuration values (bind IPs, ports, passwords).
2. Write a complete `.env` file.
3. Create the `web_network` Docker network.
4. Start all services with `docker compose up -d`.
5. Optionally run the ETL pipeline and provision Superset dashboards.

### Step 3 – Verify stack health

```bash
bash scripts/stackctl.sh health
```

All services should report healthy within **2–3 minutes** of startup.

### Step 4 (Optional) – Load sample data and run ETL

```bash
# Interactive mode
uv run python scripts/run_etl_and_dashboard.py

# Non-interactive / CI mode
uv run python scripts/run_etl_and_dashboard.py --auto
```

---

## Option B — Manual Setup

If you prefer full control over each step:

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Edit .env — replace every change-* and replace-* placeholder value
nano .env

# 3. Create the external Docker network
docker network create web_network

# 4. Start the stack
docker compose up -d

# 5. Check health
bash scripts/stackctl.sh health
```

---

## Accessing the Services

Once the stack is up, open these URLs in your browser:

| Service | URL |
|---------|-----|
| Mage (ETL UI) | http://localhost:26789 |
| Superset (Dashboards) | http://localhost:28088 |
| Grafana (Monitoring) | http://localhost:23001 |
| RustFS Console (Object store) | http://localhost:29101 |
| Authentik (Identity) | http://localhost:29090 |
| CloudBeaver (SQL IDE) | http://localhost:28978 |
| Dockhand (Docker UI) | http://localhost:23000 |
| Redis Insight | http://localhost:25540 |

Default credentials for each service are set in `.env`. See the [Configuration](Configuration) page.

---

## Running the ETL Pipelines

After the stack is healthy, trigger ETL via any of the following methods:

### Via the setup/automation script

```bash
uv run python scripts/run_etl_and_dashboard.py --auto
```

### Via stackctl

```bash
bash scripts/stackctl.sh redeploy --with-etl
```

### Via Mage UI

1. Open http://localhost:26789
2. Go to **Pipelines**
3. Select `etl_postgres_to_lakehouse`
4. Click **Run Pipeline Now**

### Via CLI inside the Mage container

```bash
docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
```

---

## Verifying the Deployment

Run the end-to-end architecture validation script:

```bash
bash scripts/stackctl.sh check-system
# or directly:
uv run python scripts/verify_lakehouse_architecture.py
```

Exit code `0` means all services are connected and data is flowing correctly.

### Quick connectivity checks

```bash
curl http://localhost:28123/ping                       # ClickHouse → expected: Ok.
curl http://localhost:29100/health                     # RustFS S3 API
docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping  # Redis → PONG
```

---

## What Happens During the ETL Run?

1. **Extract** — `extract_postgres.py` pulls rows from the PostgreSQL source table.
2. **Bronze** — `bronze_to_rustfs.py` saves raw Parquet to `s3://bronze/`.
3. **Silver** — `transform_silver.py` cleans and validates the data; `silver_to_rustfs.py` saves to `s3://silver/`.
4. **Gold** — `transform_gold.py` aggregates; `gold_to_rustfs.py` saves to `s3://gold/`.
5. **Load** — `load_to_clickhouse.py` reads Silver + Gold from RustFS and inserts into ClickHouse.
6. Superset dashboards are now populated and queryable.

---

## Next Steps

- Understand the full stack: [Architecture](Architecture)
- Manage day-to-day operations: [Operations](Operations)
- Add your own data sources: [Developer Guide](Developer-Guide)
- Prepare for production: [Security](Security)

---

> See [docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) for the complete deployment reference.

# Configuration

All configuration is managed through a single `.env` file at the project root.
No secrets are stored in `docker-compose.yaml`.

---

## Setup

### Initial configuration

```bash
# Copy the template
cp .env.example .env

# Edit with your values
nano .env
```

Alternatively, the interactive setup script prompts for every value and writes `.env` automatically:

```bash
bash scripts/setup.sh
```

### Validate and sync

```bash
# Check for port conflicts and missing required fields
bash scripts/stackctl.sh validate-env

# Interactive update + write back to .env
bash scripts/stackctl.sh sync-env

# Print current values
bash scripts/stackctl.sh check-env
```

After changing `.env`, apply with:

```bash
bash scripts/stackctl.sh redeploy
```

---

## Key Variable Groups

### Network bind IPs

| Variable | Default | Description |
|----------|---------|-------------|
| `DLH_APP_BIND_IP` | `127.0.0.1` | Bind IP for UI/app ports (Mage, Superset, Grafana, etc.) |
| `DLH_DATA_BIND_IP` | `127.0.0.1` | Bind IP for data/DB ports (PostgreSQL, ClickHouse, RustFS S3) |
| `DLH_BIND_IP` | `127.0.0.1` | Fallback bind IP if app/data-specific IPs are not set |
| `DLH_LAN_CIDR` | `192.168.1.0/24` | LAN subnet for firewall rules |

> Set `DLH_DATA_BIND_IP=0.0.0.0` to allow LAN clients to connect directly to databases.

### PostgreSQL

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER` | Admin user |
| `POSTGRES_PASSWORD` | Admin password |
| `POSTGRES_DB` | Main source/operational database |
| `POSTGRES_HOST` | Service hostname (`dlh-postgres`) |
| `SOURCE_TABLE` | Table name to extract in the primary ETL pipeline |
| `SOURCE_TABLE_CANDIDATES` | Comma-separated fallback table names |
| `SOURCE_SCHEMA` | Schema containing the source table (default: `public`) |

### ClickHouse

| Variable | Description |
|----------|-------------|
| `CLICKHOUSE_USER` | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | ClickHouse password |
| `CLICKHOUSE_DB` | Analytics database name (`analytics`) |
| `CLICKHOUSE_HOST` | Service hostname (`dlh-clickhouse`) |

### RustFS (S3-compatible object store)

| Variable | Description |
|----------|-------------|
| `RUSTFS_ACCESS_KEY` | S3 access key |
| `RUSTFS_SECRET_KEY` | S3 secret key |
| `RUSTFS_ENDPOINT` | S3 API endpoint (e.g. `http://dlh-rustfs:9000`) |
| `RUSTFS_BRONZE_BUCKET` | Bronze bucket name (default: `bronze`) |
| `RUSTFS_SILVER_BUCKET` | Silver bucket name (default: `silver`) |
| `RUSTFS_GOLD_BUCKET` | Gold bucket name (default: `gold`) |

### Redis

| Variable | Description |
|----------|-------------|
| `REDIS_PASSWORD` | Redis AUTH password |
| `REDIS_HOST` | Service hostname (`dlh-redis`) |
| `REDIS_PORT` | Redis port (default: `6379`) |
| `REDIS_AUTHENTIK_DB` | Redis DB index for Authentik (default: `1`) |
| `SUPERSET_REDIS_CACHE_DB` | Redis DB index for Superset cache (default: `2`) |
| `SUPERSET_REDIS_RESULTS_DB` | Redis DB index for Superset results (default: `3`) |

### Mage

| Variable | Description |
|----------|-------------|
| `MAGE_DEFAULT_OWNER_USERNAME` | Mage admin username |
| `MAGE_DEFAULT_OWNER_PASSWORD` | Mage admin password |
| `MAGE_DB_NAME` | PostgreSQL database for Mage metadata |

### Superset

| Variable | Description |
|----------|-------------|
| `SUPERSET_ADMIN_USER` | Superset admin username |
| `SUPERSET_ADMIN_PASSWORD` | Superset admin password |
| `SUPERSET_SECRET_KEY` | Flask secret key (set a long random string) |

### Grafana

| Variable | Description |
|----------|-------------|
| `GRAFANA_ADMIN_USER` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password |

### Authentik

| Variable | Description |
|----------|-------------|
| `AUTHENTIK_BOOTSTRAP_EMAIL` | Initial admin email |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Initial admin password |
| `AUTHENTIK_SECRET_KEY` | Authentik signing secret (set a long random string) |

### Image versions

Pin all images to specific tags for reproducible deployments:

| Variable | Recommended value |
|----------|------------------|
| `POSTGRES_IMAGE_VERSION` | `17-alpine` |
| `CLICKHOUSE_IMAGE_VERSION` | `25.4-alpine` |
| `MAGE_IMAGE_VERSION` | `0.9.76` |
| `SUPERSET_IMAGE_VERSION` | `4.1.2` |
| `GRAFANA_IMAGE_VERSION` | `12.0.0` |
| `REDIS_STACK_IMAGE_VERSION` | `7.4.2-v3` |
| `AUTHENTIK_IMAGE_VERSION` | `2026.2.1` |
| `MINIO_MC_IMAGE_VERSION` | `RELEASE.2025-04-16T18-13-26Z` |

### Service ports (default)

All ports are in the `2xxxx` range to avoid conflicts with common system services.

| Variable | Default | Service |
|----------|---------|---------|
| `DLH_POSTGRES_PORT` | `25432` | PostgreSQL |
| `DLH_CLICKHOUSE_HTTP_PORT` | `28123` | ClickHouse HTTP API |
| `DLH_CLICKHOUSE_TCP_PORT` | `29000` | ClickHouse native TCP |
| `DLH_RUSTFS_API_PORT` | `29100` | RustFS S3 API |
| `DLH_RUSTFS_GUI_PORT` | `29101` | RustFS Console |
| `DLH_MAGE_PORT` | `26789` | Mage |
| `DLH_SUPERSET_PORT` | `28088` | Superset |
| `DLH_GRAFANA_PORT` | `23001` | Grafana |
| `DLH_AUTHENTIK_PORT` | `29090` | Authentik |
| `DLH_CLOUDBEAVER_PORT` | `28978` | CloudBeaver |
| `DLH_REDIS_PORT` | `26379` | Redis |
| `DLH_REDIS_GUI_PORT` | `25540` | Redis Insight |
| `DLH_DOCKHAND_PORT` | `23000` | Dockhand |
| `DLH_NPM_ADMIN_PORT` | `28081` | Nginx Proxy Manager admin |

### Firewall

| Variable | Description |
|----------|-------------|
| `UFW_ALLOW_DATA_PORTS` | `true` to open data ports (PostgreSQL, ClickHouse, RustFS) to `DLH_LAN_CIDR` |

---

## Split-Access Example

For a typical server where UIs are behind a reverse proxy but databases are accessible from your LAN:

```ini
# UI ports — local only, exposed via Nginx Proxy Manager
DLH_APP_BIND_IP=127.0.0.1

# Data/DB ports — accessible from LAN for direct client tools
DLH_DATA_BIND_IP=0.0.0.0
UFW_ALLOW_DATA_PORTS=true
DLH_LAN_CIDR=192.168.1.0/24
```

---

## Mage I/O Profiles (`mage/io_config.yaml`)

Mage uses named connection profiles. Three profiles are configured:

| Profile | Database | Used by |
|---------|----------|---------|
| `default` | `MAGE_DB_NAME` | Mage internal metadata |
| `source_db` | `POSTGRES_DB` | ETL extractor blocks |
| `custom_db` | `CUSTOM_DB_NAME` | Optional workspace database |
| `clickhouse` | `CLICKHOUSE_DB` | Data loader/exporter blocks |

All credentials are resolved from environment variables at runtime using Mage's `{{ env_var('VAR_NAME') }}` syntax.

---

> See [docs/VARIABLES_REFERENCE.md](../docs/VARIABLES_REFERENCE.md) for the complete variable reference with descriptions and example values.

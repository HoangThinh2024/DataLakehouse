# Variables Reference

Complete reference for all environment variables used by the DataLakehouse stack.

Sources of truth:

| File | Purpose |
|------|---------|
| `.env.example` | Default values template — copy to `.env` and customise |
| `.env` | Active deployment configuration (not committed to git) |
| `scripts/setup.sh` | Generates `.env` interactively on first setup |
| `scripts/stackctl.sh sync-env` | Updates individual `.env` values without full re-setup |

Quick validation:

```bash
bash scripts/stackctl.sh validate-env
```

## 1. Global

| Variable | Description | Example |
|---|---|---|
| `TZ` | Container timezone | `Asia/Ho_Chi_Minh` |
| `DLH_BIND_IP` | Host bind IP for published ports | `127.0.0.1` |
| `DLH_APP_BIND_IP` | Host bind IP for UI/app ports (Mage, Superset, Grafana, RustFS console) | `127.0.0.1` |
| `DLH_DATA_BIND_IP` | Host bind IP for data/database ports (PostgreSQL, ClickHouse, RustFS API) | `0.0.0.0` |
| `DLH_LAN_CIDR` | Trusted LAN range for firewall rules | `192.168.1.0/24` |
| `UFW_ALLOW_DATA_PORTS` | Whether data ports are opened to LAN by firewall script | `false` |

## 2. Docker Image Tags

| Variable | Description | Example |
|---|---|---|
| `POSTGRES_IMAGE_VERSION` | PostgreSQL image tag | `17-alpine` |
| `RUSTFS_IMAGE_VERSION` | RustFS image tag | `latest` |
| `MINIO_MC_IMAGE_VERSION` | MinIO mc client tag for rustfs-init | `latest` |
| `CLICKHOUSE_IMAGE_VERSION` | ClickHouse image tag | `latest` |
| `MAGE_IMAGE_VERSION` | Mage image tag | `latest` |
| `SUPERSET_IMAGE_VERSION` | Superset image tag | `latest` |
| `GRAFANA_IMAGE_VERSION` | Grafana image tag | `latest` |
| `REDIS_STACK_IMAGE_VERSION` | Redis Stack image tag | `7.4.2-v3` |
| `AUTHENTIK_IMAGE_VERSION` | Authentik image tag | `2026.2.1` |

## 3. Core PostgreSQL

| Variable | Description | Example |
|---|---|---|
| `POSTGRES_DB` | Main admin database | `datalakehouse` |
| `POSTGRES_USER` | Main admin user | `dlh_admin` |
| `POSTGRES_PASSWORD` | Main admin password | `change-this-admin-password` |
| `POSTGRES_HOST` | Internal hostname used by services | `dlh-postgres` |
| `DLH_POSTGRES_PORT` | Host port mapped to container `5432` | `25432` |

## 4. Custom Workspace

| Variable | Description | Example |
|---|---|---|
| `CUSTOM_DB_NAME` | Optional isolated business workspace DB | `dlh_custom` |
| `CUSTOM_DB_USER` | Workspace DB user | `dlh_custom_user` |
| `CUSTOM_DB_PASSWORD` | Workspace DB password | `change-this-custom-password` |
| `CUSTOM_SCHEMA` | Workspace schema | `custom_schema` |

## 5. RustFS

| Variable | Description | Example |
|---|---|---|
| `RUSTFS_ACCESS_KEY` | RustFS access key | `rustfsadmin` |
| `RUSTFS_SECRET_KEY` | RustFS secret key | `rustfsadmin` |
| `DLH_RUSTFS_API_PORT` | Host port mapped to RustFS S3 API | `29100` |
| `DLH_RUSTFS_CONSOLE_PORT` | Host port mapped to RustFS console | `29101` |
| `RUSTFS_CORS_ALLOWED_ORIGINS` | Allowed origins for RustFS API | `http://127.0.0.1:29100` |
| `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS` | Allowed origins for RustFS console | `http://127.0.0.1:29101` |
| `RUSTFS_BUCKET` | Generic app bucket | `general` |
| `RUSTFS_BRONZE_BUCKET` | Bronze layer bucket | `bronze` |
| `RUSTFS_SILVER_BUCKET` | Silver layer bucket | `silver` |
| `RUSTFS_GOLD_BUCKET` | Gold layer bucket | `gold` |

## 6. ClickHouse

| Variable | Description | Example |
|---|---|---|
| `CLICKHOUSE_DB` | Analytics database name | `analytics` |
| `CLICKHOUSE_USER` | ClickHouse user | `default` |
| `CLICKHOUSE_PASSWORD` | ClickHouse password | `` |
| `DLH_CLICKHOUSE_HTTP_PORT` | Host HTTP port (`8123` in container) | `28123` |
| `DLH_CLICKHOUSE_TCP_PORT` | Host native TCP port (`9000` in container) | `29000` |

## 7. Mage

| Variable | Description | Example |
|---|---|---|
| `DLH_MAGE_PORT` | Host port for Mage UI/API | `26789` |
| `MAGE_DB_NAME` | Mage metadata database | `dlh_mage` |
| `MAGE_DB_USER` | Mage metadata user | `dlh_mage_user` |
| `MAGE_DB_PASSWORD` | Mage metadata password | `change-this-mage-password` |
| `MAGE_DEFAULT_OWNER_EMAIL` | Default Mage owner email (created if no owner exists) | `admin@admin.com` |
| `MAGE_DEFAULT_OWNER_USERNAME` | Default Mage owner username | `admin` |
| `MAGE_DEFAULT_OWNER_PASSWORD` | Default Mage owner password | `admin` |
| `SOURCE_DB_NAME` | Source DB used by ETL extractors | `dlh_custom` |
| `SOURCE_DB_USER` | Source DB user for ETL | `dlh_custom_user` |
| `SOURCE_DB_PASSWORD` | Source DB password for ETL | `...` |
| `SOURCE_SCHEMA` | Primary source schema | `custom_schema` |
| `SOURCE_SCHEMA_FALLBACKS` | Comma-separated fallback schemas | `public` |
| `SOURCE_TABLE` | Optional exact table for ETL | `` |
| `SOURCE_TABLE_CANDIDATES` | Candidate table names for discovery | `Demo,test_projects,sales_orders` |
| `CSV_UPLOAD_BUCKET` | CSV upload source bucket | `bronze` |
| `CSV_UPLOAD_PREFIX` | Prefix for uploaded CSV files | `csv_upload/` |
| `CSV_UPLOAD_ALLOW_ANYWHERE` | Allow scanning arbitrary paths | `true` |
| `CSV_UPLOAD_SEPARATOR` | CSV delimiter | `,` |
| `CSV_UPLOAD_ENCODING` | CSV encoding | `utf-8` |
| `CSV_UPLOAD_SCAN_LIMIT` | Max files scanned per run | `200` |

## 8. Redis

| Variable | Description | Example |
|---|---|---|
| `REDIS_HOST` | Internal Redis hostname used by services | `dlh-redis` |
| `REDIS_BIND_IP` | Host bind IP for published Redis port (set `127.0.0.1` for local-only) | `127.0.0.1` |
| `DLH_REDIS_PORT` | Host port mapped to Redis `6379` | `26379` |
| `REDIS_PASSWORD` | Shared Redis password | `change-this-redis-password` |
| `REDIS_PROTECTED_MODE` | Redis protected mode flag | `yes` |
| `REDIS_APPENDONLY` | Enable append-only persistence | `yes` |
| `REDIS_MAXMEMORY` | Memory ceiling for Redis container | `512mb` |
| `REDIS_MAXMEMORY_POLICY` | Eviction policy when memory is full | `allkeys-lru` |
| `REDIS_VM_OVERCOMMIT_MEMORY` | Container sysctl value for `vm.overcommit_memory` | `1` |
| `REDIS_STACK_IMAGE_VERSION` | Redis Stack image tag | `7.4.2-v3` |
| `DLH_REDIS_GUI_PORT` | Host port for Redis Insight UI (built into `redis/redis-stack`, container port 8001) | `25540` |
| `REDIS_AUTHENTIK_DB` | Redis logical DB index used by Authentik | `1` |
| `SUPERSET_REDIS_CACHE_DB` | Redis logical DB index used by Superset cache | `2` |
| `SUPERSET_REDIS_RESULTS_DB` | Redis logical DB index used by Superset SQL Lab results | `3` |

## 9. CloudBeaver

| Variable | Description | Example |
|---|---|---|
| `DLH_CLOUDBEAVER_PORT` | Host port for CloudBeaver web SQL IDE | `28978` |

## 10. Dockhand

| Variable | Description | Example |
|---|---|---|
| `DLH_DOCKHAND_PORT` | Host port for Dockhand (Docker Management UI) | `23000` |

## 11. Superset

| Variable | Description | Example |
|---|---|---|
| `DLH_SUPERSET_PORT` | Host port for Superset | `28088` |
| `SUPERSET_SECRET_KEY` | Flask/Superset secret key | `replace-this-secret` |
| `SUPERSET_DB_NAME` | Superset metadata DB | `dlh_superset` |
| `SUPERSET_DB_USER` | Superset metadata user | `dlh_superset_user` |
| `SUPERSET_DB_PASSWORD` | Superset metadata password | `change-this-superset-db-password` |
| `SUPERSET_ADMIN_USER` | Superset admin username | `admin` |
| `SUPERSET_ADMIN_PASSWORD` | Superset admin password | `admin` |
| `SUPERSET_ADMIN_EMAIL` | Superset admin email | `admin@superset.local` |
| `SUPERSET_PREFERRED_URL_SCHEME` | URL scheme behind proxy or direct | `http` |
| `SUPERSET_PIP_REQUIREMENTS` | Extra Python packages installed at Superset startup (must be quoted if multiple packages are listed) | `"psycopg2-binary==2.9.9 clickhouse-connect==0.8.3"` |

## 11. Authentik

| Variable | Description | Example |
|---|---|---|
| `DLH_AUTHENTIK_PORT` | Host port for Authentik web UI/API | `29090` |
| `AUTHENTIK_SECRET_KEY` | Authentik cryptographic secret key | `replace-this-with-a-long-random-secret` |
| `AUTHENTIK_DB_NAME` | Authentik metadata DB name | `dlh_authentik` |
| `AUTHENTIK_DB_USER` | Authentik metadata DB user | `dlh_authentik_user` |
| `AUTHENTIK_DB_PASSWORD` | Authentik metadata DB password | `change-this-authentik-db-password` |
| `AUTHENTIK_BOOTSTRAP_EMAIL` | Initial admin email for first bootstrap | `admin@authentik.local` |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Initial admin password for first bootstrap | `admin` |
| `AUTHENTIK_BOOTSTRAP_TOKEN` | Optional first-run bootstrap token | `` |

## 12. Grafana

| Variable | Description | Example |
|---|---|---|
| `DLH_GRAFANA_PORT` | Host port for Grafana | `23001` |
| `GRAFANA_DB_NAME` | Grafana metadata DB | `dlh_grafana` |
| `GRAFANA_DB_USER` | Grafana metadata user | `dlh_grafana_user` |
| `GRAFANA_DB_PASSWORD` | Grafana metadata password | `change-this-grafana-db-password` |
| `GRAFANA_ADMIN_USER` | Grafana admin username | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | `admin` |

## 13. Optional Reverse Proxy

| Variable | Description | Example |
|---|---|---|
| `DLH_NPM_HTTP_PORT` | Nginx Proxy Manager HTTP port | `28080` |
| `DLH_NPM_HTTPS_PORT` | Nginx Proxy Manager HTTPS port | `28443` |
| `DLH_NPM_ADMIN_PORT` | Nginx Proxy Manager admin UI port | `28081` |

## 14. Validation Checklist

Before deploying, verify:

1. No required credential is blank for your target environment.
2. No two `DLH_*_PORT` values are duplicated.
3. `DLH_LAN_CIDR` matches your trusted network.
4. `DLH_BIND_IP` is appropriate for local-only vs LAN access.
5. Service passwords are rotated from defaults in production.

Quick validation command:

```bash
bash scripts/stackctl.sh validate-env
```

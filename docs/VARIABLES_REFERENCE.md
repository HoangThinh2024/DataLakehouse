# Variables Reference

This document defines the environment variables used by the DataLakehouse stack.

Source of truth:

- `.env.example` for defaults
- `.env` for active deployment values
- `scripts/setup.sh` and `scripts/stackctl.sh sync-env` for managed updates

## 1. Global

| Variable | Description | Example |
|---|---|---|
| `TZ` | Container timezone | `Asia/Ho_Chi_Minh` |
| `DLH_BIND_IP` | Host bind IP for published ports | `127.0.0.1` |
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
| `NOCODB_IMAGE_VERSION` | NocoDB image tag | `latest` |
| `SUPERSET_IMAGE_VERSION` | Superset image tag | `latest` |
| `GRAFANA_IMAGE_VERSION` | Grafana image tag | `latest` |

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
| `RUSTFS_BUCKET` | Generic app bucket | `nocodb` |
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

## 8. NocoDB

| Variable | Description | Example |
|---|---|---|
| `DLH_NOCODB_PORT` | Host port for NocoDB | `28082` |
| `NOCODB_DB_NAME` | NocoDB metadata DB | `dlh_nocodb` |
| `NOCODB_DB_USER` | NocoDB metadata user | `dlh_nocodb_user` |
| `NOCODB_DB_PASSWORD` | NocoDB metadata password | `change-this-nocodb-password` |

## 9. Superset

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

## 10. Grafana

| Variable | Description | Example |
|---|---|---|
| `DLH_GRAFANA_PORT` | Host port for Grafana | `23001` |
| `GRAFANA_DB_NAME` | Grafana metadata DB | `dlh_grafana` |
| `GRAFANA_DB_USER` | Grafana metadata user | `dlh_grafana_user` |
| `GRAFANA_DB_PASSWORD` | Grafana metadata password | `change-this-grafana-db-password` |
| `GRAFANA_ADMIN_USER` | Grafana admin username | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | `admin` |

## 11. Optional Reverse Proxy

| Variable | Description | Example |
|---|---|---|
| `DLH_NPM_HTTP_PORT` | Nginx Proxy Manager HTTP port | `28080` |
| `DLH_NPM_HTTPS_PORT` | Nginx Proxy Manager HTTPS port | `28443` |
| `DLH_NPM_ADMIN_PORT` | Nginx Proxy Manager admin UI port | `28081` |

## 12. Validation Checklist

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

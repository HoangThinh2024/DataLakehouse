# superset/

Apache Superset configuration for the DataLakehouse analytics dashboard layer.

## Structure

```
superset/
└── superset_config.py    # Superset Flask configuration (cache, results backend, security)
```

---

## Configuration (`superset_config.py`)

This file is mounted into the Superset container at the path defined by
`SUPERSET_CONFIG_PATH` (default: `/app/pythonpath/superset_config.py`).

Key settings applied:

| Setting | Description |
|---------|-------------|
| `CACHE_CONFIG` | Redis-backed cache using DB `SUPERSET_REDIS_CACHE_DB` (default: 2) |
| `RESULTS_BACKEND` | Redis-backed SQL Lab results backend using DB `SUPERSET_REDIS_RESULTS_DB` (default: 3) |
| `SECRET_KEY` | Flask session secret (`SUPERSET_SECRET_KEY` from `.env`) |
| `SUPERSET_AUTH_TYPE` | `db` for local login or `oauth` for Authentik SSO |
| `PREFERRED_URL_SCHEME` | `http` or `https` depending on `SUPERSET_PREFERRED_URL_SCHEME` |
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL metadata DB (`dlh_superset`) |

All values are read from environment variables at container startup — no credentials are
hardcoded in this file.

---

## Accessing Superset

URL: `http://localhost:28088` (default)

Default credentials (change before production use):

```
Username: admin   (SUPERSET_ADMIN_USER in .env)
Password: admin   (SUPERSET_ADMIN_PASSWORD in .env)
```

If you want Authentik SSO instead of local database login, set:

```ini
SUPERSET_AUTH_TYPE=oauth
SUPERSET_OIDC_CLIENT_ID=dlh-superset
SUPERSET_OIDC_CLIENT_SECRET=...
SUPERSET_OIDC_DISCOVERY_URL=https://<authentik-host>/application/o/superset/.well-known/openid-configuration
```

For local development, keep `SUPERSET_AUTH_TYPE=db` so the `admin/admin` account works.

If login still fails after changing the password in `.env`, restart Superset so the
startup command can re-apply the password to the metadata database:

```bash
docker compose up -d --force-recreate superset
```

---

## Datasources (Databases in Superset)

Superset connects to ClickHouse as its primary analytics database. The connection
is configured via the **Superset UI** or provisioned programmatically by
`scripts/create_superset_demo_dashboard.py`.

Recommended ClickHouse connection string:

```
clickhousedb://default:<password>@dlh-clickhouse:8123/analytics
```

Or using the `clickhouse-connect` driver (preferred):

```
clickhousedb+connect://default:<password>@dlh-clickhouse:8123/analytics
```

---

## Automated Dashboard Provisioning

`scripts/create_superset_demo_dashboard.py` uses the Superset REST API to:

1. Register the ClickHouse datasource (database).
2. Create virtual datasets for `silver_demo`, `gold_demo_daily`, `gold_demo_by_region`, etc.
3. Create pre-built charts.
4. Assemble a **Sales Overview** dashboard.

Run:

```bash
uv run python scripts/create_superset_demo_dashboard.py
```

Or trigger it as part of the full ETL + dashboard flow:

```bash
uv run python scripts/run_etl_and_dashboard.py --auto
```

---

## Python Dependencies

Superset requires additional Python packages to connect to ClickHouse and PostgreSQL.
These are installed at container startup using the `_PIP_ADDITIONAL_REQUIREMENTS`
environment variable:

```ini
# .env
SUPERSET_PIP_REQUIREMENTS=psycopg2-binary==2.9.9 clickhouse-connect==0.8.3
```

Change the versions here to upgrade connectors without rebuilding the Superset image.

---

## Troubleshooting

### Superset shows empty dashboards / "No data"

1. Verify the ETL pipeline has run: `bash scripts/stackctl.sh check-system`
2. Verify ClickHouse connection in Superset: **Settings → Database Connections → Test**
3. Check Redis cache: `docker compose exec dlh-redis redis-cli -a "$REDIS_PASSWORD" ping`

### Superset startup is slow

Superset runs `superset db upgrade` and `superset init` on every container start.
This is expected and typically takes 30–60 seconds. Monitor with:

```bash
docker compose logs dlh-superset --follow
```

### Login fails after password rotation

Superset stores its admin password hash in the metadata DB (`dlh_superset`). If you
change `SUPERSET_ADMIN_PASSWORD` in `.env`, you must reset the password via CLI:

```bash
docker compose exec dlh-superset superset fab reset-password \
  --username admin --password <new-password>
```

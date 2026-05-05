# grafana/

Grafana provisioning configuration for the DataLakehouse operational monitoring dashboard.

## Structure

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   ├── clickhouse.yaml     # ClickHouse datasource (analytics DB)
│   │   └── postgres.yaml       # PostgreSQL datasource (metadata DB)
│   └── dashboards/
│       ├── provider.yaml       # Dashboard provider config (scan this directory)
│       └── lakehouse_monitoring.json  # Pre-built DataLakehouse monitoring dashboard
└── dashboards/                 # (Optional) additional dashboard JSON files
```

---

## Provisioning

Grafana loads all files in `provisioning/` automatically on startup via the
`./grafana/provisioning:/etc/grafana/provisioning:ro` volume mount in `docker-compose.yaml`.

### Datasources

Both datasources are automatically configured on first boot:

| Datasource | Type | Internal URL | Database |
|------------|------|-------------|----------|
| ClickHouse | `grafana-clickhouse-datasource` | `http://dlh-clickhouse:8123` | `analytics` |
| PostgreSQL | `postgres` | `dlh-postgres:5432` | `datalakehouse` |

Credentials are injected from environment variables at runtime (not hardcoded in YAML).

### Dashboards

`lakehouse_monitoring.json` is the pre-built monitoring dashboard. It queries
the `analytics.pipeline_runs` table in ClickHouse to show:

- Pipeline run history (count over time)
- Latest run status per pipeline
- Row counts per pipeline run
- Error log (most recent failures)

---

## Accessing Grafana

URL: `http://localhost:23001` (default)

Default credentials (change before production use):

```
Username: admin   (set via GRAFANA_ADMIN_USER in .env)
Password: admin   (set via GRAFANA_ADMIN_PASSWORD in .env)
```

---

## Plugins

Plugins listed in `GF_INSTALL_PLUGINS` are installed automatically on container start:

| Plugin | Purpose |
|--------|---------|
| `grafana-piechart-panel` | Pie/donut chart panel |
| `grafana-clickhouse-datasource` | ClickHouse native datasource |

To add a plugin, append to `GF_INSTALL_PLUGINS` in `.env` and redeploy:

```bash
# .env
GF_INSTALL_PLUGINS=grafana-piechart-panel,grafana-clickhouse-datasource,other-plugin

bash scripts/stackctl.sh redeploy
```

---

## Adding a New Dashboard

1. Build the dashboard in the Grafana UI.
2. Export it as JSON: **Dashboard menu → Share → Export → Save to file**.
3. Save the JSON file to `grafana/provisioning/dashboards/` (or `grafana/dashboards/`).
4. Redeploy: `bash scripts/stackctl.sh redeploy` — Grafana will auto-import the new file.

Or use Grafana's API to create/update dashboards programmatically:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d @grafana/provisioning/dashboards/my_dashboard.json \
  http://localhost:23001/api/dashboards/import
```

---

## Useful ClickHouse Queries for Dashboards

```sql
-- Pipeline run timeline
SELECT
    toStartOfHour(started_at) AS hour,
    pipeline_name,
    count() AS runs,
    sum(rows_loaded) AS total_rows
FROM analytics.pipeline_runs
GROUP BY hour, pipeline_name
ORDER BY hour DESC;

-- Latest pipeline status
SELECT pipeline_name, status, rows_loaded, started_at
FROM analytics.pipeline_runs
ORDER BY started_at DESC
LIMIT 20;

-- Error summary
SELECT pipeline_name, error_message, count() AS occurrences
FROM analytics.pipeline_runs
WHERE status = 'error'
GROUP BY pipeline_name, error_message
ORDER BY occurrences DESC;
```

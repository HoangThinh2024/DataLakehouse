# postgres/

PostgreSQL initialisation and bootstrap files for the DataLakehouse stack.

## Structure

```
postgres/
└── init/
    ├── 000_create_app_security.sh    # Bootstrap: creates per-service DB roles and schemas
    ├── 001_lakehouse_metadata.sql    # Creates DataLakehouse metadata tables
    └── 002_sample_data.sql           # (Optional) Inserts demo/sample data into source tables
```

---

## How Initialisation Works

The `init/` directory is mounted to `/docker-entrypoint-initdb.d/` in the `dlh-postgres`
container.

### First-time volume creation (docker-entrypoint)

Scripts with `.sh` and `.sql` extensions are executed **alphabetically**, but
**only when the PostgreSQL data volume is brand new**. If the volume already
exists from a previous deployment, these scripts are skipped.

Files executed in order:
1. `000_create_app_security.sh` — creates databases, users, schemas
2. `001_lakehouse_metadata.sql` — creates metadata tracking tables
3. `002_sample_data.sql` — inserts sample data (demo tables)

### Re-sync on every `docker compose up` (`postgres-bootstrap` service)

The `postgres-bootstrap` container in `docker-compose.yaml` re-runs
`000_create_app_security.sh` every time the stack starts. This ensures all
per-service roles and passwords stay in sync even when the data volume already
exists (e.g., after a password rotation).

---

## Databases and Roles Created

`000_create_app_security.sh` creates the following databases and roles using
variables from `.env`:

| Database | Owner Role | `docker-compose.yaml` service |
|----------|-----------|-------------------------------|
| `datalakehouse` (`POSTGRES_DB`) | `dlh_admin` | Admin, source data |
| `dlh_mage` | `dlh_mage_user` | Mage pipeline metadata |
| `dlh_superset` | `dlh_superset_user` | Superset metadata |
| `dlh_grafana` | `dlh_grafana_user` | Grafana settings |
| `dlh_authentik` | `dlh_authentik_user` | Authentik identity data |
| `dlh_custom` (optional) | `dlh_custom_user` | Business workspace DB |

The custom workspace (`CUSTOM_DB_NAME`) is only created when `CUSTOM_DB_NAME` is
non-empty in `.env`.

---

## Connecting to PostgreSQL

### From the host (via mapped port)

```bash
PGPASSWORD="${POSTGRES_PASSWORD}" psql \
  -h 127.0.0.1 -p 25432 \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}"
```

### Inside the container

```bash
docker compose exec dlh-postgres \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
```

### Via CloudBeaver (web UI)

Open `http://localhost:28978`, create a new PostgreSQL connection:

- Host: `dlh-postgres`
- Port: `5432`
- Database: `datalakehouse` (or any service DB)
- User / Password: from `.env`

---

## Useful Queries

```sql
-- List all databases
\l

-- List users/roles
\du

-- Show source tables available for ETL
SELECT table_schema, table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name)::regclass)) AS size
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

---

## Adding a New Service Database

To add a new application database to the stack:

1. Edit `postgres/init/000_create_app_security.sh` and add:
   ```bash
   create_db_and_user "${NEW_DB_NAME}" "${NEW_DB_USER}" "${NEW_DB_PASSWORD}"
   ```
2. Add the corresponding variables to `.env.example` and `.env`.
3. Run `bash scripts/stackctl.sh redeploy` — the bootstrap service will create the new DB/user.

---

## Backup

PostgreSQL data is persisted in the `postgres_data` Docker volume.

Manual volume backup:

```bash
docker run --rm \
  -v datalakehouse_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /data
```

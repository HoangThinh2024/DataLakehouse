# Backup and Restore

This page covers how to back up and restore data in the DataLakehouse stack.

> **Design principle:** RustFS is the source of truth. ClickHouse is a serving layer
> that can be fully rebuilt from RustFS at any time. This makes the backup story simple:
> protect RustFS, and ClickHouse will always be recoverable.

---

## ClickHouse Backup

### How it works

`scripts/maintenance_tasks.py` uses ClickHouse's native `BACKUP DATABASE` command to create a compressed snapshot and stores it in RustFS at:

```
s3://backups/clickhouse/YYYY-MM-DD/
```

### Run manually

```bash
docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py
```

### Automate with cron

```bash
# Add to crontab: crontab -e
0 2 * * * docker exec dlh-mage python3 /home/src/scripts/maintenance_tasks.py >> /var/log/dlh_maintenance.log 2>&1
```

### Verify a backup exists

1. Open the RustFS Console at http://localhost:29101
2. Navigate to the `backups` bucket → `clickhouse/`
3. Confirm the `YYYY-MM-DD/` directory exists with objects inside

---

## ClickHouse Restore

### Step 1 — Find the backup

Open the RustFS Console and note the date of the backup you want to restore.

### Step 2 — Connect to ClickHouse

Use CloudBeaver (http://localhost:28978) or the ClickHouse HTTP API:

```bash
docker compose exec dlh-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD"
```

### Step 3 — Drop the existing database and restore

```sql
-- CAUTION: this is irreversible
DROP DATABASE IF EXISTS analytics;

-- Restore from S3 backup (replace YYYY-MM-DD with your target date)
RESTORE DATABASE analytics FROM S3(
    'http://dlh-rustfs:9000/backups/clickhouse/YYYY-MM-DD/',
    'rustfsadmin',    -- your RUSTFS_ACCESS_KEY
    'rustfsadmin'     -- your RUSTFS_SECRET_KEY
);
```

### Step 4 — Verify

```sql
SELECT table, count() AS parts
FROM system.parts
WHERE database = 'analytics' AND active
GROUP BY table
ORDER BY table;
```

---

## Rebuild ClickHouse from RustFS (without a backup)

Because RustFS holds all Silver and Gold Parquet files, you can re-populate ClickHouse at any time by re-running the load step:

```bash
# Re-run the full ETL pipeline
uv run python scripts/run_etl_and_dashboard.py --auto

# Or via Mage UI → etl_postgres_to_lakehouse → Run Pipeline Now
```

`load_to_clickhouse.py` always reads the latest Silver/Gold Parquet from RustFS, so re-running the pipeline is equivalent to a full restore.

---

## PostgreSQL Backup

### Back up a Docker volume to a tar archive

```bash
docker run --rm \
  -v datalakehouse_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /data
```

### Restore from archive

```bash
# Stop the stack first
bash scripts/stackctl.sh down

# Restore volume contents
docker run --rm \
  -v datalakehouse_postgres_data:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/postgres_backup_YYYYMMDD.tar.gz --strip 1"

# Start the stack
bash scripts/stackctl.sh up
```

### Using pg_dump / pg_restore

```bash
# Dump
docker compose exec dlh-postgres pg_dump -U "$POSTGRES_USER" -d datalakehouse \
  | gzip > datalakehouse_$(date +%Y%m%d).sql.gz

# Restore
gunzip -c datalakehouse_YYYYMMDD.sql.gz \
  | docker compose exec -T dlh-postgres psql -U "$POSTGRES_USER" -d datalakehouse
```

---

## RustFS (Lake Storage) Backup

RustFS stores all Parquet files as Docker volumes. Back up the volume:

```bash
docker run --rm \
  -v datalakehouse_rustfs_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/rustfs_backup_$(date +%Y%m%d).tar.gz /data
```

For offsite backups, use `mc` (MinIO Client) to sync to another S3-compatible bucket:

```bash
mc alias set source http://localhost:29100 "$RUSTFS_ACCESS_KEY" "$RUSTFS_SECRET_KEY"
mc mirror source/bronze source/silver source/gold s3://your-offsite-bucket/datalakehouse/
```

---

## Maintenance and Retention

`scripts/maintenance_tasks.py` automatically cleans up old data:

- **Retention:** 30 days (configurable via `RETENTION_DAYS` constant in the script)
- **Cleaned objects:**
  - Old Parquet files in RustFS `silver/` and `gold/` layers
  - Old ClickHouse backups in `s3://backups/` older than 30 days

To adjust the retention period:

```bash
# Edit the constant in the script
nano scripts/maintenance_tasks.py
# Change: RETENTION_DAYS = 30
```

---

## Full Disaster Recovery

If everything is lost but you have a PostgreSQL dump and a RustFS volume backup:

1. Start a fresh stack:
   ```bash
   bash scripts/stackctl.sh reset --hard
   bash scripts/setup.sh
   ```
2. Restore PostgreSQL from dump.
3. Restore RustFS volume from backup.
4. Re-run the load pipeline to repopulate ClickHouse:
   ```bash
   uv run python scripts/run_etl_and_dashboard.py --auto
   ```
5. Validate:
   ```bash
   bash scripts/stackctl.sh check-system
   ```

---

> See [docs/OPERATIONS.md § Backup and Restore](../docs/OPERATIONS.md#8-backup-and-restore) for additional details.

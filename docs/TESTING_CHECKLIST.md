# Data Lakehouse Validation Checklist

Use this checklist to verify the Data Lakehouse architecture is properly implemented.

## Architecture Compliance ✅

- [x] **PostgreSQL → RustFS Bronze**: Extracts saved to `bronze/demo/dt=YYYY-MM-DD/*.parquet`
- [x] **RustFS Bronze → RustFS Silver**: Cleaned data saved to `silver/demo/dt=YYYY-MM-DD/*.parquet`
- [x] **RustFS Silver → RustFS Gold**: Aggregations saved to `gold/demo_*/dt=YYYY-MM-DD/*.parquet`
- [x] **RustFS Gold → ClickHouse**: ClickHouse loads from RustFS, not PostgreSQL
- [x] **CSV Upload → RustFS Silver**: CSV cleaned and saved to `silver/csv_upload/dt=YYYY-MM-DD/*.parquet`
- [x] **No direct source → ClickHouse**: All data routes through RustFS intermediary

## Code Implementation ✅

- [x] `mage/utils/rustfs_layer_reader.py` created with helper functions
- [x] `mage/utils/__init__.py` created for package structure
- [x] `load_to_clickhouse.py` refactored to read from RustFS
- [x] `csv_to_rustfs_silver.py` exporter created
- [x] CSV pipeline metadata updated with new block
- [x] All imports and path handling correct

## Documentation ✅

- [x] `docs/LAKEHOUSE_ARCHITECTURE.md` - Complete blueprint (400+ lines)
- [x] `docs/RUSTFS_LAYER_READER_GUIDE.md` - Developer guide (450+ lines)
- [x] `docs/LAKEHOUSE_REFACTORING_SUMMARY.md` - Implementation summary (300+ lines)
- [x] `README.md` updated with architecture reference
- [x] `scripts/verify_lakehouse_architecture.py` - Validation tool created

## Git Commits ✅

- [x] Commit 4d66a39: "Implement proper Data Lakehouse architecture"
- [x] Commit fffa1f4: "Add comprehensive Data Lakehouse documentation"
- [x] Commit 10f5663: "Add detailed refactoring summary and verification guide"

## Testing Procedure

### Pre-Test Setup
```bash
cd /home/thinh03/Desktop/DataLakehouse

# Verify environment
docker compose ps
# Expected: dlh-postgres, dlh-rustfs, dlh-clickhouse, dlh-mage all UP

# Show RustFS layers
aws s3 ls s3://bronze/ --recursive --endpoint-url http://localhost:29100
aws s3 ls s3://silver/ --recursive --endpoint-url http://localhost:29100
aws s3 ls s3://gold/ --recursive --endpoint-url http://localhost:29100
```

### Step 1: Verify Layer Structure
```bash
# Check each layer exists and has proper structure
[ ] Bronze layer empty initially? dt=YYYY-MM-DD/ structure exists?
[ ] Silver layer empty initially? dt=YYYY-MM-DD/ structure exists?
[ ] Gold layer empty initially? dt=*, daily/region/category folders present?
```

### Step 2: Run Extract → Transform → Load
```bash
# Via Mage UI: http://localhost:26789
# Or CLI: docker compose exec dlh-mage magic run etl_postgres_to_lakehouse
```

**Monitor**:
- [ ] Extract Postgres block completes
- [ ] Bronze to RustFS exports successfully
- [ ] Transform Silver completes
- [ ] Silver to RustFS exports successfully
- [ ] Transform Gold completes
- [ ] Gold to RustFS exports successfully
- [ ] Load to ClickHouse completes (reading from RustFS!)

### Step 3: Verify RustFS Content
```bash
# After pipeline runs

# Check Bronze files created
aws s3 ls s3://bronze/demo/dt=$TODAY/ --endpoint-url http://localhost:29100
# Expected: 1 .parquet file with UUID name

# Check Silver files created
aws s3 ls s3://silver/demo/dt=$TODAY/ --endpoint-url http://localhost:29100
# Expected: 1 .parquet file

# Check Gold files created
aws s3 ls s3://gold/demo_daily/dt=$TODAY/ --endpoint-url http://localhost:29100
# Expected: 1 .parquet file (and for region, category)
```

### Step 4: Verify ClickHouse Data
```bash
# Connect to ClickHouse
docker compose exec dlh-clickhouse clickhouse-client

# Check tables exist
SHOW TABLES IN analytics;
# Expected: silver_demo, gold_demo_daily, gold_demo_by_region, gold_demo_by_category

# Check data loaded
SELECT COUNT(*) FROM analytics.silver_demo;
# Expected: > 0 (probably ~100k rows for demo)

# Check metadata tracking
SELECT DISTINCT _pipeline_run_id FROM analytics.silver_demo LIMIT 5;
# Expected: UUIDs showing lineage

# Check source tracking
SELECT _source_table, COUNT(*) FROM analytics.silver_demo GROUP BY _source_table;
# Expected: 'Demo' with row count
```

### Step 5: Verify Data Lineage
```bash
# Trace data through layers
# Bronze → Silver transformation
SELECT 'Bronze rows:', COUNT(*) FROM analytics.silver_demo;

# Check Silver → Gold aggregation
SELECT 'Gold daily rows:', COUNT(*) FROM analytics.gold_demo_daily;

# Verify timestamps show pipeline flow
SELECT MIN(_silver_processed_at), MAX(_silver_processed_at) FROM analytics.silver_demo;
SELECT MIN(_gold_processed_at), MAX(_gold_processed_at) FROM analytics.gold_demo_daily;
```

### Step 6: CSV Upload Pipeline Test
```bash
# Upload a CSV file
# Via Superset: Browse bucket, upload .csv file
# Or CLI: aws s3 cp test.csv s3://bronze/csv_upload/ --endpoint-url http://localhost:29100

# Wait 5 minutes for pipeline to run

# Check Silver layer
aws s3 ls s3://silver/csv_upload/dt=$TODAY/ --endpoint-url http://localhost:29100
# Expected: 1 .parquet file from CSV

# Check ClickHouse
SELECT COUNT(*) FROM analytics.csv_clean_rows;
# Expected: > 0
```

### Step 7: Run Verification Script
```bash
# (Requires boto3 in environment)
python3 scripts/verify_lakehouse_architecture.py
# Expected: ✓ All checks pass
```

## Performance Baseline

After first run:
- [ ] RustFS storage used: ~50MB-500MB (depends on data size)
- [ ] Pipeline execution time: < 5 minutes
- [ ] ClickHouse query response: < 1 second

## Rollback Criteria

If  issues occur, consider rollback if:
- [ ] Pipeline fails repeatedly
- [ ] Data corruption detected
- [ ] Performance degradation > 50%
- [ ] RustFS storage errors

Rollback command:
```bash
git revert 10f5663
git revert fffa1f4
git revert 4d66a39
docker compose up -d mage
```

## Sign-Off

- **Tested By**: _________________
- **Date**: _________________
- **Status**: ☐ Passed ☐ Failed ☐ Issues Found

**Notes**:
_____________________________________________________________________________

_____________________________________________________________________________

---

**Reference**: See `docs/LAKEHOUSE_REFACTORING_SUMMARY.md` for detailed implementation.

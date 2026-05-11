# Bronze Layer Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct data path inconsistencies, fix accurate data lake monitoring, and ensure reliable PostgreSQL bronze layer archival.

**Architecture:** Use S3 pagination for accurate monitoring, align ingestion prefixes with warehouse metadata, and optimize Mage archival logic.

**Tech Stack:** Python (boto3), Bash, Mage.ai.

---

### Task 1: Fix Object Counting in Architecture Verification

**Files:**
- Modify: `scripts/verify_lakehouse_architecture.py`

- [ ] **Step 1: Implement pagination for bucket counting**
Update the script to correctly count all objects in a bucket instead of being limited to 10.

```python
# scripts/verify_lakehouse_architecture.py
# In check_rusfs_layers function:

        layer_res = {'bucket': bucket, 'exists': False, 'object_count': 0, 'samples': []}
        try:
            client.head_bucket(Bucket=bucket)
            layer_res['exists'] = True
            
            # New code with pagination for accurate counting:
            count = 0
            paginator = client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                count += page.get('KeyCount', 0)
                if 'Contents' in page and not layer_res['samples']:
                    layer_res['samples'] = [obj['Key'] for obj in page['Contents'][:3]]
            
            layer_res['object_count'] = count
            if not results.get('json_mode'):
                print(f"✓ {layer_name.upper()} bucket exists: {bucket} ({count} objects)")
```

- [ ] **Step 2: Verify the fix**
Run: `uv run python scripts/verify_lakehouse_architecture.py`
Expected: `✓ BRONZE bucket exists: bronze (14 objects)` (instead of 10).

- [ ] **Step 3: Commit**
```bash
git add scripts/verify_lakehouse_architecture.py
git commit -m "fix: use S3 pagination for accurate object counting in architecture verification"
```

### Task 2: Align Excel Ingestion Paths and Watcher

**Files:**
- Modify: `scripts/ingest_to_bronze.py`
- Modify: `scripts/realtime_watcher.sh`

- [ ] **Step 1: Update prefix in `ingest_to_bronze.py`**
Change `excel_upload` to `Data Mẫu 12 dự án` to match the ClickHouse event log.

```python
# scripts/ingest_to_bronze.py:53
# Replace:
# prefix = "excel_upload" if file_name.endswith(".xlsx") else "csv_upload"
# With:
prefix = "Data Mẫu 12 dự án" if file_name.endswith(".xlsx") else "csv_upload"
```

- [ ] **Step 2: Update `realtime_watcher.sh` to monitor the new prefix**
Update the S3 state detection to include the new prefix.

```bash
# scripts/realtime_watcher.sh:65
# Replace:
# current_excel_state=$(docker exec dlh-rustfs ls -lR /data/bronze/excel_upload 2>/dev/null | grep ".xlsx" || echo "")
# With:
current_excel_state=$(docker exec dlh-rustfs ls -lR "/data/bronze/Data Mẫu 12 dự án" 2>/dev/null | grep ".xlsx" || echo "")
```

- [ ] **Step 3: Re-align existing S3 data**
Move existing files from `excel_upload/` to `Data Mẫu 12 dự án/` in S3.

```bash
uv run python -c "
import boto3
from botocore.config import Config
s3 = boto3.client('s3', endpoint_url='http://localhost:29100', aws_access_key_id='doe', aws_secret_access_key='Do12345678910..', config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}))
resp = s3.list_objects_v2(Bucket='bronze', Prefix='excel_upload/')
if 'Contents' in resp:
    for obj in resp['Contents']:
        old_key = obj['Key']
        new_key = old_key.replace('excel_upload/', 'Data Mẫu 12 dự án/')
        print(f'Moving {old_key} to {new_key}')
        s3.copy_object(Bucket='bronze', CopySource={'Bucket': 'bronze', 'Key': old_key}, Key=new_key)
        s3.delete_object(Bucket='bronze', Key=old_key)
"
```

- [ ] **Step 4: Commit**
```bash
git add scripts/ingest_to_bronze.py scripts/realtime_watcher.sh
git commit -m "refactor: align excel ingestion paths with warehouse metadata"
```

### Task 3: Stabilize PostgreSQL Bronze Archival

**Files:**
- Modify: `mage/data_exporters/bronze_to_rustfs.py`

- [ ] **Step 1: Improve connection resilience in Mage**
Add better logging for connection failures to RustFS from within the container.

```python
# mage/data_exporters/bronze_to_rustfs.py
# Inside export_bronze function:
    client = _s3_client()
    try:
        _ensure_bucket(client, bucket)
    except Exception as e:
        print(f"[bronze_to_rustfs] CRITICAL: Connection to RustFS failed: {e}")
        # Ensure we don't proceed if archival is mandatory
        raise
```

- [ ] **Step 2: Force a full archival run**
Run the PostgreSQL pipeline manually to ensure it creates the Bronze records.
Run: `docker exec dlh-mage mage run /home/src etl_postgres_to_lakehouse`

### Task 4: Final Validation

- [ ] **Step 1: Run Reconcile**
Run: `uv run python scripts/reconcile_data.py`
Expected: `✓ System in sync.`

- [ ] **Step 2: Run Architecture Verification**
Run: `uv run python scripts/verify_lakehouse_architecture.py`
Expected: `OVERALL STATUS: PASSED` (or significantly improved).

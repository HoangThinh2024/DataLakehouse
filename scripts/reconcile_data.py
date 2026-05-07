import os
import sys
import subprocess
import logging
import time
from clickhouse_driver import Client
import boto3
from botocore.client import Config as BotoConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
CHECK_INTERVAL = int(os.getenv('HEALER_CHECK_INTERVAL', '300')) # 5 minutes

RUSTFS_ENDPOINT = os.getenv('RUSTFS_ENDPOINT_URL', 'http://localhost:29100').replace('dlh-rustfs:9000', 'localhost:29100')
ACCESS_KEY = os.getenv('RUSTFS_ACCESS_KEY', 'rustfsadmin')
SECRET_KEY = os.getenv('RUSTFS_SECRET_KEY', 'rustfsadmin')
BRONZE_BUCKET = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')

CH_HOST = os.getenv('CLICKHOUSE_HOST', 'localhost')
if CH_HOST == 'dlh-clickhouse': CH_HOST = 'localhost'
CH_PORT = int(os.getenv('DLH_CLICKHOUSE_TCP_PORT', '29000'))
CH_USER = os.getenv('CLICKHOUSE_USER', 'default')
CH_PASS = os.getenv('CLICKHOUSE_PASSWORD', '')
CH_DB = os.getenv('CLICKHOUSE_DB', 'analytics')

PIPELINE_UUID = "etl_excel_to_lakehouse"

def get_ch_client():
    return Client(host=CH_HOST, port=CH_PORT, user=CH_USER, password=CH_PASS, database=CH_DB)

def get_missing_files():
    """Find files in S3 Bronze that aren't in ClickHouse events."""
    try:
        s3 = boto3.client('s3', endpoint_url=RUSTFS_ENDPOINT, aws_access_key_id=ACCESS_KEY,
                         aws_secret_access_key=SECRET_KEY, config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}))
        s3_files = {}
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=BRONZE_BUCKET):
            for obj in page.get('Contents', []):
                if obj['Key'].lower().endswith('.xlsx'):
                    s3_files[obj['Key']] = obj['ETag'].strip('"')
        
        ch = get_ch_client()
        rows = ch.execute("SELECT source_key, etag FROM excel_upload_events WHERE status = 'success'")
        processed = {row[0]: row[1] for row in rows}
        
        return [k for k, v in s3_files.items() if k not in processed or processed.get(k) != v]
    except Exception as e:
        logger.error(f"Error checking missing files: {e}")
        return []

def check_sync_status():
    """Check if ClickHouse reports table is in sync with Silver/Gold layer."""
    try:
        ch = get_ch_client()
        # Get total expected rows from successful events
        expected = ch.execute("SELECT sum(row_count) FROM (SELECT source_key, argMax(row_count, processed_at) as row_count FROM excel_upload_events WHERE status = 'success' GROUP BY source_key)")[0][0] or 0
        # Get actual rows in project_reports
        actual = ch.execute("SELECT count() FROM project_reports")[0][0]
        
        return actual >= expected, actual, expected
    except Exception as e:
        logger.error(f"Error checking sync status: {e}")
        return True, 0, 0

def trigger_pipeline(reason):
    logger.info(f"Triggering Pipeline ({reason})...")
    # For Excel, we have a special trigger that can force a reload of the last silver file
    # even if no new files are found in Bronze.
    # We can pass a runtime variable to Mage if needed, but here we'll just run it.
    cmd = ["docker", "exec", "dlh-mage", "mage", "run", "/home/src", PIPELINE_UUID]
    subprocess.run(cmd)

def run_once():
    missing = get_missing_files()
    if missing:
        trigger_pipeline(f"Missing {len(missing)} files from Bronze")
        return
        
    is_synced, actual, expected = check_sync_status()
    if not is_synced:
        logger.warning(f"Data out of sync! ClickHouse: {actual}, Expected: {expected}. Repairing...")
        # To repair, we need to force the 'Load' block to run. 
        # In this specific Mage setup, running the pipeline will skip if no new files.
        # We might need to delete one event or use a different trigger.
        # Hack: delete the latest event to force re-processing of that file and trigger the batch load.
        ch = get_ch_client()
        ch.execute("DELETE FROM excel_upload_events WHERE source_key = (SELECT source_key FROM excel_upload_events ORDER BY processed_at DESC LIMIT 1)")
        trigger_pipeline("Forced refresh due to sync gap")
    else:
        logger.info(f"✓ System in sync. Gold rows: {actual}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        logger.info(f"Starting Healer Watcher (Interval: {CHECK_INTERVAL}s)...")
        while True:
            run_once()
            time.sleep(CHECK_INTERVAL)
    else:
        run_once()

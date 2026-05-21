import os
import io
import sys
import boto3
from clickhouse_driver import Client
from dotenv import load_dotenv
import subprocess
import time

# Setup paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

load_dotenv(os.path.join(REPO_ROOT, ".env"))

def get_ch_client():
    ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
    if ch_host == 'dlh-clickhouse':
        ch_host = 'localhost'
    return Client(
        host=ch_host,
        port=int(os.getenv('CLICKHOUSE_TCP_PORT', '29000')),
        database=os.getenv('CLICKHOUSE_DB', 'analytics'),
        user=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
        connect_timeout=10
    )

def get_s3_client():
    rustfs_endpoint = os.getenv('RUSTFS_EXTERNAL_ENDPOINT', os.getenv('RUSTFS_ENDPOINT_URL', 'http://localhost:29100'))
    if "dlh-rustfs" in rustfs_endpoint:
        rustfs_endpoint = rustfs_endpoint.replace("dlh-rustfs:9000", "localhost:29100")
    return boto3.client(
        's3',
        endpoint_url=rustfs_endpoint,
        aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY', 'doe'),
        aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY', 'change-me-in-production'),
        config=boto3.session.Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )

def main():
    print("=" * 60)
    print("DATALAKEHOUSE PURGE & CLEAN RELOAD")
    print("=" * 60)

    s3_client = get_s3_client()
    ch_client = get_ch_client()
    bronze_bucket = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')
    silver_bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    gold_bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')

    # 1. Purge S3 Silver & Gold Excel Parquet files
    print("\n1. Purging Excel Parquet files from S3 Silver and Gold layers...")
    
    # Silver bucket excel_projects/
    res = s3_client.list_objects_v2(Bucket=silver_bucket, Prefix='excel_projects/')
    for obj in res.get('Contents', []):
        key = obj['Key']
        print(f"  [-] Deleting s3://{silver_bucket}/{key}")
        s3_client.delete_object(Bucket=silver_bucket, Key=key)

    # Gold bucket projects/
    res = s3_client.list_objects_v2(Bucket=gold_bucket, Prefix='projects/')
    for obj in res.get('Contents', []):
        key = obj['Key']
        print(f"  [-] Deleting s3://{gold_bucket}/{key}")
        s3_client.delete_object(Bucket=gold_bucket, Key=key)

    # Gold bucket workload/
    res = s3_client.list_objects_v2(Bucket=gold_bucket, Prefix='workload/')
    for obj in res.get('Contents', []):
        key = obj['Key']
        print(f"  [-] Deleting s3://{gold_bucket}/{key}")
        s3_client.delete_object(Bucket=gold_bucket, Key=key)

    # 2. Truncate ClickHouse serving tables and events log
    print("\n2. Truncating ClickHouse serving and log tables...")
    tables_to_truncate = [
        'analytics.project_reports',
        'analytics.gold_projects_summary',
        'analytics.gold_workload_report',
        'analytics.excel_upload_events'
    ]
    for table in tables_to_truncate:
        print(f"  [+] Truncating {table}")
        ch_client.execute(f"TRUNCATE TABLE {table}")

    # 3. Trigger Mage Excel pipeline run to rebuild the Lakehouse cleanly
    print("\n3. Triggering Mage Pipeline (etl_excel_to_lakehouse) to reload all Bronze files...")
    trigger_cmd = "docker exec dlh-mage mage run /home/src etl_excel_to_lakehouse"
    subprocess.run(trigger_cmd, shell=True)

    print("\n4. Verifying new counts...")
    time.sleep(5)  # Wait briefly for DBT and serving inserts to settle
    
    reports_count = ch_client.execute("SELECT count() FROM analytics.project_reports")[0][0]
    summary_count = ch_client.execute("SELECT count() FROM analytics.fct_projects_summary")[0][0]
    
    print(f"\nFinal ClickHouse Serving Counts:")
    print(f"  - analytics.project_reports: {reports_count} rows (Expected: 321)")
    print(f"  - analytics.fct_projects_summary: {summary_count} rows (Expected: 12)")

    if reports_count == 321 and summary_count == 12:
        print("\nSUCCESS: Lakehouse cleaned and reloaded successfully! ✅")
    else:
        print("\nWARNING: Counts differ from expectations. Please audit Mage logs. ⚠️")

if __name__ == "__main__":
    main()

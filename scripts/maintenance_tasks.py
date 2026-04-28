import os
import datetime as dt
import boto3
from botocore.client import Config as BotoConfig
from clickhouse_driver import Client

# Configuration
RUSTFS_ENDPOINT = 'http://dlh-rustfs:9000'
ACCESS_KEY = 'rustfsadmin'
SECRET_KEY = 'rustfsadmin'
CLICKHOUSE_HOST = 'dlh-clickhouse'
DB_NAME = 'analytics'
BACKUP_BUCKET = 'backups'
RETENTION_DAYS = 30  # Keep backups and old data for 30 days

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=RUSTFS_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'})
    )

def backup_clickhouse():
    print(f"[{dt.datetime.now()}] Starting ClickHouse backup...")
    date_str = dt.date.today().isoformat()
    s3_client = get_s3_client()
    
    # Ensure backup bucket exists
    try:
        s3_client.create_bucket(Bucket=BACKUP_BUCKET)
    except:
        pass
    
    # ClickHouse Native Backup to S3 (RustFS)
    # Using the native BACKUP command available in modern ClickHouse
    backup_path = f"S3('{RUSTFS_ENDPOINT}/{BACKUP_BUCKET}/clickhouse/{date_str}/', '{ACCESS_KEY}', '{SECRET_KEY}')"
    
    client = Client(
        host=CLICKHOUSE_HOST,
        user=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', '')
    )
    try:
        client.execute(f"BACKUP DATABASE {DB_NAME} TO {backup_path}")
        print(f"[{dt.datetime.now()}] Backup successful: s3://{BACKUP_BUCKET}/clickhouse/{date_str}/")
    except Exception as e:
        print(f"[{dt.datetime.now()}] Backup failed: {e}")

def cleanup_old_data():
    print(f"[{dt.datetime.now()}] Starting cleanup tasks...")
    s3_client = get_s3_client()
    cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RETENTION_DAYS)
    
    buckets = ['silver', 'gold', 'backups']
    for bucket in buckets:
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    last_modified = obj['LastModified']
                    if last_modified < cutoff_date:
                        print(f"Deleting expired object: s3://{bucket}/{obj['Key']} (Modified: {last_modified})")
                        s3_client.delete_object(Bucket=bucket, Key=obj['Key'])
        except Exception as e:
            print(f"Error cleaning bucket {bucket}: {e}")

if __name__ == "__main__":
    backup_clickhouse()
    cleanup_old_data()
    print(f"[{dt.datetime.now()}] All maintenance tasks completed.")

import os
import datetime as dt
import logging
import sys
import boto3
from botocore.client import Config as BotoConfig
from clickhouse_driver import Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration from environment or defaults
RUSTFS_S3_ENDPOINT = os.getenv('RUSTFS_S3_ENDPOINT', 'http://127.0.0.1:29100')
RUSTFS_INTERNAL_ENDPOINT = os.getenv('RUSTFS_INTERNAL_ENDPOINT', 'http://dlh-rustfs:9000')

# Secrets should be provided via environment variables
ACCESS_KEY = os.getenv('RUSTFS_ACCESS_KEY')
SECRET_KEY = os.getenv('RUSTFS_SECRET_KEY')

CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', '127.0.0.1')
CLICKHOUSE_PORT = int(os.getenv('DLH_CLICKHOUSE_TCP_PORT', 29000))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD')
DB_NAME = os.getenv('CLICKHOUSE_DB', 'analytics')

BACKUP_BUCKET = 'backups'
RETENTION_DAYS = 30  # Keep backups and old data for 30 days

def validate_config():
    """Validate that all required environment variables are set."""
    required_vars = {
        'RUSTFS_ACCESS_KEY': ACCESS_KEY,
        'RUSTFS_SECRET_KEY': SECRET_KEY,
        'CLICKHOUSE_USER': CLICKHOUSE_USER,
        'CLICKHOUSE_PASSWORD': CLICKHOUSE_PASSWORD
    }
    
    missing = [var for var, value in required_vars.items() if not value]
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please set these variables before running the script.")
        sys.exit(1)
    
    logger.info("Configuration validated successfully.")

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=RUSTFS_S3_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'})
    )

def backup_clickhouse():
    logger.info("Starting ClickHouse backup...")
    date_str = dt.date.today().isoformat()
    s3_client = get_s3_client()
    
    # Ensure backup bucket exists
    try:
        s3_client.create_bucket(Bucket=BACKUP_BUCKET)
    except Exception:
        # Bucket might already exist
        pass
    
    # ClickHouse Native Backup to S3 (RustFS)
    # The server needs the INTERNAL endpoint
    backup_path = f"S3('{RUSTFS_INTERNAL_ENDPOINT}/{BACKUP_BUCKET}/clickhouse/{date_str}/', '{ACCESS_KEY}', '{SECRET_KEY}')"
    
    logger.info(f"Connecting to ClickHouse at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}...")
    client = Client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD
    )
    try:
        logger.info(f"Running BACKUP DATABASE {DB_NAME} to RustFS...")
        client.execute(f"BACKUP DATABASE {DB_NAME} TO {backup_path}")
        logger.info(f"Backup successful: s3://{BACKUP_BUCKET}/clickhouse/{date_str}/")
    except Exception as e:
        logger.error(f"Backup failed: {e}")

def cleanup_old_data():
    logger.info("Starting cleanup tasks...")
    s3_client = get_s3_client()
    cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RETENTION_DAYS)
    
    buckets = ['silver', 'gold', 'backups']
    for bucket in buckets:
        try:
            logger.info(f"Checking bucket: {bucket}")
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    last_modified = obj['LastModified']
                    if last_modified < cutoff_date:
                        logger.info(f"Deleting expired object: s3://{bucket}/{obj['Key']} (Modified: {last_modified})")
                        s3_client.delete_object(Bucket=bucket, Key=obj['Key'])
        except Exception as e:
            logger.error(f"Error cleaning bucket {bucket}: {e}")

if __name__ == "__main__":
    validate_config()
    backup_clickhouse()
    cleanup_old_data()
    logger.info("All maintenance tasks completed.")

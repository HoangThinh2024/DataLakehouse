import os
import datetime as dt
import logging
import sys
import socket
import functools
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError, ConnectTimeoutError
from clickhouse_driver import Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Discovery Helpers ---

@functools.lru_cache(maxsize=1)
def _local_ip_candidates() -> list[str]:
    candidates = []
    try:
        hostname_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        candidates.extend(hostname_ips)
    except Exception: pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('8.8.8.8', 80))
            candidates.append(probe.getsockname()[0])
        finally: probe.close()
    except Exception: pass
    return list(dict.fromkeys(candidates))

def is_port_open(host, port, timeout=0.5):
    if not host or not port: return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError): return False

def _probe_s3(endpoint):
    try:
        parsed = urlparse(endpoint)
        if not is_port_open(parsed.hostname, parsed.port or 80): return None
        client = boto3.client('s3', endpoint_url=endpoint,
                             aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY'),
                             aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY'),
                             config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'},
                                              connect_timeout=1, retries={'max_attempts': 0}))
        client.list_buckets()
        return endpoint
    except Exception: return None

def _probe_ch(host, port):
    if not is_port_open(host, port): return None
    try:
        client = Client(host=host, port=port, user=os.getenv('CLICKHOUSE_USER'),
                        password=os.getenv('CLICKHOUSE_PASSWORD'), connect_timeout=1)
        client.execute('SELECT 1')
        return (host, port)
    except Exception: return None

# --- Configuration ---

ACCESS_KEY = os.getenv('RUSTFS_ACCESS_KEY')
SECRET_KEY = os.getenv('RUSTFS_SECRET_KEY')
DB_NAME = os.getenv('CLICKHOUSE_DB', 'analytics')
BACKUP_BUCKET = os.getenv('BACKUP_BUCKET', 'backups')
RETENTION_DAYS = int(os.getenv('RETENTION_DAYS', '30'))

# Internal endpoint for ClickHouse server to reach RustFS
RUSTFS_INTERNAL_ENDPOINT = os.getenv('RUSTFS_INTERNAL_ENDPOINT', 'http://dlh-rustfs:9000')

_cached_s3_endpoint = None
_cached_ch_endpoint = None

def get_effective_s3_endpoint():
    global _cached_s3_endpoint
    if _cached_s3_endpoint: return _cached_s3_endpoint
    
    endpoints = [os.getenv('RUSTFS_S3_ENDPOINT'), os.getenv('RUSTFS_ENDPOINT_URL'),
                 'http://dlh-rustfs:9000', 'http://localhost:29100', 'http://127.0.0.1:29100']
    endpoints.extend(f'http://{ip}:29100' for ip in _local_ip_candidates())
    unique = [e for e in dict.fromkeys(endpoints) if e]
    
    with ThreadPoolExecutor(max_workers=len(unique)) as executor:
        futures = {executor.submit(_probe_s3, e): e for e in unique}
        for future in as_completed(futures):
            res = future.result()
            if res:
                _cached_s3_endpoint = res
                return res
    raise RuntimeError("Could not connect to RustFS S3 API")

def get_effective_ch_endpoint():
    global _cached_ch_endpoint
    if _cached_ch_endpoint: return _cached_ch_endpoint
    
    hosts = [os.getenv('CLICKHOUSE_HOST'), 'dlh-clickhouse', 'localhost', '127.0.0.1']
    hosts.extend(_local_ip_candidates())
    ports = [int(os.getenv('DLH_CLICKHOUSE_TCP_PORT', 29000)), 9000]
    probes = [(h, p) for h in hosts if h for p in ports]
    
    with ThreadPoolExecutor(max_workers=min(len(probes), 10)) as executor:
        futures = {executor.submit(_probe_ch, h, p): (h, p) for h, p in probes}
        for future in as_completed(futures):
            res = future.result()
            if res:
                _cached_ch_endpoint = res
                return res
    raise RuntimeError("Could not connect to ClickHouse")

def get_s3_client():
    return boto3.client('s3', endpoint_url=get_effective_s3_endpoint(),
                       aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                       config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'},
                                        connect_timeout=5, read_timeout=10))

# --- Tasks ---

def backup_clickhouse():
    logger.info("Starting ClickHouse backup task...")
    try:
        s3_client = get_s3_client()
        try:
            s3_client.create_bucket(Bucket=BACKUP_BUCKET)
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') not in ('BucketAlreadyExists', 'BucketAlreadyOwnedByYou'):
                raise
        
        host, port = get_effective_ch_endpoint()
        date_str = dt.date.today().isoformat()
        # Note: Server uses INTERNAL endpoint
        backup_path = f"S3('{RUSTFS_INTERNAL_ENDPOINT}/{BACKUP_BUCKET}/clickhouse/{date_str}/', '{ACCESS_KEY}', '{SECRET_KEY}')"
        
        with Client(host=host, port=port, user=os.getenv('CLICKHOUSE_USER'), 
                    password=os.getenv('CLICKHOUSE_PASSWORD')) as ch:
            logger.info(f"Triggering native backup for database '{DB_NAME}'...")
            ch.execute(f"BACKUP DATABASE {DB_NAME} TO {backup_path}")
            logger.info(f"✓ Backup successful: s3://{BACKUP_BUCKET}/clickhouse/{date_str}/")
    except Exception as e:
        logger.error(f"✗ ClickHouse backup failed: {e}")
        return False
    return True

def cleanup_old_data():
    logger.info(f"Starting cleanup task (Retention: {RETENTION_DAYS} days)...")
    try:
        s3_client = get_s3_client()
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RETENTION_DAYS)
        buckets = ['silver', 'gold', 'backups']
        
        total_deleted = 0
        for bucket in buckets:
            logger.info(f"Scanning bucket: {bucket}")
            try:
                paginator = s3_client.get_paginator('list_objects_v2')
                bucket_deleted = 0
                for page in paginator.paginate(Bucket=bucket):
                    if 'Contents' not in page: continue
                    for obj in page['Contents']:
                        if obj['LastModified'] < cutoff:
                            s3_client.delete_object(Bucket=bucket, Key=obj['Key'])
                            bucket_deleted += 1
                if bucket_deleted > 0:
                    logger.info(f"  → Deleted {bucket_deleted} expired objects from {bucket}")
                total_deleted += bucket_deleted
            except ClientError as e:
                if e.response.get('Error', {}).get('Code') == 'NoSuchBucket':
                    logger.warning(f"  ⚠ Bucket '{bucket}' does not exist, skipping.")
                else: raise
        logger.info(f"✓ Cleanup complete. Total objects removed: {total_deleted}")
    except Exception as e:
        logger.error(f"✗ Cleanup failed: {e}")
        return False
    return True

if __name__ == "__main__":
    logger.info("=== DataLakehouse Maintenance Suite ===")
    if not all([ACCESS_KEY, SECRET_KEY]):
        logger.error("Missing RUSTFS credentials in environment.")
        sys.exit(1)
        
    ch_ok = backup_clickhouse()
    s3_ok = cleanup_old_data()
    
    if ch_ok and s3_ok:
        logger.info("=== All maintenance tasks finished successfully ===")
    else:
        logger.warning("=== Maintenance finished with errors ===")
        sys.exit(1)

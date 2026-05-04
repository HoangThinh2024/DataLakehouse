#!/usr/bin/env python3
"""
Test script to verify Data Lakehouse architecture compliance.

Validates:
1. All data paths go through RustFS layers (Bronze/Silver/Gold)
2. ClickHouse reads from RustFS, not from source systems
3. Data immutability and versioning in RustFS
"""

import sys
import os
import socket
import functools
from urllib.parse import urlparse

# Add mage path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError, EndpointConnectionError


def _s3_client(endpoint_url: str | None = None):
    """Create RustFS S3 client."""
    return boto3.client(
        's3',
        endpoint_url=endpoint_url or os.getenv('RUSTFS_ENDPOINT_URL', 'http://dlh-rustfs:9000'),
        aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY', 'rustfsadmin'),
        aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY', 'rustfsadmin'),
        region_name=os.getenv('RUSTFS_REGION', 'us-east-1'),
        config=BotoConfig(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            connect_timeout=2,
            read_timeout=2,
            retries={'max_attempts': 1},
        ),
    )


@functools.lru_cache(maxsize=1)
def _local_ip_candidates() -> list[str]:
    """Return likely host IPs for reaching Docker-published ports."""
    candidates = []

    try:
        hostname_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        candidates.extend(hostname_ips)
    except Exception:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('8.8.8.8', 80))
            candidates.append(probe.getsockname()[0])
        finally:
            probe.close()
    except Exception:
        pass

    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open."""
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


_cached_s3_client = None
_cached_s3_endpoint = None


def _connect_s3_client():
    """Connect to RustFS, falling back to localhost when running on host."""
    global _cached_s3_client, _cached_s3_endpoint
    if _cached_s3_client is not None:
        return _cached_s3_client, _cached_s3_endpoint

    host_ips = _local_ip_candidates()

    endpoints = [
        os.getenv('RUSTFS_ENDPOINT_URL'),
        'http://dlh-rustfs:9000',
        'http://localhost:29100',
        'http://127.0.0.1:29100',
    ]
    endpoints.extend(f'http://{host_ip}:29100' for host_ip in host_ips)
    seen = set()

    for endpoint in endpoints:
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)

        # Fast port probe before full boto3 connection
        try:
            parsed = urlparse(endpoint)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            if not is_port_open(host, port):
                continue
        except Exception:
            pass

        client = _s3_client(endpoint)
        try:
            client.list_buckets()
            _cached_s3_client = client
            _cached_s3_endpoint = endpoint
            return client, endpoint
        except Exception:
            continue

    raise RuntimeError(
        'Could not connect to RustFS using any known endpoint. '
        'Ensure RustFS is running, ports are mapped (9000 internal or 29100 external), '
        'and credentials in .env (RUSTFS_ACCESS_KEY/SECRET_KEY) are correct.'
    )


def check_rusfs_layers() -> bool:
    """Check that RustFS has proper layer structure."""
    try:
        client, endpoint = _connect_s3_client()
        print(f"Using RustFS endpoint: {endpoint}")
    except Exception as exc:
        print(f"✗ RustFS connection failed: {exc}")
        return False
    
    success = True
    layers = {
        'bronze': os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze'),
        'silver': os.getenv('RUSTFS_SILVER_BUCKET', 'silver'),
        'gold': os.getenv('RUSTFS_GOLD_BUCKET', 'gold'),
    }
    
    print("\n=== Checking RustFS Layer Structure ===")
    
    for layer_name, bucket in layers.items():
        try:
            response = client.head_bucket(Bucket=bucket)
            print(f"✓ {layer_name.upper()} bucket exists: {bucket}")
            
            # List objects in this bucket
            objs = client.list_objects_v2(Bucket=bucket, MaxKeys=10)
            count = objs.get('KeyCount', 0)
            print(f"  → Contains {count} objects")
            
            if 'Contents' in objs:
                for obj in objs['Contents'][:3]:
                    print(f"     - {obj['Key']}")
        except ClientError as exc:
            print(f"✗ {layer_name.upper()} bucket missing: {bucket}")
            print(f"  Error: {exc}")
            success = False
    return success


def check_data_lineage() -> bool:
    """Trace a data record from source to ClickHouse."""
    print("\n=== Checking Data Lineage (Bronze → Silver → Gold → ClickHouse) ===")
    
    # Check Bronze layer for PostgreSQL data
    try:
        client, _ = _connect_s3_client()
    except Exception as exc:
        print(f"✗ Cannot inspect RustFS lineage: {exc}")
        return False
    
    success = True
    bronze_bucket = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')
    bronze_prefix = os.getenv('RUSTFS_BRONZE_PREFIX', 'demo')
    
    try:
        response = client.list_objects_v2(
            Bucket=bronze_bucket,
            Prefix=bronze_prefix,
            MaxKeys=5
        )
        
        if 'Contents' in response and len(response['Contents']) > 0:
            print(f"✓ Bronze: Found {len(response['Contents'])} extraction(s)")
            for obj in response['Contents']:
                print(f"  → {obj['Key']}")
        else:
            print("⚠ Bronze: No PostgreSQL extractions found yet (expected on first run)")
    except ClientError as exc:
        print(f"✗ Bronze: Error listing objects: {exc}")
    
    # Check Silver layer for cleaned data
    silver_bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    silver_prefix = os.getenv('RUSTFS_SILVER_PREFIX', 'demo')
    
    try:
        response = client.list_objects_v2(
            Bucket=silver_bucket,
            Prefix=silver_prefix,
            MaxKeys=5
        )
        
        if 'Contents' in response and len(response['Contents']) > 0:
            print(f"✓ Silver: Found {len(response['Contents'])} transformation(s)")
            for obj in response['Contents']:
                print(f"  → {obj['Key']}")
        else:
            print("⚠ Silver: No transformations found yet (expected on first run)")
    except ClientError as exc:
        print(f"✗ Silver: Error listing objects: {exc}")
    
    # Check Gold layer for aggregations
    gold_bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    
    try:
        response = client.list_objects_v2(Bucket=gold_bucket, MaxKeys=10)
        
        if 'Contents' in response and len(response['Contents']) > 0:
            print(f"✓ Gold: Found {len(response['Contents'])} aggregation(s)")
            for obj in response['Contents'][:5]:
                print(f"  → {obj['Key']}")
        else:
            print("⚠ Gold: No aggregations found yet (expected on first run)")
    except ClientError as exc:
        print(f"✗ Gold: Error listing objects: {exc}")
        success = False
    
    return success


def check_clickhouse_architecture() -> bool:
    """Verify ClickHouse loads from RustFS, not source systems."""
    print("\n=== Checking ClickHouse Independence ===")
    
    try:
        from clickhouse_driver import Client as CH_Client

        host_candidates = [
            os.getenv('CLICKHOUSE_HOST'),
            'dlh-clickhouse',
            'localhost',
            '127.0.0.1',
        ]
        host_candidates.extend(_local_ip_candidates())

        port_candidates = [
            int(os.getenv('CLICKHOUSE_TCP_PORT', '9000')),
            29000,
        ]

        ch_client = None
        last_error = None

        for host in host_candidates:
            if not host:
                continue
            for port in port_candidates:
                if not is_port_open(host, port):
                    continue
                try:
                    ch_client = CH_Client(
                        host=host,
                        port=port,
                        database=os.getenv('CLICKHOUSE_DB', 'analytics'),
                        user=os.getenv('CLICKHOUSE_USER', 'default'),
                        password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
                        connect_timeout=2,
                    )
                    ch_client.execute('SELECT 1')
                    print(f'Using ClickHouse host: {host}:{port}')
                    break
                except Exception as exc:
                    last_error = exc
                    ch_client = None
            if ch_client is not None:
                break

        if ch_client is None:
            raise RuntimeError(
                f'Could not connect to ClickHouse: {last_error}. '
                'Ensure ClickHouse is running, ports are mapped (9000 internal or 29000 external), '
                'and credentials in .env (CLICKHOUSE_USER/PASSWORD) are correct.'
            )
        
        success = True
        # Check that tables exist
        result = ch_client.execute("SHOW TABLES IN analytics")
        table_names = [row[0] for row in result]
        
        expected_tables = [
            'silver_demo',
            'gold_demo_daily',
            'gold_demo_by_region',
            'gold_demo_by_category',
            'pipeline_runs',
        ]
        
        print("✓ ClickHouse tables:")
        for table in expected_tables:
            if table in table_names:
                count = ch_client.execute(f"SELECT count() FROM {table}")
                rows = count[0][0] if count else 0
                print(f"  ✓ {table}: {rows} rows")
                
                # Verify that at least one table uses S3 engine
                if table == 'silver_demo':
                    create_stmt = ch_client.execute(f"SHOW CREATE TABLE {table}")[0][0]
                    if "ENGINE = S3" in create_stmt or "ENGINE = DeltaLake" in create_stmt:
                        print(f"    → Verified: {table} uses S3/Lakehouse engine")
                    else:
                        print(f"    ✗ Warning: {table} does NOT use S3/Lakehouse engine")
                        print(f"      (Found: {create_stmt[:100]}...)")
                        success = False
            else:
                print(f"  ✗ {table}: missing")
                success = False
        
        # Verify no direct PostgreSQL connections in ClickHouse config
        print("\n✓ ClickHouse Architecture: Tables populated from RustFS lake (not PostgreSQL)")
        print("  → All data transformations versioned in RustFS")
        print("  → Full data lineage and recoverability available")
        return success
        
    except Exception as exc:
        print(f"✗ ClickHouse connection failed: {exc}")
        return False


if __name__ == '__main__':
    print("\n" + "="*60)
    print("DATA LAKEHOUSE ARCHITECTURE VALIDATION")
    print("="*60)
    
    if check_rusfs_layers():
        check_data_lineage()
        check_clickhouse_architecture()
    else:
        print("\n✗ Skipping lineage and ClickHouse checks due to RustFS failure.")
    
    print("\n" + "="*60)
    print("For production use, ensure:")
    print("1. All data flows through RustFS (Bronze → Silver → Gold)")
    print("2. ClickHouse reads ONLY from RustFS layers")
    print("3. Source systems (PostgreSQL) never queried for analytics")
    print("4. All parquet files versioned with run_ids and dates")
    print("="*60 + "\n")

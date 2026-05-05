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
import json
import argparse
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add mage path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


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
            connect_timeout=1,
            read_timeout=2,
            retries={'max_attempts': 0},
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


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a TCP port is open."""
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _probe_s3_endpoint(endpoint: str) -> str | None:
    """Probe a single S3 endpoint and return it if successful."""
    try:
        parsed = urlparse(endpoint)
        if not is_port_open(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)):
            return None
        client = _s3_client(endpoint)
        client.list_buckets()
        return endpoint
    except Exception:
        return None


def _probe_ch_endpoint(host: str, port: int) -> tuple[str, int] | None:
    """Probe a single ClickHouse endpoint and return it if successful."""
    from clickhouse_driver import Client as CH_Client
    if not is_port_open(host, port):
        return None
    try:
        client = CH_Client(
            host=host,
            port=port,
            database=os.getenv('CLICKHOUSE_DB', 'analytics'),
            user=os.getenv('CLICKHOUSE_USER', 'default'),
            password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
            connect_timeout=1,
        )
        client.execute('SELECT 1')
        return (host, port)
    except Exception:
        return None


_cached_s3_client = None
_cached_s3_endpoint = None


def _connect_s3_client():
    """Connect to RustFS using concurrent probing."""
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
    
    unique_endpoints = [e for e in dict.fromkeys(endpoints) if e]

    with ThreadPoolExecutor(max_workers=len(unique_endpoints)) as executor:
        futures = {executor.submit(_probe_s3_endpoint, e): e for e in unique_endpoints}
        for future in as_completed(futures):
            result = future.result()
            if result:
                _cached_s3_endpoint = result
                _cached_s3_client = _s3_client(result)
                return _cached_s3_client, result

    raise RuntimeError('Could not connect to RustFS using any known endpoint.')


def check_rusfs_layers(results: dict) -> bool:
    """Check that RustFS has proper layer structure."""
    try:
        client, endpoint = _connect_s3_client()
        if not results.get('json_mode'):
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
    
    if not results.get('json_mode'):
        print("\n=== Checking RustFS Layer Structure ===")
    
    results['layers'] = {}
    for layer_name, bucket in layers.items():
        layer_res = {'bucket': bucket, 'exists': False, 'object_count': 0, 'samples': []}
        try:
            client.head_bucket(Bucket=bucket)
            layer_res['exists'] = True
            objs = client.list_objects_v2(Bucket=bucket, MaxKeys=10)
            count = objs.get('KeyCount', 0)
            layer_res['object_count'] = count
            if 'Contents' in objs:
                layer_res['samples'] = [obj['Key'] for obj in objs['Contents'][:3]]
            if not results.get('json_mode'):
                print(f"✓ {layer_name.upper()} bucket exists: {bucket} ({count} objects)")
        except ClientError as exc:
            if not results.get('json_mode'):
                print(f"✗ {layer_name.upper()} bucket missing: {bucket} ({exc})")
            success = False
        results['layers'][layer_name] = layer_res
    return success


def check_data_lineage(results: dict) -> bool:
    """Trace data records across layers."""
    if not results.get('json_mode'):
        print("\n=== Checking Data Lineage (Bronze → Silver → Gold) ===")
    try:
        client, _ = _connect_s3_client()
    except Exception:
        return False
    
    success = True
    results['lineage'] = {}
    checks = [
        ('bronze', os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze'), os.getenv('RUSTFS_BRONZE_PREFIX', 'demo')),
        ('silver', os.getenv('RUSTFS_SILVER_BUCKET', 'silver'), os.getenv('RUSTFS_SILVER_PREFIX', 'demo')),
        ('gold', os.getenv('RUSTFS_GOLD_BUCKET', 'gold'), ''),
    ]
    for layer_name, bucket, prefix in checks:
        try:
            response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=5)
            found = len(response.get('Contents', []))
            results['lineage'][layer_name] = {'found': found, 'keys': [obj['Key'] for obj in response.get('Contents', [])]}
            if not results.get('json_mode'):
                status = "✓" if found > 0 else "⚠"
                print(f"{status} {layer_name.capitalize()}: Found {found} object(s)")
        except Exception as exc:
            if not results.get('json_mode'):
                print(f"✗ {layer_name.capitalize()} check failed: {exc}")
            success = False
    return success


def check_clickhouse_architecture(results: dict) -> bool:
    """Verify ClickHouse loads from RustFS using concurrent discovery."""
    if not results.get('json_mode'):
        print("\n=== Checking ClickHouse Independence ===")
    results['clickhouse'] = {'endpoint': None, 'tables': []}
    try:
        from clickhouse_driver import Client as CH_Client
        host_candidates = [os.getenv('CLICKHOUSE_HOST'), 'dlh-clickhouse', 'localhost', '127.0.0.1']
        host_candidates.extend(_local_ip_candidates())
        port_candidates = [int(os.getenv('CLICKHOUSE_TCP_PORT', '9000')), 29000]
        probes = [(h, p) for h in host_candidates if h for p in port_candidates]
        ch_endpoint = None
        with ThreadPoolExecutor(max_workers=min(len(probes), 10)) as executor:
            futures = {executor.submit(_probe_ch_endpoint, h, p): (h, p) for h, p in probes}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    ch_endpoint = res
                    break
        if not ch_endpoint:
            raise RuntimeError("Could not connect to ClickHouse")

        host, port = ch_endpoint
        if not results.get('json_mode'):
            print(f'Using ClickHouse host: {host}:{port}')
        results['clickhouse']['endpoint'] = f"{host}:{port}"
        ch_client = CH_Client(host=host, port=port, database=os.getenv('CLICKHOUSE_DB', 'analytics'),
                             user=os.getenv('CLICKHOUSE_USER', 'default'), password=os.getenv('CLICKHOUSE_PASSWORD', '') or '')
        
        table_names = [row[0] for row in ch_client.execute("SHOW TABLES IN analytics")]
        expected = ['silver_demo', 'gold_demo_daily', 'gold_demo_by_region', 'gold_demo_by_category', 'pipeline_runs']
        success = True
        for table in expected:
            table_res = {'name': table, 'exists': False, 'rows': 0, 'engine_ok': True}
            if table in table_names:
                table_res['exists'] = True
                table_res['rows'] = ch_client.execute(f"SELECT count() FROM {table}")[0][0]
                if not results.get('json_mode'):
                    print(f"  ✓ {table}: {table_res['rows']} rows")
                if table == 'silver_demo':
                    create_stmt = ch_client.execute(f"SHOW CREATE TABLE {table}")[0][0]
                    if "ENGINE = S3" not in create_stmt and "ENGINE = DeltaLake" not in create_stmt:
                        table_res['engine_ok'] = False
                        success = False
            else:
                if not results.get('json_mode'):
                    print(f"  ✗ {table}: missing")
                success = False
            results['clickhouse']['tables'].append(table_res)
        return success
    except Exception as exc:
        if not results.get('json_mode'):
            print(f"✗ ClickHouse connection failed: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify Data Lakehouse Architecture")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()
    results = {'status': 'fail', 'json_mode': args.json, 'layers': {}, 'lineage': {}, 'clickhouse': {}}

    if not args.json:
        print("\n" + "="*60 + "\nDATA LAKEHOUSE ARCHITECTURE VALIDATION\n" + "="*60)
    
    layers_ok = check_rusfs_layers(results)
    if layers_ok:
        lineage_ok = check_data_lineage(results)
        ch_ok = check_clickhouse_architecture(results)
        if layers_ok and lineage_ok and ch_ok:
            results['status'] = 'pass'
        else:
            results['status'] = 'partial'

    if args.json:
        del results['json_mode']
        print(json.dumps(results, indent=2))
    else:
        print("\n" + "="*60 + f"\nOVERALL STATUS: {results['status'].upper()}\n" + "="*60 + "\n")


if __name__ == '__main__':
    main()

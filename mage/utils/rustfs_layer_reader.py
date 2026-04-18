"""
RustFS Lake Layer Reader – Utility to read latest data from Bronze/Silver/Gold layers.

Handles:
- Listing parquet files from a given layer (bucket/prefix)
- Reading latest dated partition
- Combining multiple run_id parquet files into single DataFrame
- Consistent timestamp handling across layers
"""

import os
import io
import datetime as dt
from typing import Optional

import boto3
import pandas as pd
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


def _s3_client():
    """Create S3 client for RustFS."""
    return boto3.client(
        's3',
        endpoint_url=os.getenv('RUSTFS_ENDPOINT_URL', 'http://dlh-rustfs:9000'),
        aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY', 'rustfsadmin'),
        aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY', 'rustfsadmin'),
        region_name=os.getenv('RUSTFS_REGION', 'us-east-1'),
        config=BotoConfig(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
        ),
    )


def list_layer_partitions(bucket: str, prefix: str) -> list[str]:
    """
    List all dt=YYYY-MM-DD partitions under a layer prefix.
    Returns sorted list of dates (newest first).
    """
    client = _s3_client()
    partitions = set()
    
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        for page in pages:
            if 'Contents' not in page:
                continue
            for obj in page['Contents']:
                key = obj['Key']
                # Extract dt=YYYY-MM-DD from path
                if '/dt=' in key:
                    parts = key.split('/dt=')
                    if len(parts) > 1:
                        date_part = parts[1].split('/')[0]
                        partitions.add(date_part)
    except ClientError:
        pass
    
    return sorted(partitions, reverse=True)


def read_latest_layer(bucket: str, prefix: str, date_str: Optional[str] = None) -> pd.DataFrame:
    """
    Read all parquet files from a specific date partition or latest date.
    
    Returns combined DataFrame from all run_id parquet files in that partition.
    """
    if not date_str:
        # Get latest partition
        partitions = list_layer_partitions(bucket, prefix)
        if not partitions:
            return pd.DataFrame()
        date_str = partitions[0]
    
    layer_path = f'{prefix}/dt={date_str}'
    client = _s3_client()
    dfs = []
    
    try:
        response = client.list_objects_v2(Bucket=bucket, Prefix=layer_path)
        if 'Contents' not in response:
            return pd.DataFrame()
        
        for obj in response['Contents']:
            key = obj['Key']
            if key.endswith('.parquet'):
                # Read parquet file
                obj_response = client.get_object(Bucket=bucket, Key=key)
                buffer = io.BytesIO(obj_response['Body'].read())
                df = pd.read_parquet(buffer, engine='pyarrow')
                dfs.append(df)
                print(f"[read_latest_layer] Read {len(df)} rows from s3://{bucket}/{key}")
    
    except ClientError as exc:
        print(f"[read_latest_layer] Error reading s3://{bucket}/{layer_path}: {exc}")
        return pd.DataFrame()
    
    if not dfs:
        return pd.DataFrame()
    
    result = pd.concat(dfs, ignore_index=True)
    print(f"[read_latest_layer] Combined {len(result)} rows from {len(dfs)} files")
    return result


def read_latest_bronze(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Bronze layer data."""
    bucket = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')
    prefix = os.getenv('RUSTFS_BRONZE_PREFIX', 'demo')
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_silver(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Silver layer data."""
    bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    prefix = os.getenv('RUSTFS_SILVER_PREFIX', 'demo')
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_gold_daily(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold daily aggregation layer."""
    bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    prefix = os.getenv('RUSTFS_GOLD_PREFIX', 'demo_daily')
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_gold_region(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold by-region aggregation layer."""
    bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    prefix = os.getenv('RUSTFS_GOLD_PREFIX', 'demo_by_region')
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_gold_category(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold by-category aggregation layer."""
    bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    prefix = os.getenv('RUSTFS_GOLD_PREFIX', 'demo_by_category')
    return read_latest_layer(bucket, prefix, date_str)


def read_all_gold() -> dict:
    """Read all Gold layer tables as a dict."""
    return {
        'gold_daily': read_latest_gold_daily(),
        'gold_region': read_latest_gold_region(),
        'gold_category': read_latest_gold_category(),
    }


def read_latest_csv_silver(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest CSV Silver layer data (cleaned uploaded CSV)."""
    bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    prefix = os.getenv('RUSTFS_CSV_SILVER_PREFIX', 'csv_upload')
    return read_latest_layer(bucket, prefix, date_str)

"""
Data Exporter – Save cleaned CSV to RustFS Silver layer.

This is part of proper lakehouse architecture:
  CSV (Bronze) → Clean → Silver → ClickHouse
  
All data must be versioned in RustFS, not passed in-memory.
"""

import io
import os
import datetime as dt

import pandas as pd
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


def _s3_client():
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


def _ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = str(exc.response.get('Error', {}).get('Code', ''))
        if code not in {'404', 'NoSuchBucket', 'NotFound'}:
            raise
        client.create_bucket(Bucket=bucket)


@data_exporter
def export_csv_silver(data, *args, **kwargs):
    """Save cleaned CSV data to RustFS Silver layer."""
    if not isinstance(data, dict) or data.get('skip'):
        return data
    
    cleaned_df = data.get('cleaned_dataframe')
    if cleaned_df is None or len(cleaned_df) == 0:
        return data
    
    run_id = data.get('pipeline_run_id', 'unknown')
    source_key = data.get('source_key', 'unknown')
    
    bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    date_str = dt.date.today().isoformat()
    key = f'csv_upload/dt={date_str}/{run_id}.parquet'
    
    # Prepare dataframe for parquet export
    df_export = cleaned_df.copy()
    for col in df_export.select_dtypes(include=['object']).columns:
        df_export[col] = df_export[col].astype(str).replace({'None': None, 'nan': None})
    
    buffer = io.BytesIO()
    df_export.to_parquet(buffer, index=False, engine='pyarrow')
    buffer.seek(0)
    
    client = _s3_client()
    _ensure_bucket(client, bucket)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/octet-stream',
    )
    
    print(
        f"[csv_to_rustfs_silver] Saved {len(cleaned_df)} rows "
        f"from {source_key} → s3://{bucket}/{key}"
    )
    
    return data


@test
def test_output(output, *args):
    assert output is not None, 'Output is None'
    if isinstance(output, dict) and not output.get('skip'):
        assert 'cleaned_dataframe' in output, 'Missing cleaned_dataframe'

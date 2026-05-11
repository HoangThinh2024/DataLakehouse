"""
Data Exporter – Upload cleaned Excel (Silver) data to RustFS.
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

def _s3_client():
    return boto3.client(
        's3',
        endpoint_url=os.getenv('RUSTFS_ENDPOINT_URL', 'http://dlh-rustfs:9000'),
        aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY', 'rustfsadmin'),
        aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY', 'rustfsadmin'),
        region_name=os.getenv('RUSTFS_REGION', 'us-east-1'),
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}),
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
def export_silver(data, *args, **kwargs):
    # Guard malformed payloads to keep pipeline resilient across integration changes.
    if not isinstance(data, dict):
        print(f"[excel_silver_to_rustfs] Skip run - invalid payload type: {type(data)}")
        return data
    if data.get('skip'):
        return data

    df = data.get('dataframe')
    if not isinstance(df, pd.DataFrame):
        print("[excel_silver_to_rustfs] Skip upload - missing or invalid dataframe payload.")
        return data
    if df.empty:
        print("[excel_silver_to_rustfs] Skip upload - dataframe is empty.")
        return data

    df = df.copy()
    bucket = os.getenv('RUSTFS_SILVER_BUCKET', 'silver')
    prefix = 'excel_projects'
    run_id = data.get('pipeline_run_id', 'unknown')
    date_str = dt.date.today().isoformat()
    key = f'{prefix}/dt={date_str}/{run_id}.parquet'

    # Convert objects to strings for Parquet
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).replace({'None': None, 'nan': None})

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine='pyarrow')
    buffer.seek(0)

    client = _s3_client()
    _ensure_bucket(client, bucket)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/octet-stream'
    )

    print(f"[excel_silver_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")
    return data

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

@data_exporter
def export_silver(data, *args, **kwargs):
    if data.get('skip'):
        return data

    df = data['dataframe'].copy()
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
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/octet-stream'
    )

    print(f"[excel_silver_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")
    return data

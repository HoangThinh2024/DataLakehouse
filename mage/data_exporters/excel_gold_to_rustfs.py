"""
Data Exporter – Upload Project Gold data to RustFS.
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

def _upload_df(client, bucket, key, df):
    if df is None or len(df) == 0: return
    # Convert objects to strings for Parquet
    df_export = df.copy()
    for col in df_export.select_dtypes(include=['object']).columns:
        df_export[col] = df_export[col].astype(str).replace({'None': None, 'nan': None})
        
    buffer = io.BytesIO()
    df_export.to_parquet(buffer, index=False, engine='pyarrow')
    buffer.seek(0)
    client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    print(f"[excel_gold_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")

@data_exporter
def export_gold(data, *args, **kwargs):
    if not isinstance(data, dict) or data.get('skip'): return data
    
    bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    run_id = data.get('pipeline_run_id', 'unknown')
    date_str = dt.date.today().isoformat()
    client = _s3_client()

    if 'gold_projects' in data:
        _upload_df(client, bucket, f'projects/dt={date_str}/{run_id}.parquet', data['gold_projects'])
    if 'gold_workload' in data:
        _upload_df(client, bucket, f'workload/dt={date_str}/{run_id}.parquet', data['gold_workload'])

    return data

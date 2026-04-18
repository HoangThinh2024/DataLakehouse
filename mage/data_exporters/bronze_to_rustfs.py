"""
Data Exporter – Upload raw (Bronze) data to RustFS.

Saves the raw extract as a Parquet file under:
  bronze/demo/dt=YYYY-MM-DD/<run_id>.parquet

Passes the DataFrame through unchanged so downstream blocks receive it.
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
def export_bronze(df: pd.DataFrame, *args, **kwargs):
    bucket = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')
    prefix = os.getenv('RUSTFS_BRONZE_PREFIX', 'demo')
    run_id = df['_pipeline_run_id'].iloc[0] if '_pipeline_run_id' in df.columns else 'unknown'
    date_str = dt.date.today().isoformat()
    key = f'{prefix}/dt={date_str}/{run_id}.parquet'

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine='pyarrow')
    buffer.seek(0)

    client = _s3_client()
    _ensure_bucket(client, bucket)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/octet-stream',
    )

    print(f"[bronze_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Output is None after bronze export'
    assert len(output) > 0, 'Empty DataFrame after bronze export'

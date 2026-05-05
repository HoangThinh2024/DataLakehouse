"""
Data Exporter – Upload raw (Bronze) data to RustFS.

Saves the raw extract as a Parquet file under:
  bronze/demo/dt=YYYY-MM-DD/<run_id>.parquet

A content-hash (SHA-256 over business columns only) is stored as S3 object
metadata.  If the same hash is found on an existing file for today's
partition the upload is skipped to avoid accumulating identical copies.

Passes the DataFrame through unchanged so downstream blocks receive it.
"""

import hashlib
import io
import os
import datetime as dt
from typing import Optional

import pandas as pd
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test

# Metadata columns that change on every run and must be excluded from the
# content hash so that "same business data, new run" is still detected as
# unchanged.
_RUN_META_COLS = {'_pipeline_run_id', '_source_table', '_extracted_at'}


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


def _compute_content_hash(df: pd.DataFrame) -> str:
    """Compute a deterministic SHA-256 hash over business columns only.

    Excludes run-specific metadata columns so the hash is stable across
    multiple pipeline executions that extract the same source data.
    Uses JSON serialisation with sorted keys for consistent output.
    """
    biz_cols = sorted([c for c in df.columns if c not in _RUN_META_COLS])
    if not biz_cols:
        return ''
    df_biz = df[biz_cols].copy()
    for col in df_biz.select_dtypes(include=['object']).columns:
        df_biz[col] = df_biz[col].astype(str)
    # Sort rows by all business columns for a deterministic order, then
    # serialise to JSON so the hash is independent of row insertion order.
    df_sorted = df_biz.sort_values(biz_cols, na_position='first').reset_index(drop=True)
    payload = df_sorted.to_json(orient='records', date_format='iso', default_handler=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _existing_hash_for_partition(client, bucket: str, prefix: str, date_str: str) -> Optional[str]:
    """Return the content-sha256 stored on the latest object in today's partition, or None."""
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=f'{prefix}/dt={date_str}/')
        objects = [o for o in resp.get('Contents', []) if o.get('Key', '').endswith('.parquet')]
        if not objects:
            return None
        latest = max(objects, key=lambda o: (o.get('LastModified'), o.get('Key', '')))
        head = client.head_object(Bucket=bucket, Key=latest['Key'])
        return head.get('Metadata', {}).get('content-sha256')
    except Exception:
        return None


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
    content = buffer.getvalue()

    client = _s3_client()
    _ensure_bucket(client, bucket)

    # Skip upload when business data is identical to the latest file already
    # stored for today's partition (avoids accumulating redundant copies).
    content_hash = _compute_content_hash(df)
    existing_hash = _existing_hash_for_partition(client, bucket, prefix, date_str)
    if content_hash and existing_hash == content_hash:
        print(
            f'[bronze_to_rustfs] Skipping upload – data unchanged for {date_str} '
            f'(hash={content_hash[:12]})'
        )
        return df

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType='application/octet-stream',
        Metadata={'content-sha256': content_hash},
    )

    print(f"[bronze_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Output is None after bronze export'
    assert len(output) > 0, 'Empty DataFrame after bronze export'

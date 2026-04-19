"""
Data Exporter – Upload Gold aggregated data to RustFS.

Saves six Parquet files under:
  gold/demo_daily/dt=YYYY-MM-DD/<run_id>.parquet
  gold/demo_weekly/dt=YYYY-MM-DD/<run_id>.parquet
  gold/demo_monthly/dt=YYYY-MM-DD/<run_id>.parquet
  gold/demo_yearly/dt=YYYY-MM-DD/<run_id>.parquet
  gold/demo_by_region/dt=YYYY-MM-DD/<run_id>.parquet
  gold/demo_by_category/dt=YYYY-MM-DD/<run_id>.parquet
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


def _upload_df(client, bucket: str, key: str, df: pd.DataFrame) -> None:
    if df is None or len(df) == 0:
        print(f"[gold_to_rustfs] Skipping empty DataFrame for key: {key}")
        return

    df_export = df.copy()
    for col in df_export.select_dtypes(include=['object']).columns:
        df_export[col] = df_export[col].astype(str).replace({'None': None, 'nan': None})

    buffer = io.BytesIO()
    df_export.to_parquet(buffer, index=False, engine='pyarrow')
    buffer.seek(0)

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/octet-stream',
    )
    print(f"[gold_to_rustfs] Uploaded {len(df)} rows → s3://{bucket}/{key}")


@data_exporter
def export_gold(data, *args, **kwargs):
    bucket = os.getenv('RUSTFS_GOLD_BUCKET', 'gold')
    date_str = dt.date.today().isoformat()

    gold_daily = data.get('gold_daily', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    gold_weekly = data.get('gold_weekly', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    gold_monthly = data.get('gold_monthly', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    gold_yearly = data.get('gold_yearly', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    gold_region = data.get('gold_region', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    gold_category = data.get('gold_category', pd.DataFrame()) if isinstance(data, dict) else pd.DataFrame()
    run_id = (
        gold_daily['_pipeline_run_id'].iloc[0]
        if isinstance(gold_daily, pd.DataFrame) and len(gold_daily) > 0 and '_pipeline_run_id' in gold_daily.columns
        else 'unknown'
    )

    client = _s3_client()
    _ensure_bucket(client, bucket)

    _upload_df(client, bucket, f'demo_daily/dt={date_str}/{run_id}.parquet', gold_daily)
    _upload_df(client, bucket, f'demo_weekly/dt={date_str}/{run_id}.parquet', gold_weekly)
    _upload_df(client, bucket, f'demo_monthly/dt={date_str}/{run_id}.parquet', gold_monthly)
    _upload_df(client, bucket, f'demo_yearly/dt={date_str}/{run_id}.parquet', gold_yearly)
    _upload_df(client, bucket, f'demo_by_region/dt={date_str}/{run_id}.parquet', gold_region)
    _upload_df(client, bucket, f'demo_by_category/dt={date_str}/{run_id}.parquet', gold_category)

    return data


@test
def test_output(output, *args):
    assert output is not None, 'Gold export returned None'

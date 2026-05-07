"""
Data Loader - Fetch newest unprocessed Excel from RustFS.

Scans a configured bucket, picks the earliest unprocessed Excel file (.xlsx),
reads it into a DataFrame, and attaches ingestion metadata.
"""

import io
import os
import uuid
import datetime as dt

import boto3
import pandas as pd
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from clickhouse_driver import Client

if 'data_loader' not in dir():
    from mage_ai.data_preparation.decorators import data_loader
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


def _s3_client():
    return boto3.client(
        's3',
        endpoint_url=os.getenv('RUSTFS_ENDPOINT_URL', 'http://dlh-rustfs:9000'),
        aws_access_key_id=os.getenv('RUSTFS_ACCESS_KEY', 'rustfsadmin'),
        aws_secret_access_key=os.getenv('RUSTFS_SECRET_KEY', 'rustfsadmin'),
        region_name=os.getenv('RUSTFS_REGION', 'us-east-1'),
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )


def _ch_client() -> Client:
    return Client(
        host=os.getenv('CLICKHOUSE_HOST', 'dlh-clickhouse'),
        port=int(os.getenv('CLICKHOUSE_TCP_PORT', '9000')),
        database=os.getenv('CLICKHOUSE_DB', 'analytics'),
        user=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
        connect_timeout=15,
        send_receive_timeout=120,
    )


def _ensure_tables(client: Client, db: str) -> None:
    statements = [
        f'CREATE DATABASE IF NOT EXISTS {db}',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.excel_upload_events
        (
            source_key String,
            etag String,
            source_size Int64,
            source_last_modified Nullable(DateTime64(3)),
            status String,
            row_count Int64 DEFAULT 0,
            processed_at DateTime64(3) DEFAULT now64(3),
            pipeline_run_id String DEFAULT '',
            error_message Nullable(String)
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(processed_at)
        ORDER BY (source_key, etag, processed_at)
        ''',
    ]
    for stmt in statements:
        client.execute(stmt)


def _already_processed(client: Client, db: str, source_key: str, etag: str) -> bool:
    rows = client.execute(
        f'SELECT count() FROM {db}.excel_upload_events '
        'WHERE source_key = %(source_key)s AND etag = %(etag)s AND status = %(status)s',
        {'source_key': source_key, 'etag': etag, 'status': 'success'},
    )
    return bool(rows and rows[0][0] > 0)


@data_loader
def load_data(*args, **kwargs):
    bucket = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')
    max_scan = int(os.getenv('CSV_UPLOAD_SCAN_LIMIT', '200'))

    s3_client = _s3_client()
    ch_client = _ch_client()
    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    _ensure_tables(ch_client, db)

    objects = []
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, MaxKeys=max_scan)
        objects = [
            obj for obj in response.get('Contents', [])
            if obj.get('Key', '').lower().endswith('.xlsx')
        ]
    except Exception as e:
        print(f'[extract_excel_from_rustfs] S3 scan failed: {e}')
        return {'skip': True, 'message': f'S3 scan error: {e}'}

    if not objects:
        print(f'[extract_excel_from_rustfs] No new Excel found at s3://{bucket}')
        return {'skip': True, 'message': 'no new excel'}

    objects.sort(key=lambda x: (x.get('LastModified'), x.get('Key', '')))

    selected_objects = []
    for obj in objects:
        source_key = obj.get('Key', '')
        etag = str(obj.get('ETag', '')).strip('"')
        if not source_key or not etag:
            continue
        if not _already_processed(ch_client, db, source_key, etag):
            selected_objects.append(obj)

    if not selected_objects:
        print(f'[extract_excel_from_rustfs] No new Excel found at s3://{bucket} or local path')
        return {'skip': True, 'message': 'no new excel'}

    all_dfs = []
    processed_files = []
    
    for selected in selected_objects:
        source_key = selected['Key']
        etag = str(selected.get('ETag', '')).strip('"')
        last_modified = selected.get('LastModified')
        size = int(selected.get('Size', 0))
        run_id = str(uuid.uuid4())

        obj = s3_client.get_object(Bucket=bucket, Key=source_key)
        body = obj['Body'].read()
            
        df = pd.read_excel(io.BytesIO(body), engine='openpyxl')

        now_utc = dt.datetime.utcnow().isoformat() + 'Z'
        df['_pipeline_run_id'] = run_id
        df['_source_table'] = 'excel_upload'
        df['_source_file_key'] = source_key
        df['_source_file_etag'] = etag
        df['_extracted_at'] = now_utc
        
        all_dfs.append(df)
        processed_files.append({
            'source_key': source_key,
            'source_etag': etag,
            'source_size': size,
            'source_last_modified': last_modified.isoformat() if last_modified else None,
            'pipeline_run_id': run_id
        })

    # Combine all Excel files into one massive dataframe for this run
    final_df = pd.concat(all_dfs, ignore_index=True)
    run_group_id = str(uuid.uuid4())

    print(
        f'[extract_excel_from_rustfs] Batch processed {len(processed_files)} files, '
        f'total rows: {len(final_df)}'
    )

    return {
        'skip': False,
        'dataframe': final_df,
        'bucket': bucket,
        'processed_files': processed_files, # For logging
        'pipeline_run_id': run_group_id,
        'raw_rows': len(final_df),
        # Legacy fields for backward compatibility with single-file exporters
        'source_key': processed_files[0]['source_key'],
        'source_etag': processed_files[0]['source_etag'],
        'source_size': processed_files[0]['source_size'],
        'source_last_modified': processed_files[0]['source_last_modified'],
    }


@test
def test_output(output, *args):
    assert output is not None, 'Output is None'
    if not output.get('skip'):
        assert 'dataframe' in output, 'Missing dataframe in output'
        assert len(output['dataframe']) > 0, 'Excel dataframe is empty'

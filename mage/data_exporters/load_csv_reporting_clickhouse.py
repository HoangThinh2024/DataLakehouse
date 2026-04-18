"""
Data Exporter - Write cleaned CSV rows and quality metrics to ClickHouse.

Tables created/used:
- analytics.csv_clean_rows
- analytics.csv_quality_metrics
- analytics.csv_upload_events
- analytics.pipeline_runs
"""

import os
import json
import datetime as dt
from typing import Any

import pandas as pd
from clickhouse_driver import Client

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


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
        CREATE TABLE IF NOT EXISTS {db}.csv_clean_rows
        (
            pipeline_run_id String,
            source_key String,
            source_etag String,
            source_last_modified Nullable(DateTime64(3)),
            row_number UInt64,
            row_json String,
            processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(processed_at)
        ORDER BY (processed_at, source_key, row_number)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.csv_quality_metrics
        (
            pipeline_run_id String,
            source_key String,
            source_etag String,
            raw_rows Int64,
            cleaned_rows Int64,
            dropped_rows Int64,
            duplicate_rows Int64,
            null_cells Int64,
            processed_at DateTime64(3)
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(processed_at)
        ORDER BY (processed_at, source_key)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.csv_upload_events
        (
            source_key String,
            etag String,
            source_size Int64,
            source_last_modified Nullable(DateTime64(3)),
            status String,
            row_count Int64 DEFAULT 0,
            duplicate_rows Int64 DEFAULT 0,
            dropped_rows Int64 DEFAULT 0,
            processed_at DateTime64(3) DEFAULT now64(3),
            pipeline_run_id String DEFAULT '',
            error_message Nullable(String)
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(processed_at)
        ORDER BY (source_key, etag, processed_at)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.pipeline_runs
        (
            run_id String,
            pipeline_name String,
            status String,
            started_at DateTime64(3),
            ended_at Nullable(DateTime64(3)),
            rows_extracted Int64 DEFAULT 0,
            rows_silver Int64 DEFAULT 0,
            rows_gold_daily Int64 DEFAULT 0,
            rows_gold_region Int64 DEFAULT 0,
            rows_gold_category Int64 DEFAULT 0,
            error_message Nullable(String),
            _created_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(started_at)
        ORDER BY started_at
        ''',
    ]
    for stmt in statements:
        client.execute(stmt)


def _to_iso_datetime(value: Any):
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


@data_exporter
def export_data(data, *args, **kwargs):
    if not isinstance(data, dict) or data.get('skip'):
        print('[load_csv_reporting_clickhouse] Skip run - no new CSV file.')
        return data

    client = _ch_client()
    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    _ensure_tables(client, db)

    started_at = dt.datetime.utcnow()
    run_id = data.get('pipeline_run_id', 'unknown')
    source_key = data.get('source_key', '')
    source_etag = data.get('source_etag', '')
    source_size = int(data.get('source_size', 0))
    source_last_modified = _to_iso_datetime(data.get('source_last_modified'))

    metrics = data.get('quality_metrics', {})
    cleaned_df = data.get('cleaned_dataframe', pd.DataFrame())
    error_msg = None

    try:
        rows_payload = []
        payload_df = cleaned_df.copy()
        if '_row_number' not in payload_df.columns:
            payload_df['_row_number'] = range(1, len(payload_df) + 1)

        for _, row in payload_df.iterrows():
            row_number = int(row.get('_row_number', 0))
            row_dict = {
                k: v for k, v in row.to_dict().items()
                if k != '_row_number'
            }
            for key, val in row_dict.items():
                if not isinstance(val, (list, dict)) and pd.isna(val):
                    row_dict[key] = None
            rows_payload.append({
                'pipeline_run_id': run_id,
                'source_key': source_key,
                'source_etag': source_etag,
                'source_last_modified': source_last_modified,
                'row_number': row_number,
                'row_json': json.dumps(row_dict, default=str),
                'processed_at': started_at,
            })

        if rows_payload:
            client.execute(
                f'INSERT INTO {db}.csv_clean_rows '
                '(pipeline_run_id, source_key, source_etag, source_last_modified, row_number, row_json, processed_at) VALUES',
                rows_payload,
            )

        quality_row = [{
            'pipeline_run_id': run_id,
            'source_key': source_key,
            'source_etag': source_etag,
            'raw_rows': int(metrics.get('raw_rows', 0)),
            'cleaned_rows': int(metrics.get('cleaned_rows', len(cleaned_df))),
            'dropped_rows': int(metrics.get('dropped_rows', 0)),
            'duplicate_rows': int(metrics.get('duplicate_rows', 0)),
            'null_cells': int(metrics.get('null_cells', 0)),
            'processed_at': _to_iso_datetime(metrics.get('processed_at')) or started_at,
        }]
        client.execute(
            f'INSERT INTO {db}.csv_quality_metrics '
            '(pipeline_run_id, source_key, source_etag, raw_rows, cleaned_rows, dropped_rows, duplicate_rows, null_cells, processed_at) VALUES',
            quality_row,
        )

        client.execute(
            f'INSERT INTO {db}.csv_upload_events '
            '(source_key, etag, source_size, source_last_modified, status, row_count, duplicate_rows, dropped_rows, processed_at, pipeline_run_id, error_message) VALUES',
            [{
                'source_key': source_key,
                'etag': source_etag,
                'source_size': source_size,
                'source_last_modified': source_last_modified,
                'status': 'success',
                'row_count': int(metrics.get('cleaned_rows', len(cleaned_df))),
                'duplicate_rows': int(metrics.get('duplicate_rows', 0)),
                'dropped_rows': int(metrics.get('dropped_rows', 0)),
                'processed_at': started_at,
                'pipeline_run_id': run_id,
                'error_message': None,
            }],
        )

        ended_at = dt.datetime.utcnow()
        client.execute(
            f'INSERT INTO {db}.pipeline_runs '
            '(run_id, pipeline_name, status, started_at, ended_at, rows_extracted, rows_silver, rows_gold_daily, rows_gold_region, rows_gold_category, error_message) VALUES',
            [{
                'run_id': run_id,
                'pipeline_name': 'etl_csv_upload_to_reporting',
                'status': 'success',
                'started_at': started_at,
                'ended_at': ended_at,
                'rows_extracted': int(metrics.get('raw_rows', 0)),
                'rows_silver': int(metrics.get('cleaned_rows', len(cleaned_df))),
                'rows_gold_daily': 0,
                'rows_gold_region': 0,
                'rows_gold_category': 0,
                'error_message': None,
            }],
        )

        print(
            f"[load_csv_reporting_clickhouse] run_id={run_id} source={source_key} "
            f"raw={metrics.get('raw_rows', 0)} cleaned={metrics.get('cleaned_rows', len(cleaned_df))}"
        )

    except Exception as exc:
        error_msg = str(exc)
        client.execute(
            f'INSERT INTO {db}.csv_upload_events '
            '(source_key, etag, source_size, source_last_modified, status, row_count, duplicate_rows, dropped_rows, processed_at, pipeline_run_id, error_message) VALUES',
            [{
                'source_key': source_key,
                'etag': source_etag,
                'source_size': source_size,
                'source_last_modified': source_last_modified,
                'status': 'failed',
                'row_count': 0,
                'duplicate_rows': 0,
                'dropped_rows': 0,
                'processed_at': dt.datetime.utcnow(),
                'pipeline_run_id': run_id,
                'error_message': error_msg,
            }],
        )
        raise

    return data


@test
def test_output(output, *args):
    assert output is not None, 'Output is None'

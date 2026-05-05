"""
Data Exporter – Load Silver and Gold data into ClickHouse.

PROPER LAKEHOUSE ARCHITECTURE:
  - Reads Silver data from RustFS silver layer (not in-memory)
  - Reads Gold data from RustFS gold layer (not in-memory)
  - Loads into ClickHouse:
    - analytics.silver_demo
    - analytics.gold_demo_daily, gold_demo_by_region, gold_demo_by_category
    - analytics.pipeline_runs (run metadata)

This ensures:
  - All data transformations are versioned in RustFS
  - Data lineage is traceable
  - ClickHouse never queries PostgreSQL directly (lake is single source of truth)
  - Full recoverability: can always re-read from RustFS
  - Duplicate prevention: TRUNCATE + full-refresh each run so old run data
    never accumulates; pre-insert dedup by business keys as a safety net.

Uses clickhouse-driver for the native TCP protocol (port 9000).
"""

import os
import sys
import datetime as dt
from typing import Any

import pandas as pd
from clickhouse_driver import Client

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test

# Import RustFS layer reader
project_root = os.getenv('MAGE_PROJECT_PATH', os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from utils.rustfs_layer_reader import read_latest_silver, read_all_gold


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


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to plain dicts safe for ClickHouse driver."""
    records = []
    for row in df.itertuples(index=False):
        record: dict[str, Any] = {}
        for field, value in zip(df.columns, row):
            if hasattr(value, 'item'):          # numpy scalar
                value = value.item()
            if not isinstance(value, (list, dict)) and pd.isna(value):
                value = None
            record[field] = value
        records.append(record)
    return records


def _insert(client: Client, table: str, df: pd.DataFrame, columns: list[str]) -> int:
    """Insert only the requested columns from df into table. Returns row count."""
    if df is None or len(df) == 0:
        return 0

    present = [c for c in columns if c in df.columns]
    df_insert = df[present].copy()

    datetime_cols = {
        'created_at', '_silver_processed_at', '_gold_processed_at',
        'started_at', 'ended_at', '_extracted_at',
    }
    date_cols = {'order_date', 'report_date', 'week_start', 'month_start'}

    # Keep temporal columns as python datetime/date objects for ClickHouse typing.
    for col in [c for c in present if c in datetime_cols]:
        ser = pd.to_datetime(df_insert[col], errors='coerce', utc=True)
        df_insert[col] = ser.dt.to_pydatetime()
        df_insert.loc[ser.isna(), col] = None

    for col in [c for c in present if c in date_cols]:
        ser = pd.to_datetime(df_insert[col], errors='coerce')
        df_insert[col] = ser.dt.date
        df_insert.loc[ser.isna(), col] = None

    # Stringify remaining object columns only.
    for col in df_insert.select_dtypes(include=['object']).columns:
        if col in datetime_cols or col in date_cols:
            continue
        df_insert[col] = df_insert[col].astype(str).replace({'None': None, 'nan': None, 'NaT': None})

    records = _to_records(df_insert)
    if records:
        client.execute(f'INSERT INTO {table} ({", ".join(present)}) VALUES', records)
    return len(records)


def _ensure_clickhouse_objects(client: Client, db: str) -> None:
    """Create required database/tables with ReplacingMergeTree for idempotency.

    ORDER BY keys deliberately exclude _pipeline_run_id so that
    ReplacingMergeTree can collapse multiple runs for the same business key
    into a single row (keeping the latest _db_processed_at version).
    """
    ddl = [
        f'CREATE DATABASE IF NOT EXISTS {db}',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.silver_demo
        (
            id Int64,
            name Nullable(String),
            category Nullable(String),
            value Nullable(Float64),
            quantity Nullable(Int32),
            order_date Date,
            region Nullable(String),
            status Nullable(String),
            customer_email Nullable(String),
            notes Nullable(String),
            created_at Nullable(DateTime64(3)),
            _pipeline_run_id String DEFAULT '',
            _source_table String DEFAULT 'Demo',
            _silver_processed_at DateTime64(3) DEFAULT now64(3),
            _db_processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_processed_at)
        ORDER BY (order_date, id)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.gold_demo_daily
        (
            order_date Date,
            order_count Int64,
            total_revenue Float64,
            avg_order_value Float64,
            total_quantity Int64,
            unique_customers Int64,
            unique_regions Int64,
            unique_categories Int64,
            _pipeline_run_id String DEFAULT '',
            _gold_processed_at DateTime64(3) DEFAULT now64(3),
            _db_processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_processed_at)
        ORDER BY (order_date)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.gold_demo_by_region
        (
            region String,
            order_count Int64,
            total_revenue Float64,
            avg_order_value Float64,
            total_quantity Int64,
            report_date Date,
            _pipeline_run_id String DEFAULT '',
            _gold_processed_at DateTime64(3) DEFAULT now64(3),
            _db_processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_processed_at)
        ORDER BY (region, report_date)
        ''',
        f'''
        CREATE TABLE IF NOT EXISTS {db}.gold_demo_by_category
        (
            category String,
            order_count Int64,
            total_revenue Float64,
            avg_order_value Float64,
            total_quantity Int64,
            report_date Date,
            _pipeline_run_id String DEFAULT '',
            _gold_processed_at DateTime64(3) DEFAULT now64(3),
            _db_processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_processed_at)
        ORDER BY (category, report_date)
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
    for statement in ddl:
        client.execute(statement)


def _truncate_analytics_tables(client: Client, db: str) -> None:
    """Truncate analytics tables before full-refresh to prevent cross-run duplicates.

    ClickHouse is the serving layer; RustFS is the source of truth.
    A full-refresh (TRUNCATE + INSERT) is correct and keeps storage bounded.
    """
    for tbl in ['silver_demo', 'gold_demo_daily', 'gold_demo_by_region', 'gold_demo_by_category']:
        try:
            client.execute(f'TRUNCATE TABLE {db}.{tbl}')
        except Exception as exc:
            print(f'[load_to_clickhouse] TRUNCATE {db}.{tbl} warning: {exc}')


def _dedup_by_keys(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Deduplicate DataFrame by business keys, keeping the most recent row.

    Sorts by _db_processed_at (if present) so the latest version survives.
    This is a safety net before INSERT even though TRUNCATE already removes old runs.
    """
    if df is None or len(df) == 0:
        return df
    present_keys = [k for k in keys if k in df.columns]
    if not present_keys:
        return df
    before = len(df)
    sort_col = '_db_processed_at' if '_db_processed_at' in df.columns else (
        '_silver_processed_at' if '_silver_processed_at' in df.columns else None
    )
    if sort_col:
        df = df.sort_values(sort_col, ascending=True, na_position='first')
    df = df.drop_duplicates(subset=present_keys, keep='last').reset_index(drop=True)
    removed = before - len(df)
    if removed:
        print(f'[load_to_clickhouse] Pre-insert dedup ({present_keys}): removed {removed} duplicates')
    return df


@data_exporter
def load_clickhouse(data, *args, **kwargs):
    """Load latest Silver and Gold data from RustFS into ClickHouse.

    Uses TRUNCATE + full-refresh to guarantee no cross-run duplicates.
    Pre-insert dedup by business keys guards against within-run duplicates.
    """
    started_at = dt.datetime.now(dt.timezone.utc)
    client = _ch_client()
    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    _ensure_clickhouse_objects(client, db)

    rows_silver = rows_daily = rows_region = rows_category = 0
    error_msg = None
    run_id = 'auto-load'
    status = 'unknown'

    try:
        # 1. Read Silver and Gold from RustFS BEFORE truncating, so we only
        #    truncate when we have data to replace the tables with.
        silver_df = read_latest_silver()
        gold_data = read_all_gold()
        gold_daily = gold_data.get('gold_daily', pd.DataFrame())
        gold_region = gold_data.get('gold_region', pd.DataFrame())
        gold_category = gold_data.get('gold_category', pd.DataFrame())

        # 2. Truncate analytics tables for a clean full-refresh (prevents
        #    duplicate rows accumulating across pipeline runs).
        _truncate_analytics_tables(client, db)

        # 3. Insert Silver (deduplicated by business key first)
        if len(silver_df) > 0:
            if '_pipeline_run_id' in silver_df.columns:
                run_id = silver_df['_pipeline_run_id'].iloc[0]
            silver_df = _dedup_by_keys(silver_df, ['order_date', 'id'])
            silver_cols = [
                'id', 'name', 'category', 'value', 'quantity', 'order_date',
                'region', 'status', 'customer_email', 'notes', 'created_at',
                '_pipeline_run_id', '_source_table', '_silver_processed_at'
            ]
            rows_silver = _insert(client, f'{db}.silver_demo', silver_df, silver_cols)

        # 4. Insert Gold (deduplicated by business key first)
        if len(gold_daily) > 0:
            gold_daily = _dedup_by_keys(gold_daily, ['order_date'])
            rows_daily = _insert(client, f'{db}.gold_demo_daily', gold_daily, [
                'order_date', 'order_count', 'total_revenue', 'avg_order_value',
                'total_quantity', 'unique_customers', 'unique_regions', 'unique_categories',
                '_pipeline_run_id', '_gold_processed_at'
            ])
        if len(gold_region) > 0:
            gold_region = _dedup_by_keys(gold_region, ['region', 'report_date'])
            rows_region = _insert(client, f'{db}.gold_demo_by_region', gold_region, [
                'region', 'order_count', 'total_revenue', 'avg_order_value',
                'total_quantity', 'report_date', '_pipeline_run_id', '_gold_processed_at'
            ])
        if len(gold_category) > 0:
            gold_category = _dedup_by_keys(gold_category, ['category', 'report_date'])
            rows_category = _insert(client, f'{db}.gold_demo_by_category', gold_category, [
                'category', 'order_count', 'total_revenue', 'avg_order_value',
                'total_quantity', 'report_date', '_pipeline_run_id', '_gold_processed_at'
            ])

        status = 'success'
        for tbl in ['silver_demo', 'gold_demo_daily', 'gold_demo_by_region', 'gold_demo_by_category']:
            client.execute(f'OPTIMIZE TABLE {db}.{tbl} FINAL')

    except Exception as exc:
        error_msg = str(exc)
        status = 'failed'
        raise
    finally:
        # Record run
        ended_at = dt.datetime.now(dt.timezone.utc)
        cols = [
            'run_id', 'pipeline_name', 'status', 'started_at', 'ended_at',
            'rows_extracted', 'rows_silver', 'rows_gold_daily', 'rows_gold_region',
            'rows_gold_category', 'error_message'
        ]
        client.execute(f'INSERT INTO {db}.pipeline_runs ({", ".join(cols)}) VALUES', [{
            'run_id': run_id, 'pipeline_name': 'etl_postgres_to_lakehouse', 'status': status,
            'started_at': started_at, 'ended_at': ended_at, 'rows_extracted': rows_silver,
            'rows_silver': rows_silver, 'rows_gold_daily': rows_daily, 'rows_gold_region': rows_region,
            'rows_gold_category': rows_category, 'error_message': error_msg
        }])
    return {}


@test
def test_output(output, *args):
    assert output is not None, 'ClickHouse exporter returned None'

"""
Data Exporter – Load Excel data into ClickHouse.
"""

import os
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


def _to_records(df: pd.DataFrame) -> list[dict]:
    records = []
    # Convert dataframe to a list of dictionaries with native Python types
    # and handle ClickHouse compatibility
    for row in df.itertuples(index=False):
        record: dict[str, Any] = {}
        for field, value in zip(df.columns, row):
            # Convert numpy types to native python types
            if hasattr(value, 'item'):
                value = value.item()
            
            # Handle NaN/Null explicitly
            if pd.isna(value):
                value = None
            
            record[field] = value
        records.append(record)
    return records


def _ensure_tables(client: Client, db: str, df: pd.DataFrame, table_name: str) -> None:
    # Build dynamic DDL based on dataframe columns
    columns_ddl = []
    # Primary Key columns must be non-nullable in ClickHouse sorting keys
    pk_cols = ['_source_file_key', 'Mã công việc (ID)']

    for col in df.columns:
        # SUPER ROBUST MAPPING: Everything is a String for Excel data 
        # to avoid any type mismatch or encoding issues with mixed content.
        col_type = 'String'
        
        # Keep metadata timestamps as DateTime64 if they are definitely correct
        if col in ['_extracted_at', '_silver_processed_at', '_processed_at']:
             col_type = 'DateTime64(3)'
        
        # If part of PK, make it NOT Nullable
        if col in pk_cols:
            columns_ddl.append(f'`{col}` {col_type}')
        else:
            columns_ddl.append(f'`{col}` Nullable({col_type})')

    ddl = f'''
    CREATE TABLE IF NOT EXISTS {db}.{table_name}
    (
        {", ".join(columns_ddl)},
        `_db_processed_at` DateTime64(3) DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(_db_processed_at)
    ORDER BY (`_source_file_key`, `Mã công việc (ID)`)
    '''
    client.execute(f'CREATE DATABASE IF NOT EXISTS {db}')
    client.execute(ddl)


@data_exporter
def export_data(data, *args, **kwargs):
    if data.get('skip'):
        return {}

    df = data['dataframe'].copy()

    # 0. Filter out rows with empty/null ID to avoid junk data
    id_col = 'Mã công việc (ID)'
    if id_col in df.columns:
        initial_count = len(df)
        df = df[df[id_col].notna()]
        df = df[df[id_col].astype(str).str.strip() != '']
        print(f"[load_excel_to_clickhouse] Filtered out {initial_count - len(df)} junk rows (empty IDs)")

    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    table_name = 'project_reports'
    client = _ch_client()

    # 1. Force everything to strings except known datetime columns
    for col in df.columns:
        if col not in ['_extracted_at', '_silver_processed_at', '_processed_at']:
            # Use apply to handle every element individually to be 100% sure
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) else None)
            df[col] = df[col].replace({'nan': None, 'None': None, 'NaT': None, '<NA>': None})
        else:
            # Ensure dates are proper datetime objects for ClickHouse
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 2. Ensure table exists
    _ensure_tables(client, db, df, table_name)

    # 3. Prepare records
    records = _to_records(df)

    # 4. Insert
    if records:
        cols = ", ".join([f'`{c}`' for c in df.columns])
        client.execute(f'INSERT INTO {db}.{table_name} ({cols}) VALUES', records)
        client.execute(f'OPTIMIZE TABLE {db}.{table_name} FINAL')

    # 5. Log events for all files in batch
    processed_files = data.get('processed_files', [{
        'source_key': data.get('source_key', 'unknown'),
        'source_etag': data.get('source_etag', 'unknown'),
        'source_size': data.get('source_size', 0),
        'source_last_modified': data.get('source_last_modified'),
        'pipeline_run_id': data.get('pipeline_run_id', 'unknown')
    }])

    events = []
    for f in processed_files:
        events.append({
            'source_key': f['source_key'],
            'etag': f['source_etag'],
            'source_size': int(f['source_size']),
            'source_last_modified': dt.datetime.fromisoformat(f['source_last_modified']) if f.get('source_last_modified') else None,
            'status': 'success',
            'row_count': 0, # Aggregate row count is handled at CH table level or ignored
            'pipeline_run_id': f['pipeline_run_id'],
            'processed_at': dt.datetime.utcnow(),
        })
    
    client.execute(
        f'INSERT INTO {db}.excel_upload_events '
        '(source_key, etag, source_size, source_last_modified, status, row_count, pipeline_run_id, processed_at) VALUES',
        events
    )

    print(f"[load_excel_to_clickhouse] Successfully loaded {len(df)} rows to {db}.{table_name}")
    return {}


@test
def test_output(output, *args):
    assert output is not None

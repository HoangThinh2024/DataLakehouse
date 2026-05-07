"""
Data Exporter – Load Excel data into ClickHouse.
"""

import os
import datetime as dt
from typing import Any
import sys

import pandas as pd
from clickhouse_driver import Client

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter

# Import RustFS layer reader
project_root = os.getenv('MAGE_PROJECT_PATH', os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from utils.rustfs_layer_reader import read_latest_excel_silver

def _ch_client() -> Client:
    return Client(
        host=os.getenv('CLICKHOUSE_HOST', 'dlh-clickhouse'),
        port=int(os.getenv('CLICKHOUSE_TCP_PORT', '9000')),
        database=os.getenv('CLICKHOUSE_DB', 'analytics'),
        user=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
    )

def _to_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for row in df.itertuples(index=False):
        record: dict[str, Any] = {}
        for field, value in zip(df.columns, row):
            if hasattr(value, 'item'): value = value.item()
            if pd.isna(value): value = None
            record[field] = value
        records.append(record)
    return records

@data_exporter
def export_data(data, *args, **kwargs):
    if data.get('skip'): return {}

    # PROPER LAKEHOUSE: Read from RustFS Silver layer
    df = read_latest_excel_silver()
    if df.empty:
        print("[load_excel_to_clickhouse] No data found in Silver layer to load.")
        return {}

    # Filter junk
    id_col = 'Mã công việc (ID)'
    if id_col in df.columns:
        df = df[df[id_col].notna()]
        df = df[df[id_col].astype(str).str.strip() != '']

    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    table_name = 'project_reports'
    client = _ch_client()

    # Truncate for full refresh idempotency
    client.execute(f'TRUNCATE TABLE {db}.{table_name}')

    # Stringify for CH
    for col in df.columns:
        if col not in ['_extracted_at', '_silver_processed_at', '_db_processed_at']:
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) else None)
        else:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    records = _to_records(df)
    if records:
        cols = ", ".join([f'`{c}`' for c in df.columns])
        client.execute(f'INSERT INTO {db}.{table_name} ({cols}) VALUES', records)
        client.execute(f'OPTIMIZE TABLE {db}.{table_name} FINAL')

    # Log event
    processed_files = data.get('processed_files', [])
    events = []
    for f in processed_files:
        events.append({
            'source_key': f['source_key'],
            'etag': f['source_etag'],
            'source_size': int(f['source_size']),
            'source_last_modified': dt.datetime.fromisoformat(f['source_last_modified']) if f.get('source_last_modified') else None,
            'status': 'success',
            'row_count': len(df),
            'pipeline_run_id': f['pipeline_run_id'],
            'processed_at': dt.datetime.utcnow(),
        })
    
    if events:
        client.execute(f'INSERT INTO {db}.excel_upload_events (source_key, etag, source_size, source_last_modified, status, row_count, pipeline_run_id, processed_at) VALUES', events)

    print(f"[load_excel_to_clickhouse] Loaded {len(df)} rows to {db}.{table_name}")
    return {}

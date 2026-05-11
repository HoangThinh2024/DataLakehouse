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

_DATETIME_COLS = {'_extracted_at', '_silver_processed_at', '_db_processed_at'}


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
    for row in df.itertuples(index=False):
        record: dict[str, Any] = {}
        for field, value in zip(df.columns, row):
            if hasattr(value, 'item'):
                value = value.item()
            if not isinstance(value, (list, dict)) and pd.isna(value):
                value = None
            record[field] = value
        records.append(record)
    return records


def _ensure_table(client: Client, db: str, table_name: str) -> None:
    """Create project_reports table if it does not yet exist.

    This table uses 2-phase initialization:
    1) Bootstrap with metadata columns only.
    2) Add business columns dynamically from incoming DataFrame schema.
    """
    client.execute(f'CREATE DATABASE IF NOT EXISTS {db}')
    client.execute(f'''
        CREATE TABLE IF NOT EXISTS {db}.{table_name}
        (
            _extracted_at Nullable(DateTime64(3)),
            _silver_processed_at Nullable(DateTime64(3)),
            _db_processed_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_processed_at)
        ORDER BY _db_processed_at
    ''')


@data_exporter
def export_data(data, *args, **kwargs):
    # Guardrail: exporter should never crash when upstream returns unexpected payload.
    # Keep this check first so future refactors preserve safe no-op behaviour.
    if not isinstance(data, dict):
        print(f"[load_excel_to_clickhouse] Skip run - invalid payload type: {type(data)}")
        return {}
    if data.get('skip'):
        return {}

    # PROPER LAKEHOUSE: Read from RustFS Silver layer
    df = read_latest_excel_silver()
    if df.empty:
        print("[load_excel_to_clickhouse] No data found in Silver layer to load.")
        return {}

    # Filter rows with missing task ID
    id_col = 'Mã công việc (ID)'
    if id_col in df.columns:
        df = df[df[id_col].notna() & (df[id_col].astype(str).str.strip() != '')]

    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    table_name = 'project_reports'
    client = _ch_client()

    # Ensure table exists, then discover current columns
    _ensure_table(client, db, table_name)
    table_info = client.execute(f'DESCRIBE {db}.{table_name}')
    existing_cols = {row[0] for row in table_info}

    # Automatically evolve schema for new columns
    new_cols = [c for c in df.columns if c not in existing_cols]
    if new_cols:
        print(f"[load_excel_to_clickhouse] Found new columns to add: {new_cols}")
        for col in new_cols:
            try:
                client.execute(f'ALTER TABLE {db}.{table_name} ADD COLUMN `{col}` Nullable(String)')
                print(f"  ✓ Added column: {col}")
            except Exception as e:
                print(f"  ✗ Failed to add column {col}: {e}")
        # Refresh column list after ALTER
        table_info = client.execute(f'DESCRIBE {db}.{table_name}')
        existing_cols = {row[0] for row in table_info}

    df_cols = [c for c in df.columns if c in existing_cols]
    df = df[df_cols].copy()

    # Truncate for full refresh idempotency
    client.execute(f'TRUNCATE TABLE {db}.{table_name}')

    # Convert datetime columns; vectorized stringify for all others
    for col in df.columns:
        if col in _DATETIME_COLS:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        else:
            # 2-step normalization:
            # 1) Keep original null positions while stringifying non-null values.
            # 2) Convert sentinel strings ('nan'/'None'/'NaT') back to NULL.
            str_col = df[col].astype(str)
            df[col] = str_col.where(df[col].notna(), other=None)
            df.loc[str_col.isin({'nan', 'None', 'NaT'}), col] = None

    records = _to_records(df)
    if records:
        cols = ", ".join([f'`{c}`' for c in df.columns])
        client.execute(f'INSERT INTO {db}.{table_name} ({cols}) VALUES', records)
        client.execute(f'OPTIMIZE TABLE {db}.{table_name} FINAL')

    # Log event
    now_utc = dt.datetime.now(dt.timezone.utc)
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
            'processed_at': now_utc,
        })

    if events:
        client.execute(
            f'INSERT INTO {db}.excel_upload_events '
            '(source_key, etag, source_size, source_last_modified, status, row_count, pipeline_run_id, processed_at) VALUES',
            events,
        )

    print(f"[load_excel_to_clickhouse] Loaded {len(df)} rows to {db}.{table_name}")
    return {}

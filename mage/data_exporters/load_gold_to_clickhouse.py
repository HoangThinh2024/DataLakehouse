"""
Data Exporter – Load Gold aggregated project data into ClickHouse.
"""

import os
import sys
import pandas as pd
from clickhouse_driver import Client

if 'data_exporter' not in dir():
    from mage_ai.data_preparation.decorators import data_exporter

# Import RustFS layer reader
project_root = os.getenv('MAGE_PROJECT_PATH', os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from utils.rustfs_layer_reader import read_all_excel_gold

def _ch_client() -> Client:
    return Client(
        host=os.getenv('CLICKHOUSE_HOST', 'dlh-clickhouse'),
        port=int(os.getenv('CLICKHOUSE_TCP_PORT', '9000')),
        database=os.getenv('CLICKHOUSE_DB', 'analytics'),
        user=os.getenv('CLICKHOUSE_USER', 'default'),
        password=os.getenv('CLICKHOUSE_PASSWORD', '') or '',
    )

def _ensure_tables(client: Client, db: str) -> None:
    # 1. Projects Summary Table
    client.execute(f'''
        CREATE TABLE IF NOT EXISTS {db}.gold_projects_summary
        (
            _source_file_key String,
            total_tasks UInt64,
            completed_tasks UInt64,
            ongoing_tasks UInt64,
            overdue_tasks UInt64,
            completion_rate Float64,
            _pipeline_run_id String,
            _gold_processed_at DateTime64(3),
            _db_inserted_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_inserted_at)
        ORDER BY _source_file_key
    ''')
    
    # 2. Workload Table
    client.execute(f'''
        CREATE TABLE IF NOT EXISTS {db}.gold_workload_report
        (
            `Người thực hiện` String,
            task_count UInt64,
            urgent_tasks UInt64,
            _pipeline_run_id String,
            _gold_processed_at DateTime64(3),
            _db_inserted_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(_db_inserted_at)
        ORDER BY `Người thực hiện`
    ''')

@data_exporter
def export_gold_to_clickhouse(data, *args, **kwargs):
    if not isinstance(data, dict) or data.get('skip'):
        return data

    client = _ch_client()
    db = os.getenv('CLICKHOUSE_DB', 'analytics')
    _ensure_tables(client, db)

    # PROPER LAKEHOUSE: Read from RustFS Gold layer
    gold_data = read_all_excel_gold()
    df_p = gold_data.get('gold_projects', pd.DataFrame())
    df_w = gold_data.get('gold_workload', pd.DataFrame())

    # Load Project Summary
    if not df_p.empty:
        client.execute(f'TRUNCATE TABLE {db}.gold_projects_summary')
        df_p['_gold_processed_at'] = pd.to_datetime(df_p['_gold_processed_at'])
        records_p = df_p.to_dict('records')
        cols_p = ", ".join([f'`{c}`' for c in df_p.columns])
        client.execute(f'INSERT INTO {db}.gold_projects_summary ({cols_p}) VALUES', records_p)
        client.execute(f'OPTIMIZE TABLE {db}.gold_projects_summary FINAL')

    # Load Workload
    if not df_w.empty:
        client.execute(f'TRUNCATE TABLE {db}.gold_workload_report')
        df_w['_gold_processed_at'] = pd.to_datetime(df_w['_gold_processed_at'])
        records_w = df_w.to_dict('records')
        cols_w = ", ".join([f'`{c}`' for c in df_w.columns])
        client.execute(f'INSERT INTO {db}.gold_workload_report ({cols_w}) VALUES', records_w)
        client.execute(f'OPTIMIZE TABLE {db}.gold_workload_report FINAL')

    print(f"[load_gold_to_clickhouse] Loaded Gold data from RustFS to {db}")
    return data

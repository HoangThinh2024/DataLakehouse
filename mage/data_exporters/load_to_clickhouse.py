"""
Data Exporter – Load Silver and Gold data into ClickHouse.

Loads:
  - analytics.bronze_demo  (raw, from silver df before cleaning – passed in dict)
  - analytics.silver_demo  (cleaned typed rows)
  - analytics.gold_demo_daily, gold_demo_by_region, gold_demo_by_category (aggregations)
  - analytics.pipeline_runs (run-level metadata for Grafana monitoring)

Uses clickhouse-driver for the native TCP protocol (port 9000).
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

    # Coerce object/date/datetime columns to strings where needed
    for col in df_insert.select_dtypes(include=['object', 'datetime64[ns, UTC]']).columns:
        df_insert[col] = df_insert[col].astype(str).replace({'None': None, 'nan': None, 'NaT': None})

    records = _to_records(df_insert)
    if records:
        client.execute(f'INSERT INTO {table} ({", ".join(present)}) VALUES', records)
    return len(records)


@data_exporter
def load_clickhouse(data, *args, **kwargs):
    started_at = dt.datetime.utcnow()
    silver_df = pd.DataFrame()
    gold_daily = pd.DataFrame()
    gold_region = pd.DataFrame()
    gold_category = pd.DataFrame()
    run_id = 'unknown'

    if isinstance(data, dict):
        silver_df = data.get('silver', pd.DataFrame())
        gold_daily = data.get('gold_daily', pd.DataFrame())
        gold_region = data.get('gold_region', pd.DataFrame())
        gold_category = data.get('gold_category', pd.DataFrame())
    elif isinstance(data, pd.DataFrame):
        silver_df = data

    if len(silver_df) > 0 and '_pipeline_run_id' in silver_df.columns:
        run_id = silver_df['_pipeline_run_id'].iloc[0]

    client = _ch_client()
    rows_silver = rows_daily = rows_region = rows_category = 0
    error_msg = None

    try:
        # ── Silver ───────────────────────────────────────────
        silver_cols = [
            'id', 'name', 'category', 'value', 'quantity', 'order_date',
            'region', 'status', 'customer_email', 'notes', 'created_at',
            '_pipeline_run_id', '_source_table', '_silver_processed_at',
        ]
        rows_silver = _insert(client, 'analytics.silver_demo', silver_df, silver_cols)
        print(f"[load_to_clickhouse] silver_demo ← {rows_silver} rows")

        # ── Gold daily ───────────────────────────────────────
        gold_daily_cols = [
            'order_date', 'order_count', 'total_revenue', 'avg_order_value',
            'total_quantity', 'unique_customers', 'unique_regions', 'unique_categories',
            '_pipeline_run_id', '_gold_processed_at',
        ]
        rows_daily = _insert(client, 'analytics.gold_demo_daily', gold_daily, gold_daily_cols)
        print(f"[load_to_clickhouse] gold_demo_daily ← {rows_daily} rows")

        # ── Gold by region ───────────────────────────────────
        gold_region_cols = [
            'region', 'order_count', 'total_revenue', 'avg_order_value',
            'total_quantity', 'report_date', '_pipeline_run_id', '_gold_processed_at',
        ]
        rows_region = _insert(client, 'analytics.gold_demo_by_region', gold_region, gold_region_cols)
        print(f"[load_to_clickhouse] gold_demo_by_region ← {rows_region} rows")

        # ── Gold by category ─────────────────────────────────
        gold_cat_cols = [
            'category', 'order_count', 'total_revenue', 'avg_order_value',
            'total_quantity', 'report_date', '_pipeline_run_id', '_gold_processed_at',
        ]
        rows_category = _insert(client, 'analytics.gold_demo_by_category', gold_category, gold_cat_cols)
        print(f"[load_to_clickhouse] gold_demo_by_category ← {rows_category} rows")

        status = 'success'

    except Exception as exc:
        error_msg = str(exc)
        status = 'failed'
        print(f"[load_to_clickhouse] ERROR: {error_msg}")
        raise

    finally:
        # ── Pipeline run record ──────────────────────────────
        ended_at = dt.datetime.utcnow()
        run_record = [{
            'run_id': run_id,
            'pipeline_name': 'etl_postgres_to_lakehouse',
            'status': status,
            'started_at': started_at,
            'ended_at': ended_at,
            'rows_extracted': len(silver_df),
            'rows_silver': rows_silver,
            'rows_gold_daily': rows_daily,
            'rows_gold_region': rows_region,
            'rows_gold_category': rows_category,
            'error_message': error_msg,
        }]
        try:
            client.execute(
                'INSERT INTO analytics.pipeline_runs '
                '(run_id, pipeline_name, status, started_at, ended_at, '
                'rows_extracted, rows_silver, rows_gold_daily, rows_gold_region, '
                'rows_gold_category, error_message) VALUES',
                run_record,
            )
        except Exception as log_exc:
            print(f"[load_to_clickhouse] WARNING: could not write pipeline_runs: {log_exc}")

    print(
        f"[load_to_clickhouse] run_id={run_id}  status={status}  "
        f"silver={rows_silver}  daily={rows_daily}  region={rows_region}  cat={rows_category}"
    )
    return data


@test
def test_output(output, *args):
    assert output is not None, 'ClickHouse exporter returned None'

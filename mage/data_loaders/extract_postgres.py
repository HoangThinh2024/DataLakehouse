"""
Data Loader – Extract data from PostgreSQL source table.

Reads from public."Demo" (or the table configured via SOURCE_TABLE env var)
and enriches each row with pipeline run metadata before passing downstream.
"""

import os
import uuid
import datetime as dt

import pandas as pd
import psycopg2

if 'data_loader' not in dir():
    from mage_ai.data_preparation.decorators import data_loader
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


@data_loader
def load_data(*args, **kwargs):
    """Extract rows from PostgreSQL and attach run metadata."""
    run_id = str(uuid.uuid4())
    kwargs['pipeline_run_id'] = run_id

    host = os.getenv('SOURCE_DB_HOST', 'dlh-postgres')
    port = int(os.getenv('SOURCE_DB_PORT', '5432'))
    dbname = os.getenv('SOURCE_DB_NAME', os.getenv('POSTGRES_DB', 'datalakehouse'))
    user = os.getenv('SOURCE_DB_USER', os.getenv('POSTGRES_USER', 'dlh_admin'))
    password = os.getenv('SOURCE_DB_PASSWORD', os.getenv('POSTGRES_PASSWORD', ''))
    schema = os.getenv('SOURCE_SCHEMA', 'public')
    table = os.getenv('SOURCE_TABLE', 'Demo')

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=int(os.getenv('SOURCE_DB_CONNECT_TIMEOUT', '15')),
    )

    df = pd.read_sql(f'SELECT * FROM "{schema}"."{table}"', conn)
    conn.close()

    # Attach pipeline run metadata columns
    now_utc = dt.datetime.utcnow().isoformat() + 'Z'
    df['_pipeline_run_id'] = run_id
    df['_source_table'] = table
    df['_extracted_at'] = now_utc

    print(f"[extract_postgres] run_id={run_id}  rows={len(df)}  table={schema}.{table}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Output DataFrame is None'
    assert len(output) > 0, 'No rows were extracted from source'
    assert '_pipeline_run_id' in output.columns, '_pipeline_run_id column missing'

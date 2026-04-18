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
from psycopg2 import sql

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
    configured_table = os.getenv('SOURCE_TABLE')
    # If SOURCE_TABLE is not explicitly set, try common demo table names.
    # This helps the pipeline run on varied local databases out of the box.
    candidate_tables = [
        name.strip()
        for name in os.getenv('SOURCE_TABLE_CANDIDATES', 'Demo,test_projects').split(',')
        if name.strip()
    ]

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=int(os.getenv('SOURCE_DB_CONNECT_TIMEOUT', '15')),
    )

    # Resolve table name with case-insensitive fallback.
    # Priority:
    # 1) Explicit SOURCE_TABLE (strict)
    # 2) SOURCE_TABLE_CANDIDATES (first match)
    with conn.cursor() as cur:
        table_match = None
        requested_names = [configured_table] if configured_table else candidate_tables

        for requested_name in requested_names:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                  AND lower(table_name) = lower(%s)
                ORDER BY CASE WHEN table_name = %s THEN 0 ELSE 1 END, table_name
                LIMIT 1
                """,
                (schema, requested_name, requested_name),
            )
            table_match = cur.fetchone()
            if table_match is not None:
                break

        if table_match is None:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                LIMIT 20
                """,
                (schema,),
            )
            available_tables = [row[0] for row in cur.fetchall()]
            requested_label = configured_table if configured_table else requested_names
            raise ValueError(
                f'Source table not found in schema "{schema}". Requested: {requested_label}. '
                f'Available tables (first 20): {available_tables}. '
                'Set SOURCE_TABLE to an existing table (example: test_projects) '
                'or update SOURCE_TABLE_CANDIDATES.'
            )

    resolved_table = table_match[0]
    query = sql.SQL('SELECT * FROM {}.{}').format(
        sql.Identifier(schema),
        sql.Identifier(resolved_table),
    )
    df = pd.read_sql(query.as_string(conn), conn)
    conn.close()

    # Attach pipeline run metadata columns
    now_utc = dt.datetime.utcnow().isoformat() + 'Z'
    df['_pipeline_run_id'] = run_id
    df['_source_table'] = resolved_table
    df['_extracted_at'] = now_utc

    print(f"[extract_postgres] run_id={run_id}  rows={len(df)}  table={schema}.{resolved_table}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Output DataFrame is None'
    assert len(output) > 0, 'No rows were extracted from source'
    assert '_pipeline_run_id' in output.columns, '_pipeline_run_id column missing'

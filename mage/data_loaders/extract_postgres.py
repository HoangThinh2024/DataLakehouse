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

    source_dbname = os.getenv('SOURCE_DB_NAME')
    source_user = os.getenv('SOURCE_DB_USER')
    source_password = os.getenv('SOURCE_DB_PASSWORD')

    custom_dbname = os.getenv('CUSTOM_DB_NAME')
    custom_user = os.getenv('CUSTOM_DB_USER')
    custom_password = os.getenv('CUSTOM_DB_PASSWORD')

    if source_dbname and source_user and source_password:
        dbname = source_dbname
        user = source_user
        password = source_password
    elif custom_dbname and custom_user and custom_password:
        dbname = custom_dbname
        user = custom_user
        password = custom_password
    else:
        dbname = os.getenv('POSTGRES_DB', 'datalakehouse')
        user = os.getenv('POSTGRES_USER', 'dlh_admin')
        password = os.getenv('POSTGRES_PASSWORD', '')

    host = os.getenv('SOURCE_DB_HOST', os.getenv('POSTGRES_HOST', 'dlh-postgres'))
    port = int(os.getenv('SOURCE_DB_PORT', '5432'))
    schema = os.getenv('SOURCE_SCHEMA', os.getenv('CUSTOM_SCHEMA', 'public'))
    schema_fallbacks = [
        name.strip()
        for name in os.getenv('SOURCE_SCHEMA_FALLBACKS', 'public').split(',')
        if name.strip()
    ]
    configured_table = os.getenv('SOURCE_TABLE')
    # If SOURCE_TABLE is not explicitly set, try common demo table names.
    # This helps the pipeline run on varied local databases out of the box.
    candidate_tables = [
        name.strip()
        for name in os.getenv('SOURCE_TABLE_CANDIDATES', 'Demo,test_projects,sales_orders').split(',')
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

    # Resolve schema/table name with case-insensitive fallback.
    # Priority:
    # 1) Explicit SOURCE_TABLE (strict)
    # 2) SOURCE_TABLE_CANDIDATES (first match)
    with conn.cursor() as cur:
        table_match = None
        resolved_schema = schema
        requested_names = [configured_table] if configured_table else candidate_tables
        schema_candidates = [schema]
        for schema_name in schema_fallbacks:
            if schema_name not in schema_candidates:
                schema_candidates.append(schema_name)

        for schema_name in schema_candidates:
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
                    (schema_name, requested_name, requested_name),
                )
                table_match = cur.fetchone()
                if table_match is not None:
                    resolved_schema = schema_name
                    break
            if table_match is not None:
                break

        if table_match is None:
            available_by_schema = {}
            for schema_name in schema_candidates:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    LIMIT 20
                    """,
                    (schema_name,),
                )
                available_by_schema[schema_name] = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                LIMIT 20
                """,
            )
            public_tables = [row[0] for row in cur.fetchall()]
            requested_label = configured_table if configured_table else requested_names
            raise ValueError(
                f'Source table not found. Requested: {requested_label}. '
                f'Searched schemas: {schema_candidates}. '
                f'Available tables by schema (first 20): {available_by_schema}. '
                f'public tables (first 20): {public_tables}. '
                'Set SOURCE_TABLE to an existing table (example: test_projects) '
                'or update SOURCE_TABLE_CANDIDATES/SOURCE_SCHEMA.'
            )

    resolved_table = table_match[0]
    query = sql.SQL('SELECT * FROM {}.{}').format(
        sql.Identifier(resolved_schema),
        sql.Identifier(resolved_table),
    )
    df = pd.read_sql(query.as_string(conn), conn)
    conn.close()

    # Attach pipeline run metadata columns
    now_utc = dt.datetime.utcnow().isoformat() + 'Z'
    df['_pipeline_run_id'] = run_id
    df['_source_table'] = f'{resolved_schema}.{resolved_table}'
    df['_extracted_at'] = now_utc

    print(f"[extract_postgres] run_id={run_id}  rows={len(df)}  table={resolved_schema}.{resolved_table}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Output DataFrame is None'
    assert len(output) > 0, 'No rows were extracted from source'
    assert '_pipeline_run_id' in output.columns, '_pipeline_run_id column missing'

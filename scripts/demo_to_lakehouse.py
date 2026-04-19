#!/usr/bin/env python3
"""
Extract the configured source table from PostgreSQL,
archive the raw extract to RustFS (bronze), and load the same rows into
ClickHouse as a raw staging table.

Run this from the host or from a container that can reach:
- PostgreSQL at dlh-postgres:5432
- RustFS at dlh-rustfs:9000
- ClickHouse at dlh-clickhouse:8123

If you run it from the host instead of inside the Docker network, override:
- SOURCE_DB_HOST=127.0.0.1
- RUSTFS_ENDPOINT_URL=http://127.0.0.1:29100
- CLICKHOUSE_HTTP_URL=http://127.0.0.1:28123
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / '.env'


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return default if value in (None, '') else value


def sanitize_identifier(name: str) -> str:
    cleaned = re.sub(r'[^0-9a-zA-Z_]', '_', name).strip('_').lower()
    if not cleaned:
        cleaned = 'column'
    if cleaned[0].isdigit():
        cleaned = f'_{cleaned}'
    return cleaned


def unique_identifiers(names: Iterable[str]) -> List[str]:
    seen: Dict[str, int] = {}
    unique_names: List[str] = []

    for name in names:
        base = sanitize_identifier(name)
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique_names.append(base if count == 0 else f'{base}_{count + 1}')

    return unique_names


def normalize_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def fetch_rows() -> Tuple[List[str], List[Dict[str, Any]]]:
    source_query = get_env('SOURCE_QUERY')

    # Prefer CUSTOM_DB_* vars when provided; fall back to SOURCE_DB_* / POSTGRES_* defaults.
    custom_db = get_env('CUSTOM_DB_NAME')
    custom_user = get_env('CUSTOM_DB_USER')
    custom_password = get_env('CUSTOM_DB_PASSWORD')
    custom_schema = get_env('CUSTOM_SCHEMA')

    if custom_db and custom_user and custom_password:
        source_db_name = custom_db
        source_db_user = custom_user
        source_db_password = custom_password
        source_schema = custom_schema or get_env('SOURCE_SCHEMA', 'public')
    else:
        source_schema = get_env('SOURCE_SCHEMA', 'public')
        source_db_name = get_env('SOURCE_DB_NAME', get_env('POSTGRES_DB', 'datalakehouse'))
        source_db_user = get_env('SOURCE_DB_USER', get_env('POSTGRES_USER', 'dlh_admin'))
        source_db_password = get_env('SOURCE_DB_PASSWORD', get_env('POSTGRES_PASSWORD', ''))

    source_table = get_env('SOURCE_TABLE')
    if not source_table:
        candidates = [
            name.strip()
            for name in (get_env('SOURCE_TABLE_CANDIDATES', 'Demo,test_projects,sales_orders') or '').split(',')
            if name.strip()
        ]
        source_table = candidates[0] if candidates else 'sales_orders'

    source_db_host = get_env('SOURCE_DB_HOST', 'dlh-postgres')
    source_db_port = int(get_env('SOURCE_DB_PORT', '5432') or '5432')

    connection = psycopg2.connect(
        host=source_db_host,
        port=source_db_port,
        dbname=source_db_name,
        user=source_db_user,
        password=source_db_password,
        connect_timeout=int(get_env('SOURCE_DB_CONNECT_TIMEOUT', '10') or '10'),
    )

    with connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            if source_query:
                cursor.execute(source_query)
            else:
                query = sql.SQL('SELECT * FROM {}.{}').format(
                    sql.Identifier(source_schema),
                    sql.Identifier(source_table),
                )
                cursor.execute(query)

            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]

    connection.close()
    return columns, rows


def build_csv(columns: List[str], rows: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    safe_columns = unique_identifiers(columns)
    column_map = dict(zip(columns, safe_columns))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=safe_columns, extrasaction='ignore')
    writer.writeheader()

    for row in rows:
        writer.writerow({
            column_map[column]: normalize_value(value)
            for column, value in row.items()
            if column in column_map
        })

    return buffer.getvalue(), safe_columns


def ensure_bucket_exists(client, bucket_name: str) -> None:
    try:
        client.head_bucket(Bucket=bucket_name)
    except ClientError as error:
        error_code = str(error.response.get('Error', {}).get('Code', ''))
        if error_code not in {'404', 'NoSuchBucket', 'NotFound', 'NoSuchBucketPolicy'}:
            raise
        client.create_bucket(Bucket=bucket_name)


def upload_to_rustfs(csv_text: str, metadata: Dict[str, Any]) -> Tuple[str, str]:
    rustfs_endpoint = get_env('RUSTFS_ENDPOINT_URL', 'http://dlh-rustfs:9000')
    rustfs_bucket = get_env('RUSTFS_BRONZE_BUCKET', 'bronze')
    rustfs_prefix = get_env('RUSTFS_PREFIX', 'demo')
    rustfs_region = get_env('RUSTFS_REGION', 'us-east-1')
    rustfs_access_key = get_env('RUSTFS_ACCESS_KEY', 'rustfsadmin')
    rustfs_secret_key = get_env('RUSTFS_SECRET_KEY', 'rustfsadmin')

    s3 = boto3.client(
        's3',
        endpoint_url=rustfs_endpoint,
        aws_access_key_id=rustfs_access_key,
        aws_secret_access_key=rustfs_secret_key,
        region_name=rustfs_region,
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )

    ensure_bucket_exists(s3, rustfs_bucket)

    timestamp = dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    object_key = f'{rustfs_prefix}/dt={dt.date.today().isoformat()}/demo_{timestamp}.csv'
    metadata_key = f'{rustfs_prefix}/dt={dt.date.today().isoformat()}/demo_{timestamp}.json'

    s3.put_object(
        Bucket=rustfs_bucket,
        Key=object_key,
        Body=csv_text.encode('utf-8'),
        ContentType='text/csv',
    )
    s3.put_object(
        Bucket=rustfs_bucket,
        Key=metadata_key,
        Body=json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8'),
        ContentType='application/json',
    )

    return object_key, metadata_key


def clickhouse_post(query: str, body: bytes | None = None) -> None:
    clickhouse_url = get_env('CLICKHOUSE_HTTP_URL', 'http://dlh-clickhouse:8123').rstrip('/')
    clickhouse_database = get_env('CLICKHOUSE_DB', 'analytics')
    clickhouse_user = get_env('CLICKHOUSE_USER', 'default') or ''
    clickhouse_password = get_env('CLICKHOUSE_PASSWORD', '') or ''

    url = f'{clickhouse_url}/?{urllib.parse.urlencode({"database": clickhouse_database})}'
    payload = query.encode('utf-8') if body is None else query.encode('utf-8') + b'\n' + body

    request = urllib.request.Request(
        url,
        data=payload,
        method='POST',
        headers={'Content-Type': 'text/plain; charset=utf-8'},
    )

    if clickhouse_user:
        credentials = f'{clickhouse_user}:{clickhouse_password}'.encode('utf-8')
        request.add_header('Authorization', 'Basic ' + base64.b64encode(credentials).decode('ascii'))

    with urllib.request.urlopen(request) as response:
        response.read()


def load_into_clickhouse(columns: List[str], csv_text: str) -> None:
    safe_columns = unique_identifiers(columns)
    clickhouse_database = get_env('CLICKHOUSE_DB', 'analytics')
    clickhouse_table = get_env('CLICKHOUSE_TABLE', 'demo_raw')

    column_definitions = ',\n  '.join(f'`{column}` Nullable(String)' for column in safe_columns)
    create_database_sql = f'CREATE DATABASE IF NOT EXISTS `{clickhouse_database}`'
    create_table_sql = f'''
CREATE TABLE IF NOT EXISTS `{clickhouse_database}`.`{clickhouse_table}` (
  {column_definitions},
  `ingested_at` DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree
ORDER BY `ingested_at`;
'''.strip()

    insert_columns = ', '.join(f'`{column}`' for column in safe_columns)
    insert_sql = f'''
INSERT INTO `{clickhouse_database}`.`{clickhouse_table}` ({insert_columns})
FORMAT CSVWithNames
'''.strip()

    clickhouse_post(create_database_sql)
    clickhouse_post(create_table_sql)
    clickhouse_post(insert_sql, csv_text.encode('utf-8'))


def main() -> int:
    load_env_file(ENV_FILE)

    custom_db = get_env('CUSTOM_DB_NAME')
    custom_schema = get_env('CUSTOM_SCHEMA')

    effective_db = custom_db or get_env('SOURCE_DB_NAME', get_env('POSTGRES_DB', 'datalakehouse'))
    effective_schema = custom_schema or get_env('SOURCE_SCHEMA', 'public')

    columns, rows = fetch_rows()
    csv_text, safe_columns = build_csv(columns, rows)

    metadata = {
        'source': {
            'database': effective_db,
            'schema': effective_schema,
            'table': get_env('SOURCE_TABLE') or source_table,
            'query': get_env('SOURCE_QUERY'),
        },
        'row_count': len(rows),
        'columns': safe_columns,
        'exported_at_utc': dt.datetime.utcnow().isoformat() + 'Z',
        'rustfs': {
            'bucket': get_env('RUSTFS_BRONZE_BUCKET', 'bronze'),
            'prefix': get_env('RUSTFS_PREFIX', 'demo'),
        },
        'clickhouse': {
            'database': get_env('CLICKHOUSE_DB', 'analytics'),
            'table': get_env('CLICKHOUSE_TABLE', 'demo_raw'),
        },
    }

    rustfs_key, metadata_key = upload_to_rustfs(csv_text, metadata)
    load_into_clickhouse(columns, csv_text)

    print(f'Extracted {len(rows)} rows from source table {effective_schema}.{source_table}.')
    print(f'Uploaded CSV to RustFS: {rustfs_key}')
    print(f'Uploaded metadata JSON to RustFS: {metadata_key}')
    print(f'Loaded raw rows into ClickHouse: {get_env("CLICKHOUSE_DB", "analytics")}.{get_env("CLICKHOUSE_TABLE", "demo_raw")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
"""
Transformer - Validate and clean uploaded CSV for reporting.
"""

import re
import datetime as dt

import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


def _normalize_column_name(name: str, fallback_idx: int) -> str:
    cleaned = re.sub(r'[^0-9a-zA-Z]+', '_', str(name).strip().lower())
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        cleaned = f'col_{fallback_idx}'
    if cleaned[0].isdigit():
        cleaned = f'col_{cleaned}'
    return cleaned


@transformer
def transform_data(data, *args, **kwargs):
    if not isinstance(data, dict) or data.get('skip'):
        return data

    df = data.get('dataframe', pd.DataFrame()).copy()
    raw_rows = len(df)

    # Normalize header names and keep them unique.
    unique_names = []
    used = {}
    for idx, col in enumerate(df.columns):
        base = _normalize_column_name(col, idx)
        n = used.get(base, 0)
        used[base] = n + 1
        unique_names.append(base if n == 0 else f'{base}_{n + 1}')
    df.columns = unique_names

    # Trim all string-like columns and treat empty strings as null.
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip().replace({'': None, 'nan': None, 'None': None})

    # Remove fully-empty rows using business columns only.
    meta_cols = {
        '_pipeline_run_id', '_source_table', '_source_file_key',
        '_source_file_etag', '_extracted_at',
    }
    business_cols = [c for c in df.columns if c not in meta_cols]
    if business_cols:
        before_empty = len(df)
        df = df.dropna(how='all', subset=business_cols)
        dropped_empty_rows = before_empty - len(df)
    else:
        dropped_empty_rows = 0

    before_dedup = len(df)
    df = df.drop_duplicates()
    duplicate_rows = before_dedup - len(df)

    null_cells = int(df.isna().sum().sum())

    processed_at = dt.datetime.utcnow().isoformat() + 'Z'
    df['_silver_processed_at'] = processed_at
    df['_row_number'] = range(1, len(df) + 1)

    metrics = {
        'raw_rows': raw_rows,
        'cleaned_rows': len(df),
        'dropped_rows': dropped_empty_rows,
        'duplicate_rows': duplicate_rows,
        'null_cells': null_cells,
        'processed_at': processed_at,
    }

    print(
        f"[clean_csv_for_reporting] raw={raw_rows} cleaned={metrics['cleaned_rows']} "
        f"dropped={metrics['dropped_rows']} dup={metrics['duplicate_rows']}"
    )

    data['cleaned_dataframe'] = df
    data['quality_metrics'] = metrics
    return data


@test
def test_output(output, *args):
    assert output is not None, 'Output is None'
    if isinstance(output, dict) and not output.get('skip'):
        assert 'cleaned_dataframe' in output, 'Missing cleaned_dataframe'
        assert 'quality_metrics' in output, 'Missing quality_metrics'

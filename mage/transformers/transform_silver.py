"""
Transformer – Clean and validate raw data into Silver layer.

Cleaning rules applied:
- Drop exact duplicate rows
- Strip leading/trailing whitespace from string columns
- Normalise category and region to title-case
- Normalise status to lowercase
- Validate that value >= 0 and quantity >= 0 (negative values set to null)
- Validate email format (basic check; invalid emails set to null)
- Cast id, quantity to Int64 and value to Float64
- Parse order_date and created_at to proper datetime types
- Add _silver_processed_at timestamp
"""

import re
import datetime as dt

import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _clean_string(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().replace({'nan': None, 'None': None, '': None})


def _valid_email(val):
    if pd.isna(val) or not isinstance(val, str):
        return None
    return val.strip() if _EMAIL_RE.match(val.strip()) else None


@transformer
def transform_silver(df: pd.DataFrame, *args, **kwargs):
    run_id = df['_pipeline_run_id'].iloc[0] if '_pipeline_run_id' in df.columns else ''

    # 1. Drop exact duplicates (keep first)
    before = len(df)
    df = df.drop_duplicates()
    print(f"[transform_silver] Exact duplicates removed: {before - len(df)}")

    # 1b. Deduplicate by business key (id), keeping the row with the latest
    #     _extracted_at.  This prevents the same source record appearing
    #     multiple times when the upstream extract contains repeated ids.
    if 'id' in df.columns:
        before_biz = len(df)
        sort_cols = ['_extracted_at', 'id'] if '_extracted_at' in df.columns else ['id']
        df = df.sort_values(sort_cols, ascending=True, na_position='first')
        df = df.drop_duplicates(subset=['id'], keep='last').reset_index(drop=True)
        removed = before_biz - len(df)
        if removed:
            print(f"[transform_silver] Business-key (id) dedup removed: {removed}")

    # 2. Clean text columns
    for col in ('name', 'notes'):
        if col in df.columns:
            df[col] = _clean_string(df[col])

    # 3. Normalise controlled-vocab columns
    if 'category' in df.columns:
        df['category'] = _clean_string(df['category']).str.title()
    if 'region' in df.columns:
        df['region'] = _clean_string(df['region']).str.title()
    if 'status' in df.columns:
        df['status'] = _clean_string(df['status']).str.lower()

    # 4. Validate email
    if 'customer_email' in df.columns:
        df['customer_email'] = df['customer_email'].apply(_valid_email)

    # 5. Cast numeric columns; coerce negatives to NaN
    if 'value' in df.columns:
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df.loc[df['value'] < 0, 'value'] = None
    if 'quantity' in df.columns:
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').astype('Int64')
        df.loc[df['quantity'] < 0, 'quantity'] = None
    if 'id' in df.columns:
        df['id'] = pd.to_numeric(df['id'], errors='coerce').astype('Int64')

    # 6. Parse date / datetime columns
    if 'order_date' in df.columns:
        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce').dt.date
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)

    # 7. Add silver metadata
    df['_pipeline_run_id'] = run_id
    df['_silver_processed_at'] = dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')

    print(f"[transform_silver] Silver rows ready: {len(df)}")
    return df


@test
def test_output(output, *args):
    assert output is not None, 'Silver DataFrame is None'
    assert len(output) > 0, 'Silver DataFrame is empty'
    assert '_silver_processed_at' in output.columns, '_silver_processed_at missing'
    if 'value' in output.columns:
        assert (output['value'].dropna() >= 0).all(), 'Negative values found in silver layer'

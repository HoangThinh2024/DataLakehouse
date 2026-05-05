"""
Transformer – Clean and validate Excel data for the Silver layer.
"""

import datetime as dt
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


def _clean_string(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().replace({'nan': None, 'None': None, '': None})


@transformer
def transform_excel(data, *args, **kwargs):
    if data.get('skip'):
        return data

    df = data['dataframe']
    
    # 0. Drop unnamed columns (usually from Excel index or empty columns)
    unnamed_cols = [col for col in df.columns if 'Unnamed' in str(col)]
    if unnamed_cols:
        print(f"[clean_excel_data] Dropping unnamed columns: {unnamed_cols}")
        df = df.drop(columns=unnamed_cols)

    # 1. Clean string columns
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = _clean_string(df[col])

    # 2. Add silver metadata
    df['_silver_processed_at'] = dt.datetime.utcnow().isoformat() + 'Z'

    print(f"[clean_excel_data] Silver rows ready: {len(df)}")
    
    data['dataframe'] = df
    return data


@test
def test_output(output, *args):
    assert output is not None, 'Output is None'
    if not output.get('skip'):
        assert 'dataframe' in output, 'Missing dataframe in output'
        assert '_silver_processed_at' in output['dataframe'].columns

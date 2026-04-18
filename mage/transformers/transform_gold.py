"""
Transformer – Aggregate Silver data into Gold layer.

Produces three summary DataFrames:
  - gold_daily:    daily order metrics
  - gold_region:   per-region order metrics
  - gold_category: per-category order metrics

Returns a dict so both gold_to_rustfs and load_to_clickhouse can consume
the right frame without re-computing.
"""

import datetime as dt
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test


@transformer
def transform_gold(df: pd.DataFrame, *args, **kwargs):
    run_id = df['_pipeline_run_id'].iloc[0] if '_pipeline_run_id' in df.columns else ''
    gold_ts = dt.datetime.utcnow().isoformat() + 'Z'
    report_date = dt.date.today()

    # Work with heterogeneous source schemas (not only Demo).
    df_agg = df.copy()
    df_agg['__row_count'] = 1

    if 'value' in df_agg.columns:
        df_agg['value'] = pd.to_numeric(df_agg['value'], errors='coerce').fillna(0)
    else:
        df_agg['value'] = 0.0

    if 'quantity' in df_agg.columns:
        df_agg['quantity'] = pd.to_numeric(df_agg['quantity'], errors='coerce').fillna(0)
    else:
        df_agg['quantity'] = 0

    # ── Daily summary ────────────────────────────────────────
    if 'order_date' not in df_agg.columns:
        if 'created_at' in df_agg.columns:
            df_agg['order_date'] = pd.to_datetime(df_agg['created_at'], errors='coerce').dt.date
        else:
            df_agg['order_date'] = report_date

    df_agg['order_date'] = pd.to_datetime(df_agg['order_date'], errors='coerce').dt.date
    daily_agg = {
        'order_count': ('__row_count', 'sum'),
        'total_revenue': ('value', 'sum'),
        'avg_order_value': ('value', 'mean'),
        'total_quantity': ('quantity', 'sum'),
    }
    if 'customer_email' in df_agg.columns:
        daily_agg['unique_customers'] = ('customer_email', 'nunique')
    if 'region' in df_agg.columns:
        daily_agg['unique_regions'] = ('region', 'nunique')
    if 'category' in df_agg.columns:
        daily_agg['unique_categories'] = ('category', 'nunique')

    daily = (
        df_agg.dropna(subset=['order_date'])
        .groupby('order_date')
        .agg(**daily_agg)
        .reset_index()
    )
    if 'unique_customers' not in daily.columns:
        daily['unique_customers'] = 0
    if 'unique_regions' not in daily.columns:
        daily['unique_regions'] = 0
    if 'unique_categories' not in daily.columns:
        daily['unique_categories'] = 0

    daily['_pipeline_run_id'] = run_id
    daily['_gold_processed_at'] = gold_ts

    # ── By region ────────────────────────────────────────────
    if 'region' in df_agg.columns:
        by_region = (
            df_agg.dropna(subset=['region'])
            .groupby('region')
            .agg(
                order_count=('__row_count', 'sum'),
                total_revenue=('value', 'sum'),
                avg_order_value=('value', 'mean'),
                total_quantity=('quantity', 'sum'),
            )
            .reset_index()
        )
    else:
        by_region = pd.DataFrame()

    by_region['report_date'] = report_date
    by_region['_pipeline_run_id'] = run_id
    by_region['_gold_processed_at'] = gold_ts

    # ── By category ──────────────────────────────────────────
    if 'category' in df_agg.columns:
        by_category = (
            df_agg.dropna(subset=['category'])
            .groupby('category')
            .agg(
                order_count=('id', 'count'),
                total_revenue=('value', 'sum'),
                avg_order_value=('value', 'mean'),
                total_quantity=('quantity', 'sum'),
            )
            .reset_index()
        )
    else:
        by_category = pd.DataFrame()

    by_category['report_date'] = report_date
    by_category['_pipeline_run_id'] = run_id
    by_category['_gold_processed_at'] = gold_ts

    print(
        f"[transform_gold] daily={len(daily)} rows  "
        f"by_region={len(by_region)} rows  by_category={len(by_category)} rows"
    )

    return {
        'silver': df,
        'gold_daily': daily,
        'gold_region': by_region,
        'gold_category': by_category,
    }


@test
def test_output(output, *args):
    assert output is not None, 'Gold output is None'
    assert isinstance(output, dict), 'Gold output must be a dict'
    assert 'silver' in output, 'silver key missing from gold output'
    assert 'gold_daily' in output, 'gold_daily key missing from gold output'
    assert 'gold_region' in output, 'gold_region key missing from gold output'
    assert 'gold_category' in output, 'gold_category key missing from gold output'

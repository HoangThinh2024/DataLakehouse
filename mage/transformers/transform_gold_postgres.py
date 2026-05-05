"""
Transformer – Aggregate Postgres (Sales) Silver data into Gold layer.
Calculates daily sales, regional performance, and category summaries.
"""

import datetime as dt
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer

@transformer
def transform_gold_postgres(df, *args, **kwargs):
    if df is None or len(df) == 0:
        return {}

    run_id = df['_pipeline_run_id'].iloc[0] if '_pipeline_run_id' in df.columns else 'unknown'
    gold_ts = dt.datetime.utcnow().isoformat() + 'Z'
    
    # 1. Gold Daily Sales
    gold_daily = df.groupby('order_date').agg(
        order_count=('id', 'count'),
        total_revenue=('value', 'sum'),
        total_quantity=('quantity', 'sum'),
        unique_customers=('customer_email', 'nunique'),
        unique_regions=('region', 'nunique'),
        unique_categories=('category', 'nunique')
    ).reset_index()
    
    gold_daily['avg_order_value'] = (gold_daily['total_revenue'] / gold_daily['order_count']).round(2)
    gold_daily['_pipeline_run_id'] = run_id
    gold_daily['_gold_processed_at'] = gold_ts

    # 2. Gold Regional Performance
    gold_region = df.groupby(['region', 'order_date']).agg(
        order_count=('id', 'count'),
        total_revenue=('value', 'sum'),
        total_quantity=('quantity', 'sum')
    ).reset_index()
    gold_region['report_date'] = gold_region['order_date']
    gold_region['avg_order_value'] = (gold_region['total_revenue'] / gold_region['order_count']).round(2)
    gold_region['_pipeline_run_id'] = run_id
    gold_region['_gold_processed_at'] = gold_ts

    # 3. Gold Category Summary
    gold_category = df.groupby(['category', 'order_date']).agg(
        order_count=('id', 'count'),
        total_revenue=('value', 'sum'),
        total_quantity=('quantity', 'sum')
    ).reset_index()
    gold_category['report_date'] = gold_category['order_date']
    gold_category['avg_order_value'] = (gold_category['total_revenue'] / gold_category['order_count']).round(2)
    gold_category['_pipeline_run_id'] = run_id
    gold_category['_gold_processed_at'] = gold_ts

    print(f"[transform_gold_postgres] Daily rows: {len(gold_daily)}, Region rows: {len(gold_region)}, Category rows: {len(gold_category)}")

    return {
        'gold_daily': gold_daily,
        'gold_region': gold_region,
        'gold_category': gold_category,
        'pipeline_run_id': run_id
    }

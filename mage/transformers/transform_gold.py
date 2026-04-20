"""
Transformer – Aggregate Silver data into Gold layer.

Produces six summary DataFrames:
  - gold_daily:    daily order metrics
  - gold_weekly:   weekly order metrics (ISO week)
  - gold_monthly:  monthly order metrics
  - gold_yearly:   yearly order metrics
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
    elif 'unit_price' in df_agg.columns:
        unit_price = pd.to_numeric(df_agg['unit_price'], errors='coerce').fillna(0)
        if 'quantity' in df_agg.columns:
            quantity = pd.to_numeric(df_agg['quantity'], errors='coerce').fillna(0)
            df_agg['value'] = unit_price * quantity
        else:
            df_agg['value'] = unit_price
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

    # ── Weekly summary ───────────────────────────────────────
    df_weekly = df_agg.copy()
    df_weekly['order_date'] = pd.to_datetime(df_weekly['order_date'], errors='coerce')
    df_weekly = df_weekly.dropna(subset=['order_date'])
    if len(df_weekly) > 0:
        df_weekly['week_start'] = df_weekly['order_date'] - pd.to_timedelta(
            df_weekly['order_date'].dt.dayofweek, unit='D'
        )
        df_weekly['week_start'] = df_weekly['week_start'].dt.date
        df_weekly['year_week'] = df_weekly['order_date'].dt.strftime('%G-W%V')

        weekly_agg = {
            'order_count': ('__row_count', 'sum'),
            'total_revenue': ('value', 'sum'),
            'avg_order_value': ('value', 'mean'),
            'total_quantity': ('quantity', 'sum'),
        }
        if 'customer_email' in df_weekly.columns:
            weekly_agg['unique_customers'] = ('customer_email', 'nunique')
        if 'region' in df_weekly.columns:
            weekly_agg['unique_regions'] = ('region', 'nunique')
        if 'category' in df_weekly.columns:
            weekly_agg['unique_categories'] = ('category', 'nunique')

        weekly = (
            df_weekly.groupby(['year_week', 'week_start'])
            .agg(**weekly_agg)
            .reset_index()
        )
    else:
        weekly = pd.DataFrame(columns=[
            'year_week', 'week_start', 'order_count', 'total_revenue',
            'avg_order_value', 'total_quantity',
        ])

    for col in ('unique_customers', 'unique_regions', 'unique_categories'):
        if col not in weekly.columns:
            weekly[col] = 0
    weekly['_pipeline_run_id'] = run_id
    weekly['_gold_processed_at'] = gold_ts

    # ── Monthly summary ──────────────────────────────────────
    df_monthly = df_agg.copy()
    df_monthly['order_date'] = pd.to_datetime(df_monthly['order_date'], errors='coerce')
    df_monthly = df_monthly.dropna(subset=['order_date'])
    if len(df_monthly) > 0:
        df_monthly['year_month'] = df_monthly['order_date'].dt.strftime('%Y-%m')
        df_monthly['month_start'] = df_monthly['order_date'].dt.to_period('M').dt.to_timestamp().dt.date

        monthly_agg = {
            'order_count': ('__row_count', 'sum'),
            'total_revenue': ('value', 'sum'),
            'avg_order_value': ('value', 'mean'),
            'total_quantity': ('quantity', 'sum'),
        }
        if 'customer_email' in df_monthly.columns:
            monthly_agg['unique_customers'] = ('customer_email', 'nunique')
        if 'region' in df_monthly.columns:
            monthly_agg['unique_regions'] = ('region', 'nunique')
        if 'category' in df_monthly.columns:
            monthly_agg['unique_categories'] = ('category', 'nunique')

        monthly = (
            df_monthly.groupby(['year_month', 'month_start'])
            .agg(**monthly_agg)
            .reset_index()
        )
    else:
        monthly = pd.DataFrame(columns=[
            'year_month', 'month_start', 'order_count', 'total_revenue',
            'avg_order_value', 'total_quantity',
        ])

    for col in ('unique_customers', 'unique_regions', 'unique_categories'):
        if col not in monthly.columns:
            monthly[col] = 0
    monthly['_pipeline_run_id'] = run_id
    monthly['_gold_processed_at'] = gold_ts

    # ── Yearly summary ───────────────────────────────────────
    df_yearly = df_agg.copy()
    df_yearly['order_date'] = pd.to_datetime(df_yearly['order_date'], errors='coerce')
    df_yearly = df_yearly.dropna(subset=['order_date'])
    if len(df_yearly) > 0:
        df_yearly['year'] = df_yearly['order_date'].dt.year

        yearly_agg = {
            'order_count': ('__row_count', 'sum'),
            'total_revenue': ('value', 'sum'),
            'avg_order_value': ('value', 'mean'),
            'total_quantity': ('quantity', 'sum'),
        }
        if 'customer_email' in df_yearly.columns:
            yearly_agg['unique_customers'] = ('customer_email', 'nunique')
        if 'region' in df_yearly.columns:
            yearly_agg['unique_regions'] = ('region', 'nunique')
        if 'category' in df_yearly.columns:
            yearly_agg['unique_categories'] = ('category', 'nunique')

        yearly = (
            df_yearly.groupby('year')
            .agg(**yearly_agg)
            .reset_index()
        )
    else:
        yearly = pd.DataFrame(columns=[
            'year', 'order_count', 'total_revenue',
            'avg_order_value', 'total_quantity',
        ])

    for col in ('unique_customers', 'unique_regions', 'unique_categories'):
        if col not in yearly.columns:
            yearly[col] = 0
    yearly['_pipeline_run_id'] = run_id
    yearly['_gold_processed_at'] = gold_ts

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
        f"[transform_gold] daily={len(daily)} rows  weekly={len(weekly)} rows  "
        f"monthly={len(monthly)} rows  yearly={len(yearly)} rows  "
        f"by_region={len(by_region)} rows  by_category={len(by_category)} rows"
    )

    return {
        'silver': df,
        'gold_daily': daily,
        'gold_weekly': weekly,
        'gold_monthly': monthly,
        'gold_yearly': yearly,
        'gold_region': by_region,
        'gold_category': by_category,
    }


@test
def test_output(output, *args):
    assert output is not None, 'Gold output is None'
    assert isinstance(output, dict), 'Gold output must be a dict'
    assert 'silver' in output, 'silver key missing from gold output'
    assert 'gold_daily' in output, 'gold_daily key missing from gold output'
    assert 'gold_weekly' in output, 'gold_weekly key missing from gold output'
    assert 'gold_monthly' in output, 'gold_monthly key missing from gold output'
    assert 'gold_yearly' in output, 'gold_yearly key missing from gold output'
    assert 'gold_region' in output, 'gold_region key missing from gold output'
    assert 'gold_category' in output, 'gold_category key missing from gold output'

    expected_frames = [
        'silver',
        'gold_daily',
        'gold_weekly',
        'gold_monthly',
        'gold_yearly',
        'gold_region',
        'gold_category',
    ]
    for key in expected_frames:
        assert isinstance(output[key], pd.DataFrame), f'{key} must be a pandas DataFrame'

    weekly = output['gold_weekly']
    weekly_required_columns = {'year_week', 'week_start'}
    missing_weekly_columns = weekly_required_columns.difference(weekly.columns)
    assert not missing_weekly_columns, (
        f"gold_weekly missing required columns: {sorted(missing_weekly_columns)}"
    )
    if not weekly.empty:
        week_start = pd.to_datetime(weekly['week_start'], errors='raise')
        assert (week_start.dt.dayofweek == 0).all(), 'gold_weekly week_start must always be a Monday'
        iso_calendar = week_start.dt.isocalendar()
        expected_year_week = (
            iso_calendar['year'].astype(str)
            + '-W'
            + iso_calendar['week'].astype(str).str.zfill(2)
        )
        assert weekly['year_week'].astype(str).equals(expected_year_week), (
            'gold_weekly year_week must match ISO year/week derived from week_start'
        )

    monthly = output['gold_monthly']
    monthly_required_columns = {'year_month', 'month_start'}
    missing_monthly_columns = monthly_required_columns.difference(monthly.columns)
    assert not missing_monthly_columns, (
        f"gold_monthly missing required columns: {sorted(missing_monthly_columns)}"
    )
    if not monthly.empty:
        month_start = pd.to_datetime(monthly['month_start'], errors='raise')
        assert (month_start.dt.day == 1).all(), 'gold_monthly month_start must always be the first day of the month'
        expected_year_month = month_start.dt.strftime('%Y-%m')
        assert monthly['year_month'].astype(str).equals(expected_year_month), (
            'gold_monthly year_month must match month_start'
        )

    yearly = output['gold_yearly']
    yearly_required_columns = {'year'}
    missing_yearly_columns = yearly_required_columns.difference(yearly.columns)
    assert not missing_yearly_columns, (
        f"gold_yearly missing required columns: {sorted(missing_yearly_columns)}"
    )
    if not yearly.empty:
        assert yearly['year'].notna().all(), 'gold_yearly year must not contain null values'

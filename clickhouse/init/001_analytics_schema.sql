-- =============================================================
-- ClickHouse Analytics Schema
-- Layers: Bronze (raw) → Silver (clean) → Gold (aggregated)
-- + Pipeline run tracking table for Grafana monitoring
-- =============================================================

-- Ensure analytics database exists (also set via env CLICKHOUSE_DB)
CREATE DATABASE IF NOT EXISTS analytics;

-- =============================================================
-- BRONZE: raw staging – all columns as Nullable(String)
-- =============================================================
CREATE TABLE IF NOT EXISTS analytics.bronze_demo
(
    id                  Nullable(String),
    name                Nullable(String),
    category            Nullable(String),
    value               Nullable(String),
    quantity            Nullable(String),
    order_date          Nullable(String),
    region              Nullable(String),
    status              Nullable(String),
    customer_email      Nullable(String),
    notes               Nullable(String),
    created_at          Nullable(String),
    _pipeline_run_id    String DEFAULT '',
    _source_table       String DEFAULT 'Demo',
    _extracted_at       DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(_extracted_at)
ORDER BY (_extracted_at, _pipeline_run_id);

-- =============================================================
-- SILVER: cleaned & typed data
-- =============================================================
CREATE TABLE IF NOT EXISTS analytics.silver_demo
(
    id                      Nullable(Int64),
    name                    Nullable(String),
    category                Nullable(String),
    value                   Nullable(Float64),
    quantity                Nullable(Int32),
    order_date              Nullable(Date),
    region                  Nullable(String),
    status                  Nullable(String),
    customer_email          Nullable(String),
    notes                   Nullable(String),
    created_at              Nullable(DateTime64(3)),
    _pipeline_run_id        String DEFAULT '',
    _source_table           String DEFAULT 'Demo',
    _silver_processed_at    DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(toDateTime(_silver_processed_at))
ORDER BY (_silver_processed_at, _pipeline_run_id);

-- =============================================================
-- GOLD: aggregated summaries
-- =============================================================

-- Daily sales summary
CREATE TABLE IF NOT EXISTS analytics.gold_demo_daily
(
    order_date              Date,
    order_count             Int64,
    total_revenue           Float64,
    avg_order_value         Float64,
    total_quantity          Int64,
    unique_customers        Int64,
    unique_regions          Int64,
    unique_categories       Int64,
    _pipeline_run_id        String DEFAULT '',
    _gold_processed_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (order_date, _pipeline_run_id);

-- Sales by region
CREATE TABLE IF NOT EXISTS analytics.gold_demo_by_region
(
    region                  String,
    order_count             Int64,
    total_revenue           Float64,
    avg_order_value         Float64,
    total_quantity          Int64,
    report_date             Date,
    _pipeline_run_id        String DEFAULT '',
    _gold_processed_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(report_date)
ORDER BY (region, report_date, _pipeline_run_id);

-- Sales by category
CREATE TABLE IF NOT EXISTS analytics.gold_demo_by_category
(
    category                String,
    order_count             Int64,
    total_revenue           Float64,
    avg_order_value         Float64,
    total_quantity          Int64,
    report_date             Date,
    _pipeline_run_id        String DEFAULT '',
    _gold_processed_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(report_date)
ORDER BY (category, report_date, _pipeline_run_id);

-- =============================================================
-- MONITORING: pipeline run tracking (queried by Grafana)
-- =============================================================
CREATE TABLE IF NOT EXISTS analytics.pipeline_runs
(
    run_id              String,
    pipeline_name       String,
    status              String,
    started_at          DateTime64(3),
    ended_at            Nullable(DateTime64(3)),
    rows_extracted      Int64 DEFAULT 0,
    rows_silver         Int64 DEFAULT 0,
    rows_gold_daily     Int64 DEFAULT 0,
    rows_gold_region    Int64 DEFAULT 0,
    rows_gold_category  Int64 DEFAULT 0,
    error_message       Nullable(String),
    _created_at         DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY started_at;

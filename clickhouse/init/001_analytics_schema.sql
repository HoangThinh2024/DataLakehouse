-- =============================================================
-- ClickHouse Analytics Schema
-- Layers: Bronze (raw) → Silver (clean) → Gold (aggregated)
-- + Pipeline run tracking table for Grafana monitoring
--
-- Silver and Gold tables use ReplacingMergeTree to provide
-- idempotent/deduplicating loads on repeated pipeline runs.
-- The version column (_silver_processed_at / _gold_processed_at)
-- ensures the most-recent write wins on OPTIMIZE … FINAL.
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
-- ReplacingMergeTree deduplicates rows sharing the same
-- (_pipeline_run_id, _silver_processed_at) key, keeping the row
-- with the highest _silver_processed_at version.
-- Note: id is Nullable and therefore cannot appear in ORDER BY.
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
ENGINE = ReplacingMergeTree(_silver_processed_at)
PARTITION BY toYYYYMM(toDateTime(_silver_processed_at))
ORDER BY (_pipeline_run_id, _silver_processed_at);

-- =============================================================
-- GOLD: aggregated summaries
-- ReplacingMergeTree deduplicates repeated runs for same period.
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
ENGINE = ReplacingMergeTree(_gold_processed_at)
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
ENGINE = ReplacingMergeTree(_gold_processed_at)
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
ENGINE = ReplacingMergeTree(_gold_processed_at)
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

-- =============================================================
-- CSV REPORTING: cleaned CSV rows and quality metrics
-- =============================================================
CREATE TABLE IF NOT EXISTS analytics.csv_clean_rows
(
    pipeline_run_id     String,
    source_key          String,
    source_etag         String,
    source_last_modified Nullable(DateTime64(3)),
    row_number          UInt64,
    row_json            String,
    processed_at        DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(processed_at)
ORDER BY (processed_at, source_key, row_number);

CREATE TABLE IF NOT EXISTS analytics.csv_quality_metrics
(
    pipeline_run_id     String,
    source_key          String,
    source_etag         String,
    raw_rows            Int64,
    cleaned_rows        Int64,
    dropped_rows        Int64,
    duplicate_rows      Int64,
    null_cells          Int64,
    processed_at        DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(processed_at)
ORDER BY (processed_at, source_key);

CREATE TABLE IF NOT EXISTS analytics.csv_upload_events
(
    source_key          String,
    etag                String,
    source_size         Int64,
    source_last_modified Nullable(DateTime64(3)),
    status              String,
    row_count           Int64 DEFAULT 0,
    duplicate_rows      Int64 DEFAULT 0,
    dropped_rows        Int64 DEFAULT 0,
    processed_at        DateTime64(3) DEFAULT now64(3),
    pipeline_run_id     String DEFAULT '',
    error_message       Nullable(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(processed_at)
ORDER BY (source_key, etag, processed_at);

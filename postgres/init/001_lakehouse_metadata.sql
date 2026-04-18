-- DataLakehouse metadata bootstrap
-- This script runs automatically on first PostgreSQL init.

CREATE SCHEMA IF NOT EXISTS lakehouse;

CREATE TABLE IF NOT EXISTS lakehouse.dataset (
    dataset_id BIGSERIAL PRIMARY KEY,
    dataset_name TEXT NOT NULL UNIQUE,
    owner_name TEXT,
    source_system TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lakehouse.data_object (
    object_id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES lakehouse.dataset(dataset_id) ON DELETE CASCADE,
    storage_layer TEXT NOT NULL CHECK (storage_layer IN ('bronze', 'silver', 'gold')),
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    object_format TEXT NOT NULL,
    object_size_bytes BIGINT,
    checksum_sha256 TEXT,
    event_time TIMESTAMPTZ,
    ingestion_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    partition_values JSONB,
    UNIQUE (bucket_name, object_key)
);

CREATE TABLE IF NOT EXISTS lakehouse.pipeline_run (
    run_id BIGSERIAL PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    run_status TEXT NOT NULL CHECK (run_status IN ('running', 'success', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    row_count_in BIGINT,
    row_count_out BIGINT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_data_object_dataset_id
    ON lakehouse.data_object (dataset_id);

CREATE INDEX IF NOT EXISTS idx_data_object_layer_event_time
    ON lakehouse.data_object (storage_layer, event_time DESC);

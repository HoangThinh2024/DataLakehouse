#!/bin/bash
set -e

DB="analytics"
USER="doe"
PASS="Do12345678910.."
BROKERS="redpanda:9092"
REGISTRY="http://redpanda:8081"

echo "Creating Kafka Engine table: kafka_demo..."
docker exec dlh-clickhouse clickhouse-client -u $USER --password "$PASS" -d $DB -q "
CREATE TABLE IF NOT EXISTS kafka_demo
(
    \`after.id\` Int64,
    \`after.name\` Nullable(String),
    \`after.category\` Nullable(String),
    \`after.value\` Nullable(Float64),
    \`after.quantity\` Nullable(Int32),
    \`after.order_date\` Nullable(Int32),
    \`after.region\` Nullable(String),
    \`after.status\` Nullable(String),
    \`after.customer_email\` Nullable(String),
    \`after.notes\` Nullable(String),
    \`after.created_at\` Nullable(Int64)
)
ENGINE = Kafka
SETTINGS kafka_broker_list = '$BROKERS',
         kafka_topic_list = 'dbserver1.public.demo',
         kafka_group_name = 'clickhouse-demo-consumer',
         kafka_format = 'AvroConfluent',
         format_avro_schema_registry_url = '$REGISTRY';
"

echo "Creating Materialized View: mv_demo_realtime..."
docker exec dlh-clickhouse clickhouse-client -u $USER --password "$PASS" -d $DB -q "
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_demo_realtime
TO silver_demo AS
SELECT
    \`after.id\` AS id,
    \`after.name\` AS name,
    \`after.category\` AS category,
    \`after.value\` AS value,
    \`after.quantity\` AS quantity,
    toDate(\`after.order_date\`) AS order_date,
    \`after.region\` AS region,
    \`after.status\` AS status,
    \`after.customer_email\` AS customer_email,
    \`after.notes\` AS notes,
    fromUnixTimestamp64Milli(\`after.created_at\`) AS created_at,
    'realtime-cdc' AS _pipeline_run_id,
    'PostgreSQL.public.demo' AS _source_table,
    now64(3) AS _silver_processed_at,
    now64(3) AS _db_processed_at
FROM kafka_demo
WHERE \`after.id\` IS NOT NULL;
"

echo "ClickHouse Kafka Ingestion Setup Complete."

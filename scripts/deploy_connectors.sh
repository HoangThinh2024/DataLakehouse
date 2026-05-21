#!/usr/bin/env bash
# ============================================================================
# DataLakehouse – Kafka Connect Deployment Script
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# Load environment library
if [[ -f "$SCRIPT_DIR/lib_env.sh" ]]; then
  source "$SCRIPT_DIR/lib_env.sh"
else
  echo "Error: lib_env.sh not found in $SCRIPT_DIR"
  exit 1
fi

# Load environment variables
load_env_file "$ENV_FILE"

# Configuration from Goal
KAFKA_CONNECT_URL="http://localhost:8083"
POSTGRES_DB="${POSTGRES_DB:-datalakehouse}"
POSTGRES_USER="${POSTGRES_USER:-doe}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change-me-in-production}"
POSTGRES_HOST="${POSTGRES_HOST:-dlh-postgres}"
SCHEMA_REGISTRY_URL="http://redpanda:8081"
RUSTFS_ENDPOINT="http://rustfs:9000"
RUSTFS_ACCESS_KEY="${RUSTFS_ACCESS_KEY:-rustfsadmin}"
RUSTFS_SECRET_KEY="${RUSTFS_SECRET_KEY:-rustfsadmin}"
BRONZE_BUCKET="bronze"

header "Deploying Kafka Connectors"

# Wait for Kafka Connect to be ready
info "Waiting for Kafka Connect at $KAFKA_CONNECT_URL..."
MAX_RETRIES=60
RETRY_COUNT=0
until curl -s "$KAFKA_CONNECT_URL/" > /dev/null; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [[ $RETRY_COUNT -ge $MAX_RETRIES ]]; then
    err "Kafka Connect did not become ready in time."
    exit 1
  fi
  echo -n "."
  sleep 2
done
echo ""
info "Kafka Connect is ready."

# 1. Register Postgres Source Connector (Debezium)
info "Registering postgres-source connector..."
curl -s -X PUT -H "Content-Type:application/json" \
  "$KAFKA_CONNECT_URL/connectors/postgres-source/config" -d '{
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "'"$POSTGRES_HOST"'",
    "database.port": "5432",
    "database.user": "'"$POSTGRES_USER"'",
    "database.password": "'"$POSTGRES_PASSWORD"'",
    "database.dbname": "'"$POSTGRES_DB"'",
    "database.server.name": "dbserver1",
    "topic.prefix": "dbserver1",
    "table.include.list": "public.demo",
    "plugin.name": "pgoutput",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "'"$SCHEMA_REGISTRY_URL"'",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "'"$SCHEMA_REGISTRY_URL"'"
}' | jq .

# 2. Register RustFS S3 Sink Connector
info "Registering rustfs-sink connector..."
curl -s -X PUT -H "Content-Type:application/json" \
  "$KAFKA_CONNECT_URL/connectors/rustfs-sink/config" -d '{
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "tasks.max": "1",
    "topics": "dbserver1.public.demo",
    "s3.region": "us-east-1",
    "s3.bucket.name": "'"$BRONZE_BUCKET"'",
    "s3.part.size": "5242880",
    "flush.size": "3",
    "storage.class": "io.confluent.connect.s3.storage.S3Storage",
    "format.class": "io.confluent.connect.s3.format.parquet.ParquetFormat",
    "schema.compatibility": "NONE",
    "aws.access.key.id": "'"$RUSTFS_ACCESS_KEY"'",
    "aws.secret.access.key": "'"$RUSTFS_SECRET_KEY"'",
    "store.url": "'"$RUSTFS_ENDPOINT"'",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "'"$SCHEMA_REGISTRY_URL"'",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "'"$SCHEMA_REGISTRY_URL"'",
    "transforms": "AddMetadata",
    "transforms.AddMetadata.type": "org.apache.kafka.connect.transforms.InsertField$Value",
    "transforms.AddMetadata.offset.field": "_kafka_offset",
    "transforms.AddMetadata.partition.field": "_kafka_partition",
    "transforms.AddMetadata.timestamp.field": "_kafka_timestamp"
}' | jq .

# Verify status
header "Connector Status"
curl -s "$KAFKA_CONNECT_URL/connectors?expand=status" | jq .

info "Deployment complete."

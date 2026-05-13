# Phase 2 Implementation Plan: Real-Time Ingestion Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real-time CDC from PostgreSQL to ClickHouse and RustFS using Debezium, Redpanda, and Kafka Connect.

**Architecture:** Dual-Sink pattern. Postgres changes flow through Debezium to Redpanda. ClickHouse consumes via Kafka Engine/MV for fast analytics, while S3 Sink Connector buffers to RustFS for permanent archival.

**Tech Stack:** Docker Compose, Redpanda, Kafka Connect (Debezium + Confluent S3 Sink), ClickHouse, dbt.

---

### Task 1: Update Infrastructure (Docker Compose)

**Files:**
- Modify: `docker-compose.yaml`

- [ ] **Step 1: Add Redpanda and Console**
Append the Redpanda broker and its console to `docker-compose.yaml`.

```yaml
  redpanda:
    image: docker.redpanda.com/redpandadata/redpanda:v23.2.19
    container_name: dlh-redpanda
    command:
      - redpanda
      - start
      - --smp 1
      - --memory 1G
      - --reserve-memory 0M
      - --overprovisioned
      - --node-id 0
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
      - --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082
      - --advertise-pandaproxy-addr internal://redpanda:8082,external://localhost:18082
      - --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081
      - --rpc-addr redpanda:33145
      - --advertise-rpc-addr redpanda:33145
    ports:
      - "19092:19092"
      - "18081:18081"
      - "18082:18082"
    volumes:
      - ./data/redpanda:/var/lib/redpanda/data
    networks:
      - web_network
    healthcheck:
      test: ["CMD-SHELL", "rpk cluster health | grep -E 'Healthy:.+true' || exit 1"]
      interval: 15s
      timeout: 3s
      retries: 5
      start_period: 20s

  redpanda-console:
    image: docker.redpanda.com/redpandadata/console:v2.3.8
    container_name: dlh-redpanda-console
    entrypoint: /bin/sh
    command: -c "echo \"$$CONSOLE_CONFIG_FILE\" > /tmp/config.yml; /app/console"
    environment:
      CONFIG_FILEPATH: /tmp/config.yml
      CONSOLE_CONFIG_FILE: |
        kafka:
          brokers: ["redpanda:9092"]
          schemaRegistry:
            enabled: true
            urls: ["http://redpanda:8081"]
        redpanda:
          adminApi:
            enabled: true
            urls: ["http://redpanda:9644"]
    ports:
      - "8080:8080"
    networks:
      - web_network
    depends_on:
      redpanda:
        condition: service_healthy
```

- [ ] **Step 2: Add Kafka Connect with Plugins**
Add the Kafka Connect service configured to talk to Redpanda, including the Debezium Postgres and Confluent S3 plugins.

```yaml
  kafka-connect:
    image: confluentinc/cp-kafka-connect:7.5.0
    container_name: dlh-kafka-connect
    depends_on:
      redpanda:
        condition: service_healthy
      postgres:
        condition: service_healthy
      rustfs:
        condition: service_healthy
    ports:
      - "8083:8083"
    networks:
      - web_network
    environment:
      CONNECT_BOOTSTRAP_SERVERS: 'redpanda:9092'
      CONNECT_REST_ADVERTISED_HOST_NAME: 'kafka-connect'
      CONNECT_REST_PORT: '8083'
      CONNECT_GROUP_ID: 'connect-cluster'
      CONNECT_CONFIG_STORAGE_TOPIC: 'connect-configs'
      CONNECT_OFFSET_STORAGE_TOPIC: 'connect-offsets'
      CONNECT_STATUS_STORAGE_TOPIC: 'connect-status'
      CONNECT_KEY_CONVERTER: 'io.confluent.connect.avro.AvroConverter'
      CONNECT_VALUE_CONVERTER: 'io.confluent.connect.avro.AvroConverter'
      CONNECT_KEY_CONVERTER_SCHEMA_REGISTRY_URL: 'http://redpanda:8081'
      CONNECT_VALUE_CONVERTER_SCHEMA_REGISTRY_URL: 'http://redpanda:8081'
      CONNECT_INTERNAL_KEY_CONVERTER: 'org.apache.kafka.connect.json.JsonConverter'
      CONNECT_INTERNAL_VALUE_CONVERTER: 'org.apache.kafka.connect.json.JsonConverter'
      CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR: '1'
      CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR: '1'
      CONNECT_STATUS_STORAGE_REPLICATION_FACTOR: '1'
      CONNECT_PLUGIN_PATH: "/usr/share/java,/usr/share/confluent-hub-components"
    command: 
      - bash 
      - -c 
      - |
        confluent-hub install --no-prompt io.debezium/debezium-connector-postgresql:2.4.0
        confluent-hub install --no-prompt confluentinc/kafka-connect-s3:10.5.5
        /etc/confluent/docker/run
```

- [ ] **Step 3: Check configuration**
Run `docker compose config` to verify the YAML syntax is valid.

- [ ] **Step 4: Commit**
```bash
git add docker-compose.yaml
git commit -m "feat: add redpanda and kafka-connect infrastructure to docker-compose"
```

### Task 2: Configure PostgreSQL for Logical Replication

**Files:**
- Modify: `docker-compose.yaml` (postgres section)

- [ ] **Step 1: Update Postgres command**
Modify the `postgres` service in `docker-compose.yaml` to set `wal_level=logical`.

```yaml
# In docker-compose.yaml, under the `postgres` service:
    command: ["postgres", "-c", "wal_level=logical"]
```

- [ ] **Step 2: Start new services**
Run `docker compose up -d postgres redpanda redpanda-console kafka-connect`

- [ ] **Step 3: Verify Postgres WAL level**
```bash
docker exec dlh-postgres psql -U doe -d datalake -c "SHOW wal_level;"
# Expected output should show "logical"
```

- [ ] **Step 4: Commit**
```bash
git add docker-compose.yaml
git commit -m "feat: configure postgres for logical replication"
```

### Task 3: Deploy CDC Source Connector

**Files:**
- Create: `scripts/deploy_connectors.sh`

- [ ] **Step 1: Write connector deployment script**
Create the script to submit the Debezium Postgres connector configuration to the Kafka Connect API.

```bash
# scripts/deploy_connectors.sh
#!/bin/bash
set -e

CONNECT_URL="http://localhost:8083/connectors"

echo "Waiting for Kafka Connect to be ready..."
while ! curl -s -f http://localhost:8083/ > /dev/null; do
  sleep 2
done
echo "Kafka Connect is ready."

echo "Deploying Postgres CDC Source Connector..."
curl -X POST $CONNECT_URL \
  -H "Content-Type: application/json" \
  -d '{
  "name": "postgres-source",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "plugin.name": "pgoutput",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "doe",
    "database.password": "Do12345678910..",
    "database.dbname": "datalake",
    "database.server.name": "pg-lakehouse",
    "table.include.list": "public.project_reports",
    "topic.prefix": "cdc",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "http://redpanda:8081",
    "value.converter.schema.registry.url": "http://redpanda:8081",
    "slot.name": "debezium_slot"
  }
}'

echo -e "\nConnector deployed."
```

- [ ] **Step 2: Make executable and run**
```bash
chmod +x scripts/deploy_connectors.sh
./scripts/deploy_connectors.sh
```

- [ ] **Step 3: Verify deployment**
```bash
curl -s http://localhost:8083/connectors/postgres-source/status
# Expected output: JSON showing state: RUNNING
```

- [ ] **Step 4: Commit**
```bash
git add scripts/deploy_connectors.sh
git commit -m "feat: script to deploy debezium postgres source connector"
```

### Task 4: Deploy S3 Sink Connector (RustFS)

**Files:**
- Modify: `scripts/deploy_connectors.sh`

- [ ] **Step 1: Append S3 Sink configuration**
Add the S3 Sink configuration to the deployment script.

```bash
# Append to scripts/deploy_connectors.sh:

echo "Deploying RustFS S3 Sink Connector..."
curl -X POST $CONNECT_URL \
  -H "Content-Type: application/json" \
  -d '{
  "name": "rustfs-sink",
  "config": {
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "tasks.max": "1",
    "topics": "cdc.public.project_reports",
    "s3.region": "us-east-1",
    "s3.bucket.name": "bronze",
    "s3.part.size": "5242880",
    "flush.size": "1000",
    "rotate.interval.ms": "600000",
    "storage.class": "io.confluent.connect.s3.storage.S3Storage",
    "format.class": "io.confluent.connect.s3.format.parquet.ParquetFormat",
    "store.url": "http://rustfs:9000",
    "aws.access.key.id": "doe",
    "aws.secret.access.key": "Do12345678910..",
    "s3.path.style.access": "true",
    "schema.compatibility": "NONE",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "http://redpanda:8081",
    "value.converter.schema.registry.url": "http://redpanda:8081"
  }
}'

echo -e "\nS3 Sink Connector deployed."
```

- [ ] **Step 2: Run script to deploy sink**
```bash
./scripts/deploy_connectors.sh
```

- [ ] **Step 3: Verify deployment**
```bash
curl -s http://localhost:8083/connectors/rustfs-sink/status
# Expected output: JSON showing state: RUNNING
```

- [ ] **Step 4: Commit**
```bash
git add scripts/deploy_connectors.sh
git commit -m "feat: add rustfs s3 sink connector to deployment script"
```

### Task 5: ClickHouse Kafka Engine & dbt Models

**Files:**
- Modify: `mage/dbt_lakehouse/dbt_project.yml`
- Create: `mage/dbt_lakehouse/models/staging/src_kafka_project_reports.sql`
- Create: `mage/dbt_lakehouse/models/marts/stg_realtime_project_reports.sql`

- [ ] **Step 1: Configure dbt to allow pre/post hooks**
Ensure `dbt_project.yml` supports custom materializations if needed, though we will use `table` and explicit SQL for Kafka engines.

- [ ] **Step 2: Create Kafka Engine Source Table**
Since dbt standard materializations don't support `ENGINE = Kafka`, we create a macro or run a raw DDL to set it up. We'll use a `run-operation` or raw SQL via `clickhouse-client` for the initial setup, as Kafka Engine tables are infrastructure.

```bash
docker exec dlh-clickhouse clickhouse-client -u doe --password 'Do12345678910..' -d analytics -q "
CREATE TABLE IF NOT EXISTS kafka_project_reports
(
    \`after.Mã công việc (ID)\` String,
    \`after.Tên công việc\` String,
    \`after.Trạng thái\` String,
    \`after.Số tiền\` Float64,
    \`after.Diện tích (ha)\` Float64
)
ENGINE = Kafka
SETTINGS kafka_broker_list = 'redpanda:9092',
         kafka_topic_list = 'cdc.public.project_reports',
         kafka_group_name = 'clickhouse-consumer',
         kafka_format = 'Avro',
         kafka_schema_registry_url = 'http://redpanda:8081';
"
```

- [ ] **Step 3: Create Materialized View linking to the main table**
Run the DDL to create the Materialized View.

```bash
docker exec dlh-clickhouse clickhouse-client -u doe --password 'Do12345678910..' -d analytics -q "
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_project_reports_realtime
TO project_reports AS
SELECT
    \`after.Mã công việc (ID)\` AS \`Mã công việc (ID)\`,
    \`after.Tên công việc\` AS \`Tên công việc\`,
    \`after.Trạng thái\` AS \`Trạng thái\`,
    cast(\`after.Số tiền\` AS String) AS \`Số tiền\`,
    cast(\`after.Diện tích (ha)\` AS String) AS \`Diện tích (ha)\`,
    'realtime-cdc' AS \`_source_file_key\`,
    now64(3) AS \`_db_processed_at\`
FROM kafka_project_reports
WHERE \`after.Mã công việc (ID)\` IS NOT NULL;
"
```

- [ ] **Step 4: Commit**
```bash
# We will script this setup in a new file
cat << 'EOF' > scripts/setup_clickhouse_kafka.sh
#!/bin/bash
docker exec dlh-clickhouse clickhouse-client -u doe --password 'Do12345678910..' -d analytics -q "
CREATE TABLE IF NOT EXISTS kafka_project_reports
(
    \`after.Mã công việc (ID)\` String,
    \`after.Tên công việc\` String,
    \`after.Trạng thái\` String,
    \`after.Số tiền\` Float64,
    \`after.Diện tích (ha)\` Float64
)
ENGINE = Kafka
SETTINGS kafka_broker_list = 'redpanda:9092',
         kafka_topic_list = 'cdc.public.project_reports',
         kafka_group_name = 'clickhouse-consumer',
         kafka_format = 'Avro',
         kafka_schema_registry_url = 'http://redpanda:8081';
"

docker exec dlh-clickhouse clickhouse-client -u doe --password 'Do12345678910..' -d analytics -q "
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_project_reports_realtime
TO project_reports AS
SELECT
    \`after.Mã công việc (ID)\` AS \`Mã công việc (ID)\`,
    \`after.Tên công việc\` AS \`Tên công việc\`,
    \`after.Trạng thái\` AS \`Trạng thái\`,
    cast(\`after.Số tiền\` AS String) AS \`Số tiền\`,
    cast(\`after.Diện tích (ha)\` AS String) AS \`Diện tích (ha)\`,
    'realtime-cdc' AS \`_source_file_key\`,
    now64(3) AS \`_db_processed_at\`
FROM kafka_project_reports
WHERE \`after.Mã công việc (ID)\` IS NOT NULL;
"
EOF
chmod +x scripts/setup_clickhouse_kafka.sh
./scripts/setup_clickhouse_kafka.sh

git add scripts/setup_clickhouse_kafka.sh
git commit -m "feat: add clickhouse kafka engine and materialized view setup script"
```

### Task 6: System Test

- [ ] **Step 1: Insert record in Postgres**
```bash
docker exec dlh-postgres psql -U doe -d datalake -c "
INSERT INTO project_reports (\"Mã công việc (ID)\", \"Tên công việc\", \"Trạng thái\", \"Số tiền\", \"Diện tích (ha)\") 
VALUES ('TEST-CDC-001', 'Realtime CDC Test', 'Đang làm', 1000000, 5.5);
"
```

- [ ] **Step 2: Verify in ClickHouse**
```bash
docker exec dlh-clickhouse clickhouse-client -u doe --password 'Do12345678910..' -d analytics -q "
SELECT * FROM project_reports WHERE \`Mã công việc (ID)\` = 'TEST-CDC-001';
"
# Expected output: Record is present with _source_file_key = 'realtime-cdc'
```

- [ ] **Step 3: Trigger S3 Flush (Testing buffer)**
Wait 10 minutes or check S3 for the new partition folder in `bronze/cdc.public.project_reports/` using the list contents script.

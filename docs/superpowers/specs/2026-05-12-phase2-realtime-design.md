# Phase 2 Design: Real-Time Ingestion Architecture

## 1. Overview
Phase 2 transitions the DataLakehouse from a batch-only architecture to a true hybrid system by introducing Change Data Capture (CDC) for near real-time data ingestion from PostgreSQL.

## 2. Architecture: The Dual-Sink Pattern
To maintain the Lakehouse philosophy, CDC data must serve two purposes simultaneously:
1.  **Fast Analytics**: Available in ClickHouse immediately.
2.  **Permanent Archival & Replay**: Stored in RustFS (S3) for historical record and disaster recovery.

**Flow:**
`PostgreSQL (WAL)` -> `Debezium (Kafka Connect)` -> `Redpanda (Message Broker)` 
  ├─> `ClickHouse Kafka Engine` -> `Materialized View` -> `Analytics Table`
  └─> `S3 Sink Connector` -> `RustFS (Bronze Layer)`

## 3. Technology Stack & Configuration

### A. Message Broker (Redpanda)
-   **Why Redpanda?** Kafka-compatible, lighter footprint (no ZooKeeper required), built-in Schema Registry, and native tiered storage capabilities.
-   **Deployment**: A single-node Redpanda cluster initially (to conserve WSL2 resources), with potential to scale to 3 nodes in production.
-   **Schema Management**: We will use Avro with the built-in Schema Registry to ensure strong typing between Postgres and ClickHouse.

### B. CDC Source (Kafka Connect + Debezium)
-   **Deployment**: A Kafka Connect container image equipped with `debezium-connector-postgres` and `confluentinc/kafka-connect-s3`.
-   **Postgres Configuration**: Requires setting `wal_level = logical` in PostgreSQL configuration.
-   **Connector API Payload Example**:
    ```json
    {
      "name": "postgres-source",
      "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "plugin.name": "pgoutput",
        "database.hostname": "postgres",
        "database.user": "doe",
        "database.dbname" : "datalake",
        "table.include.list": "public.source_tables",
        "topic.prefix" : "cdc",
        "key.converter": "io.confluent.connect.avro.AvroConverter",
        "value.converter": "io.confluent.connect.avro.AvroConverter",
        "key.converter.schema.registry.url": "http://redpanda:8081",
        "value.converter.schema.registry.url": "http://redpanda:8081"
      }
    }
    ```

### C. The Data Lake Sink (Kafka Connect + S3 Sink)
-   **Goal**: Avoid "small files" problem on RustFS.
-   **Buffer Policy**: The S3 Sink connector will be configured to flush records to Parquet files only when size reaches ~100MB or time reaches 15 minutes.
    ```json
    {
      "name": "rustfs-sink",
      "config": {
        "connector.class": "io.confluent.connect.s3.S3SinkConnector",
        "format.output.type": "PARQUET",
        "aws.s3.bucket.name": "bronze",
        "store.url": "http://dlh-rustfs:9000",
        "flush.size": "50000",
        "rotate.interval.ms": "900000"
      }
    }
    ```

### D. The Data Warehouse Sink (ClickHouse & dbt)
-   **Kafka Engine**: ClickHouse will create a table with `ENGINE = Kafka` pointing to the `cdc.public.*` topics.
-   **Data Quality (Post-Ingestion)**: Since real-time streaming bypasses Mage, we will rely on ClickHouse table constraints and dbt tests.
-   **dbt Integration**: dbt will manage the Materialized Views that pipe data from the Kafka Engine table into the final MergeTree tables. This keeps all transformation logic (batch and stream) unified in dbt.

## 4. Implementation Steps
1.  **Infrastructure**: Update `docker-compose.yaml` to include Redpanda, Redpanda Console, and a custom Kafka Connect image (with Debezium + S3 plugins).
2.  **Postgres Config**: Modify Postgres startup to enable logical replication.
3.  **Connector Deployment**: Create a bash script using `curl` to submit the Source and Sink connector configurations to the Kafka Connect REST API (port 8083).
4.  **ClickHouse Schema**: Use dbt to define the Kafka Engine source, the target MergeTree table, and the Materialized View bridging them.
5.  **Testing**: Insert rows into Postgres and verify they appear in both RustFS (after buffer time) and ClickHouse (instantly).

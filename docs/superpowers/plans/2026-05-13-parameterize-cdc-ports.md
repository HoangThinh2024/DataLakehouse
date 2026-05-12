# Parameterize CDC Infrastructure Ports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parameterize host ports for Redpanda and Kafka Connect, and enable logical replication in PostgreSQL to support CDC.

**Architecture:** Update `.env.example` with new port variables and modify `docker-compose.yaml` to use these variables with consistent bind-IP patterns. Enable `wal_level=logical` in PostgreSQL via the `command` directive.

**Tech Stack:** Docker Compose, PostgreSQL, Redpanda, Kafka Connect.

---

### Task 1: Update `.env.example`

**Files:**
- Modify: `/mnt/d/DataLakehouse/.env.example`

- [ ] **Step 1: Add CDC infrastructure port variables**

Add the following block to `/mnt/d/DataLakehouse/.env.example`, likely after the ClickHouse section.

```env
# ============================================================
# CDC Infrastructure (Redpanda & Kafka Connect)
# ============================================================
DLH_REDPANDA_KAFKA_PORT=29092
DLH_REDPANDA_REGISTRY_PORT=29081
DLH_REDPANDA_PROXY_PORT=29082
DLH_REDPANDA_CONSOLE_PORT=29080
DLH_KAFKA_CONNECT_PORT=28083
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "feat: add CDC infrastructure port variables to .env.example"
```

### Task 2: Enable Logical Replication in `dlh-postgres`

**Files:**
- Modify: `/mnt/d/DataLakehouse/docker-compose.yaml`

- [ ] **Step 1: Add command to `dlh-postgres`**

In `docker-compose.yaml`, find the `dlh-postgres` service and add the `command` directive.

```yaml
  dlh-postgres:
    <<: *dlh-runtime
    image: postgres:${POSTGRES_IMAGE_VERSION:-17-alpine}
    container_name: dlh-postgres
    command: ["postgres", "-c", "wal_level=logical"]
    env_file:
      - .env
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yaml
git commit -m "feat: enable logical replication in dlh-postgres"
```

### Task 3: Parameterize Redpanda Ports

**Files:**
- Modify: `/mnt/d/DataLakehouse/docker-compose.yaml`

- [ ] **Step 1: Update `redpanda` service ports and command**

Update the `command` and `ports` in the `redpanda` service to use variables.

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
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:${DLH_REDPANDA_KAFKA_PORT:-29092}
      - --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082
      - --advertise-pandaproxy-addr internal://redpanda:8082,external://localhost:${DLH_REDPANDA_PROXY_PORT:-29082}
      - --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081
      - --rpc-addr redpanda:33145
      - --advertise-rpc-addr redpanda:33145
    ports:
      - "${DLH_DATA_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}:${DLH_REDPANDA_KAFKA_PORT:-29092}:19092"
      - "${DLH_DATA_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}:${DLH_REDPANDA_REGISTRY_PORT:-29081}:18081"
      - "${DLH_DATA_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}:${DLH_REDPANDA_PROXY_PORT:-29082}:18082"
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yaml
git commit -m "refactor: parameterize redpanda ports"
```

### Task 4: Parameterize Redpanda Console Port

**Files:**
- Modify: `/mnt/d/DataLakehouse/docker-compose.yaml`

- [ ] **Step 1: Update `redpanda-console` service ports**

```yaml
  redpanda-console:
    # ...
    ports:
      - "${DLH_APP_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}:${DLH_REDPANDA_CONSOLE_PORT:-29080}:8080"
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yaml
git commit -m "refactor: parameterize redpanda-console port"
```

### Task 5: Parameterize Kafka Connect Port

**Files:**
- Modify: `/mnt/d/DataLakehouse/docker-compose.yaml`

- [ ] **Step 1: Update `kafka-connect` service ports**

```yaml
  kafka-connect:
    # ...
    ports:
      - "${DLH_APP_BIND_IP:-${DLH_BIND_IP:-127.0.0.1}}:${DLH_KAFKA_CONNECT_PORT:-28083}:8083"
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yaml
git commit -m "refactor: parameterize kafka-connect port"
```

### Task 6: Validation

- [ ] **Step 1: Run `docker compose config`**

Run: `docker compose config`
Expected: Valid YAML output without errors.

### Task 7: Final Commit and Cleanup

- [ ] **Step 1: Final commit if needed**

(Already committed in tasks, but ensure everything is clean)

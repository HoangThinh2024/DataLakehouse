# DataLakehouse Architecture

This document explains the runtime architecture, data flow, and control plane used in this repository.

## 1. System Layers

1. Ingest and Source
- PostgreSQL source tables
- CSV uploads

2. Object Storage Lake
- RustFS buckets
- Bronze (raw)
- Silver (cleaned/normalized)
- Gold (aggregated/business-ready)

3. Processing
- Mage pipelines orchestrate extraction, transform, and load stages.
- Host-side orchestration scripts trigger ETL when needed.

4. Analytics Warehouse
- ClickHouse stores query-optimized analytics tables.
- Silver and Gold outputs are loaded for BI consumption.

5. Serving and Observability
- Superset for analytics dashboards
- Grafana for operational monitoring
- NocoDB for table exploration and lightweight operations

## 2. Logical Data Flow

```text
PostgreSQL / CSV -> RustFS Bronze -> RustFS Silver -> RustFS Gold -> ClickHouse -> Superset/Grafana
```

Supporting flow:

- Metadata and service databases are hosted in PostgreSQL.
- Mage metadata, Superset metadata, Grafana metadata, and NocoDB metadata are isolated into dedicated databases.

## 3. Control Plane

Primary operational scripts:

- `scripts/setup.sh`: Guided bootstrap, `.env` generation, initial deployment.
- `scripts/stackctl.sh`: Day-2 lifecycle (`up`, `down`, `redeploy`, `health`, `logs`, `validate-env`, `sync-env`, `reset`).
- `scripts/setup_ufw_docker.sh`: Docker-aware firewall setup with `ufw-docker` and comment-tagged rules.

Validation and automation:

- `scripts/verify_lakehouse_architecture.py`: End-to-end architecture checks.
- `scripts/run_etl_and_dashboard.py`: ETL run plus dashboard provisioning flow.
- `scripts/create_superset_demo_dashboard.py`: Programmatic Superset dashboard creation.

## 4. Deployment Topology

All services are deployed via Docker Compose on a shared network (`web_network`).

Main containers:

- PostgreSQL
- RustFS (+ rustfs-init)
- ClickHouse
- Mage
- NocoDB
- Superset
- Grafana
- Optional Nginx Proxy Manager

## 5. Security Boundaries

- Container service credentials are externalized in `.env`.
- Host port binding is controlled by `DLH_BIND_IP`.
- LAN exposure is controlled by CIDR and managed firewall rules.
- Firewall automation is based on `ufw-docker` and does not alter SSH rules.

## 6. Operational Guarantees

- Reproducible bootstrap from `setup.sh` + `.env`.
- Consistent lifecycle actions via `stackctl.sh`.
- Explicit environment validation before redeploy.
- Rule cleanup support for teardown scenarios.

## 7. Visual Diagram

The architecture diagram is maintained at:

- `docs/assets/datalakehouse-architecture.svg`

And embedded in the root README for quick reference.

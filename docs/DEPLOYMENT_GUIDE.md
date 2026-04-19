# Deployment Guide

This guide describes the recommended deployment and operations flow for the DataLakehouse stack.

## 1. Prerequisites

- Linux host with Docker Engine and Docker Compose plugin
- `uv` installed for host-side Python scripts
- At least 4 GB RAM (8 GB recommended)
- Open ports for all services (defaults listed in README)

Quick checks:

```bash
docker --version
docker compose version
uv --version
```

## 2. Recommended Bootstrap Flow

Use the guided setup script:

```bash
bash scripts/setup.sh
```

What it does:

1. Reads existing `.env` values if present.
2. Prompts for mutable settings (IP, CIDR, ports, credentials, image tags).
3. Writes a complete `.env` file.
4. Creates Docker network `web_network` when needed.
5. Starts the stack and runs initial checks.

## 3. Day-2 Operations with stackctl.sh

Use `scripts/stackctl.sh` as the main lifecycle interface.

### Core commands

```bash
bash scripts/stackctl.sh up
bash scripts/stackctl.sh down
bash scripts/stackctl.sh redeploy
bash scripts/stackctl.sh redeploy --with-etl
```

### Health, logs, and diagnostics

```bash
bash scripts/stackctl.sh status
bash scripts/stackctl.sh health
bash scripts/stackctl.sh logs all
bash scripts/stackctl.sh logs dlh-mage
bash scripts/stackctl.sh inspect dlh-postgres
```

### Environment management

```bash
bash scripts/stackctl.sh check-env
bash scripts/stackctl.sh validate-env
bash scripts/stackctl.sh sync-env
```

### Reset commands

```bash
# Soft reset: remove containers, keep volumes
bash scripts/stackctl.sh reset

# Hard reset: remove containers and volumes
bash scripts/stackctl.sh reset --hard
```

## 4. Firewall and LAN Access (ufw-docker)

Firewall setup is handled by:

```bash
bash scripts/setup_ufw_docker.sh
```

Important behavior:

- Uses `ufw-docker` workflow for Docker-published ports.
- Does not manage SSH rules.
- Adds explicit comments to rules for easier auditing.
- Supports cleanup paths so rules are removed during teardown.

Common usage:

```bash
# Configure rules based on current .env/CIDR
bash scripts/setup_ufw_docker.sh

# Remove managed rules only
bash scripts/setup_ufw_docker.sh --remove

# Remove managed rules and stop stack
bash scripts/setup_ufw_docker.sh --down
```

## 5. ETL and Dashboard Automation

Run end-to-end ETL and dashboard provisioning:

```bash
uv run python scripts/run_etl_and_dashboard.py
```

Or include it in redeploy:

```bash
bash scripts/stackctl.sh redeploy --with-etl
```

## 6. Validation

Run architecture validation script:

```bash
uv run python scripts/verify_lakehouse_architecture.py
```

`check-system` in `stackctl.sh` also invokes this script when `uv` is available.

## 7. Common Recovery Procedures

### Service unhealthy

```bash
bash scripts/stackctl.sh health
bash scripts/stackctl.sh logs <service>
```

### Port conflicts

```bash
bash scripts/stackctl.sh validate-env
bash scripts/stackctl.sh sync-env
bash scripts/stackctl.sh redeploy
```

### Full rebuild

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

## 8. Production Notes

- Pin all image tags (avoid `latest`).
- Rotate all default passwords before deployment.
- Use reverse proxy/TLS for public access.
- Restrict exposed ports to trusted CIDRs.
- Back up Docker volumes: PostgreSQL, ClickHouse, RustFS.
